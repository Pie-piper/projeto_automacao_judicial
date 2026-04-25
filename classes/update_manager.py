import requests
from packaging.version import Version
import os
import sys
import subprocess
import config
from pathlib import Path

class UpdateManager:
    def __init__(self, current_version):
        self.current_version = current_version
        self.api_url = config.GITHUB_API_URL
        self.update_info = None

    def check_for_updates(self):
        """Consulta o GitHub para verificar se há uma versão mais recente."""
        try:
            response = requests.get(self.api_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                latest_version = data.get("tag_name", "").replace("v", "")
                
                if Version(latest_version) > Version(self.current_version):
                    # Priorizar o executável principal (não-updater, não-instalador)
                    assets = data.get("assets", [])
                    download_url = None
                    for asset in assets:
                        nome = asset.get("name", "").lower()
                        # Procura por nome que termina em .exe e não é updater nem instalador
                        if nome.endswith(".exe") and "updater" not in nome and "instalador" not in nome:
                            download_url = asset.get("browser_download_url")
                            break
                    
                    # Se não achou com nome específico, pega o primeiro .exe que não seja updater
                    if not download_url:
                        for asset in assets:
                            nome = asset.get("name", "").lower()
                            if nome.endswith(".exe") and "updater" not in nome:
                                download_url = asset.get("browser_download_url")
                                break

                    if download_url:
                        self.update_info = {
                            "version": latest_version,
                            "url": download_url,
                            "notes": data.get("body", "")
                        }
                        return True, self.update_info
            
            return False, None
        except Exception as e:
            print(f"Erro ao verificar atualizações: {e}")
            return False, None

    def download_update(self, url, dest_path):
        """Baixa o novo executável em pasta segura (AppData)"""
        try:
            # Garantir que a pasta do destino existe
            Path(dest_path).parent.mkdir(exist_ok=True, parents=True)
            
            print(f"Baixando atualização para {dest_path}...")
            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()
            
            with open(dest_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk: f.write(chunk)
            return True
        except Exception as e:
            print(f"Erro ao baixar atualização: {e}")
            return False

    def launch_updater(self):
        """Lança o executável secundário de atualização e fecha o app atual"""
        # O updater.exe deve estar na mesma pasta do executável principal
        pasta_exe = Path(sys.executable).parent
        updater_exe = pasta_exe / "updater.exe"
        
        if not updater_exe.exists():
            # Fallback para pasta raiz do projeto (desenvolvimento)
            updater_exe = config.BASE_DIR / "updater.exe"

        if updater_exe.exists():
            main_exe = sys.executable
            # O novo executável é baixado para a pasta temp definida no config (AppData)
            new_exe = config.TEMP_DIR / "update_novo.exe"
            
            if "python" in main_exe.lower():
                print("Modo dev: Updater ignorado.")
                return False

            print(f"Invocando updater: {updater_exe}")
            # subprocess.Popen para não bloquear e permitir que o main feche
            subprocess.Popen([str(updater_exe), str(main_exe), str(new_exe)], 
                            cwd=str(pasta_exe),
                            shell=True)
            return True
        else:
            print(f"ERRO: updater.exe não encontrado!")
        return False
