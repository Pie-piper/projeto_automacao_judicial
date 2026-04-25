"""
Sistema de Licenciamento para RPV Automação
Gerencia chaves de ativação com período de 90 dias
"""

import json
import hashlib
import uuid
import os
from datetime import datetime, timedelta
from pathlib import Path
from cryptography.fernet import Fernet
import config
from .supabase_manager import SupabaseManager

class LicenseManager:
    # Chave mestra para criptografia do arquivo local (Carregada via config.py)
    SECRET_FILE_KEY = config.LICENSE_SECRET_KEY.encode()

    def __init__(self):
        self.app_dir = config.USER_DATA_DIR
        self.app_dir.mkdir(exist_ok=True, parents=True)
        
        self.license_file = self.app_dir / "license.dat"
        self.fernet = Fernet(self.SECRET_FILE_KEY)
        self.machine_id = self.get_machine_id()
        self.supabase = SupabaseManager()

    def get_machine_id(self):
        """Gera um ID único estável baseado no hardware da máquina (BIOS UUID)"""
        try:
            import subprocess
            # Tenta obter o UUID da BIOS via PowerShell (mais estável que MAC/uuid.getnode)
            cmd = 'powershell -ExecutionPolicy Bypass -Command "(Get-CimInstance Win32_ComputerSystemProduct).UUID"'
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip()
            
            # Algumas máquinas retornam UUIDs genéricos como "FFFFFFFF..."
            if not output or "FFFFFFFF" in output or "00000000" in output:
                 # Fallback para Serial da Placa Mãe
                 cmd = 'wmic baseboard get serialnumber'
                 output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().split('\n')[1].strip()
            
            if output and len(output) > 3:
                machine_id = hashlib.sha256(output.encode()).hexdigest()[:16].upper()
                return machine_id
        except Exception as e:
            print(f"Erro ao obter hardware ID estável: {e}")
        
        # Fallback para uuid.getnode (menos estável, mas evita erro fatal)
        try:
            import uuid
            node = uuid.getnode()
            return hashlib.sha256(str(node).encode()).hexdigest()[:16].upper()
        except Exception as e:
            print(f"Erro fatal ao obter interface MAC da máquina: {e}")
            return "UNKNOWN-MACHINE"

    def check_license(self):
        """
        Verifica se existe uma licença válida (Online primeiro, depois Cache Local).
        Retorna: (is_valid, message, days_remaining)
        """
        current_id = self.get_machine_id()
        
        # 1. TENTAR VALIDAÇÃO ONLINE (SUPABASE)
        if self.supabase.client:
            # Precisamos da chave para consultar. Vamos tentar ler do arquivo local primeiro.
            local_data = self._get_local_license_data()
            if local_data and 'chave' in local_data:
                chave_licenca = local_data['chave']
                online_data = self.supabase.verificar_licenca_online(chave_licenca)
                
                if online_data:
                    # Validar Machine ID no banco
                    if online_data['machine_id'] and online_data['machine_id'] != current_id:
                        return False, "Esta licença está vinculada a outro dispositivo.", 0
                    
                    # Validar Status e Data
                    if online_data['status'] != 'ativo':
                        return False, f"Licença suspensa ou inativa (Status: {online_data['status']}).", 0
                    
                    expiry_date = datetime.fromisoformat(online_data['expiry_date'].replace('Z', '+00:00'))
                    now = datetime.now(expiry_date.tzinfo)
                    
                    if now > expiry_date:
                        return False, "Sua licença expirou no servidor.", 0
                    
                    # Atualizar cache local se estiver tudo ok
                    self._save_local_cache(online_data)
                    
                    days_remaining = (expiry_date - now).days
                    self.supabase.registrar_log(chave_licenca, current_id, "check_license")
                    return True, "Licença validada online.", days_remaining

        # 2. FALLBACK: VALIDAÇÃO LOCAL (CACHE)
        if not self.license_file.exists():
            return False, "Licença não encontrada. Ative o sistema.", 0

        try:
            data = self._get_local_license_data()
            if not data:
                return False, "Erro ao ler cache de licença.", 0

            # Validar Machine ID
            if data['machine_id'] != current_id:
                return False, "Cache de licença inválido para esta máquina.", 0

            # Validar Data de Expiração
            expiry_date = datetime.fromisoformat(data['expiry_date'].replace('Z', '+00:00'))
            now = datetime.now(expiry_date.tzinfo)

            if now > expiry_date:
                return False, "Sua licença expirou.", 0

            days_remaining = (expiry_date - now).days
            return True, "Licença validada (modo offline).", days_remaining

        except Exception as e:
            return False, f"Erro na validação local: {str(e)}", 0

    def _get_local_license_data(self):
        """Lê e descriptografa o arquivo local."""
        if not self.license_file.exists(): return None
        try:
            encrypted_data = self.license_file.read_bytes()
            decrypted_data = self.fernet.decrypt(encrypted_data)
            return json.loads(decrypted_data.decode())
        except: return None

    def _save_local_cache(self, data):
        """Salva os dados da licença no arquivo local criptografado."""
        try:
            # Garantir que salvamos a chave de texto original para consultas futuras
            json_str = json.dumps(data)
            encrypted_data = self.fernet.encrypt(json_str.encode())
            self.license_file.write_bytes(encrypted_data)
        except Exception as e:
            print(f"Erro ao salvar cache: {e}")

    def activate(self, activation_key):
        """
        Ativa o software usando o Supabase.
        'activation_key' agora é a CHAVE simples cadastrada no banco.
        """
        if not self.supabase.client:
            return False, "Sem conexão com o servidor de ativação."

        try:
            # 1. Verificar se a chave existe no banco
            online_data = self.supabase.verificar_licenca_online(activation_key)
            if not online_data:
                return False, "Chave de ativação não encontrada no sistema."

            # 2. Verificar se já está vinculada a outra máquina
            if online_data['machine_id'] and online_data['machine_id'] != self.machine_id:
                return False, "Esta chave já foi utilizada em outro computador."

            # 3. Efetuar ativação no servidor
            if self.supabase.ativar_licenca_online(activation_key, self.machine_id, aceitou_termos=True):
                # 4. Salvar cache local
                online_data['machine_id'] = self.machine_id
                online_data['chave'] = activation_key # Garantir que a chave está no cache
                self._save_local_cache(online_data)
                
                self.supabase.registrar_log(activation_key, self.machine_id, "ativacao")
                return True, "Sistema ativado com sucesso!"
            
            return False, "Erro ao comunicar ativação com o servidor."

        except Exception as e:
            return False, f"Erro na ativação: {str(e)}"
