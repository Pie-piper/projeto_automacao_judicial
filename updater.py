import os
import time
import sys
import shutil
import subprocess

def run_updater():
    """
    Script externo para substituir o executável principal.
    Argumentos esperados:
    sys.argv[1]: Caminho do executável principal (ex: RPV_Automacao.exe)
    sys.argv[2]: Caminho do novo arquivo baixado (ex: update_novo.exe)
    """
    
    if len(sys.argv) < 3:
        print("Erro: Argumentos insuficientes.")
        time.sleep(5)
        return

    main_exe = sys.argv[1]
    new_exe = sys.argv[2]

    print("--- INICIANDO PROCESSO DE ATUALIZACAO ---")
    print(f"Diretorio Base: {os.getcwd()}")
    
    # Aguardar encerramento do processo principal (tentativas)
    for i in range(10):
        print(f"Aguardando encerramento do programa principal (Tentativa {i+1}/10)...")
        time.sleep(2)
        try:
            if os.path.exists(main_exe):
                # Tenta abrir o arquivo para escrita; se falhar, o arquivo ainda está em uso
                with open(main_exe, 'ab') as f:
                    pass
                break # Se conseguiu abrir, o processo fechou
        except IOError:
            continue
    
    try:
        if os.path.exists(new_exe):
            print(f"Substituindo {main_exe} pelo novo executável...")
            
            # Tentar remover o antigo
            if os.path.exists(main_exe):
                try:
                    os.remove(main_exe)
                except Exception as e:
                    print(f"Aviso: Nao foi possivel remover o original ({e}). Tentando renomear.")
                    old_bak = main_exe + ".old"
                    if os.path.exists(old_bak):
                        try: os.remove(old_bak)
                        except: pass
                    os.rename(main_exe, old_bak)

            # Mover o novo para o lugar do antigo
            shutil.move(new_exe, main_exe)
            print("-----------------------------------------")
            print("ATUALIZACAO CONCLUIDA COM SUCESSO!")
            print("-----------------------------------------")
            
            # Reiniciar o programa principal
            print(f"Reiniciando {main_exe}...")
            time.sleep(1)
            subprocess.Popen([main_exe], shell=True)
        else:
            print(f"ERRO: O arquivo de atualizacao nao foi encontrado em: {new_exe}")
            time.sleep(10)

    except Exception as e:
        print(f"ERRO CRITICO DURANTE A SUBSTITUICAO: {e}")
        print("Por favor, tente rodar o instalador manualmente.")
        time.sleep(20)

if __name__ == "__main__":
    run_updater()
