"""
GERADOR DE CHAVES DE ATIVAÇÃO - ADMINISTRATIVO
RPV Automação
"""

import json
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
import sys
import os
from dotenv import load_dotenv

# Carregar config local
load_dotenv()

# DEVE SER A MESMA CHAVE DO LICENSE_MANAGER.PY
SECRET_FILE_KEY = os.getenv("LICENSE_SECRET_KEY", "8vcgDu3dPSnYujPHP12uADCJ2slnAeIcHUZLyhX0WaM=").encode()

import hashlib
import subprocess

def get_stable_machine_id():
    """Gera um ID único estável baseado no hardware da máquina (BIOS UUID)"""
    try:
        # Tenta obter o UUID da BIOS via PowerShell
        cmd = 'powershell -ExecutionPolicy Bypass -Command "(Get-CimInstance Win32_ComputerSystemProduct).UUID"'
        output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip()
        
        if not output or "FFFFFFFF" in output or "00000000" in output:
             cmd = 'wmic baseboard get serialnumber'
             output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().split('\n')[1].strip()
        
        if output and len(output) > 3:
            return hashlib.sha256(output.encode()).hexdigest()[:16].upper()
    except:
        pass
    
    try:
        import uuid
        node = uuid.getnode()
        return hashlib.sha256(str(node).encode()).hexdigest()[:16].upper()
    except:
        return "UNKNOWN-MACHINE"

def gerar_chave(machine_id, dias=90):
    fernet = Fernet(SECRET_FILE_KEY)
    
    expiry_date = datetime.now() + timedelta(days=dias)
    
    data = {
        'machine_id': machine_id.upper().strip(),
        'expiry_date': expiry_date.isoformat(),
        'generated_at': datetime.now().isoformat()
    }
    
    json_data = json.dumps(data).encode()
    token = fernet.encrypt(json_data).decode()
    
    return token

if __name__ == "__main__":
    print("-" * 40)
    print("GERADOR DE CHAVES - RPV AUTOMAÇÃO")
    print("-" * 40)
    
    # Mostrar ID atual para teste
    meu_id = get_stable_machine_id()
    print(f"ID desta máquina: {meu_id}\n")
    
    m_id = input("Digite o ID DA MÁQUINA do cliente: ").strip()
    if not m_id:
        print("Erro: ID da máquina é obrigatório.")
        sys.exit()
    
    try:
        prazo = int(input("Dias de validade (padrão 90): ") or 90)
    except:
        prazo = 90
        
    chave = gerar_chave(m_id, prazo)
    
    print("\n" + "=" * 60)
    print("CHAVE DE ATIVAÇÃO GERADA:")
    print("-" * 60)
    print(chave)
    print("=" * 60)
    print("\nCopie a chave acima e envie para o cliente.")
    input("\nPressione ENTER para sair...")
