import sys
from pathlib import Path
import logging
import tkinter as tk
from tkinter import simpledialog, messagebox
import re

# Adicionar o diretório raiz ao path para importar as classes
sys.path.append(str(Path(__file__).parent.parent))

import config
from classes.tribunal_scraper import TribunalScraper
from classes.peticionamento_eletronico import PeticionamentoEletronico
from classes.human_helper import HumanHelper
from classes.selectors import Selectors
from classes.file_manager import FileManager
from classes import utils
from playwright.sync_api import sync_playwright, expect

def run_test():
    # 0. Configurar logger
    log_file = "test_peticionamento.log"
    utils.configurar_logger(nome_arquivo=log_file)
    logger = logging.getLogger("TestPeticionamento")
    
    # 1. Interface simples para entrada de dados
    root = tk.Tk()
    root.withdraw()
    
    numero_processo = simpledialog.askstring("Teste", "Digite o número do processo (CNJ):", initialvalue="0000459-72.2023.8.26.0106")
    if not numero_processo: return

    valor_teste = simpledialog.askfloat("Teste", "Digite o valor da execução (ex: 15200.50):", initialvalue=1500.00)
    if valor_teste is None: return

    data_transito_teste = simpledialog.askstring("Teste", "Data do trânsito em julgado:", initialvalue="05/09/2023")
    data_protocolo_teste = simpledialog.askstring("Teste", "Data do protocolo/ajuizamento:", initialvalue="10/01/2020")
    data_nascimento_teste = simpledialog.askstring("Teste", "Data de nascimento do autor:", initialvalue="15/05/1985")
    teve_impugnacao_teste = messagebox.askyesno("Teste", "Houve impugnação / Embargos?")

    autor_teste = simpledialog.askstring("Teste", "Primeiro nome do AUTOR (Ex: FABIANO):", initialvalue="FABIANO")
    autores_teste = [autor_teste] if autor_teste else []

    print("\n--- Seleção de Modo de Teste ---")
    print("1. Fluxo Completo (Acessar, Pesquisar, Upload, Tudo)")
    print("2. Apenas Finalização (Sincronizado com main.py)")
    modo = simpledialog.askstring("Modo de Teste", "Digite 1 (Completo) ou 2 (Apenas Finalização):", initialvalue="2")
    
    try:
        scraper = TribunalScraper(numero_processo)
        scraper.iniciar_navegador(headless=False)
        pet_eletronico = PeticionamentoEletronico(scraper.page)
        
        if modo == "1":
            scraper.acessar_tribunal()
            if not pet_eletronico.navegar_para_peticionamento_intermediaria(): return
            if not pet_eletronico.preencher_dados_processo(numero_processo): return
        else:
            print("💡 Aguardando detecção da tela de peticionamento...")
            scraper.page.goto("https://esaj.tjsp.jus.br/tarefas-adv/pet/intermediaria/peticionamento/novo", wait_until="networkidle")
            if "login" in scraper.page.url:
                scraper.page.wait_for_url(lambda url: "intermediaria" in url, timeout=0)

        # --- INÍCIO DO FLUXO SINCRONIZADO (main.py) ---
        
        # 1. Classificação Baseada no Valor (RPV vs Precatório)
        limite_rpv = getattr(config, 'LIMITE_RPV', 35000)
        codigo_pet = "1265" if valor_teste > limite_rpv else "1266"
        print(f"\n✅ [PASSO 1] Classificando como {'1265' if codigo_pet == '1265' else '1266'} (Baseado em R$ {valor_teste})")
        if not pet_eletronico.preencher_dados_classificacao(codigo_pet):
            print("❌ Falha na classificação.")

        # 2. Dados Suplementares (Natureza e Valor da Causa) - FEITO ANTES DO UPLOAD NO MAIN.PY
        print("\n🛠️ [PASSO 2] Preenchendo Natureza e Valor da Causa...")
        if pet_eletronico.abrir_dados_suplementares():
            if pet_eletronico.preencher_natureza_e_valor(
                valor=valor_teste, 
                data_ajuizamento=data_protocolo_teste,
                data_transito_julgado=data_transito_teste,
                teve_impugnacao=teve_impugnacao_teste
            ):
                print("✅ Natureza e Valor preenchidos.")
            else:
                print("❌ Falha no preenchimento de Natureza/Valor.")

        # 3. Categorização de Documentos (Upload já deve ter sido feito ou o usuário faz agora)
        print("\n🛠️ [PASSO 3] Categorizando Documentos (Definindo Tipos)...")
        if pet_eletronico.categorizar_documentos_upload():
            print("✅ Tipos de documentos definidos.")
            
            # 4. Adicionar partes no Polo Ativo
            print(f"\n🛠️ [PASSO 4] Incluindo autores no Polo Ativo: {autores_teste}")
            if pet_eletronico.adicionar_partes_polo_ativo(autores_teste):
                print("✅ Polo Ativo processado.")
                
                # 5. Vincular Documentos às Partes no Grid (MÉTODO REAL DO MAIN.PY)
                print("\n🛠️ [PASSO 5] Vinculando autores aos documentos (vincular_documentos_partes_lote)...")
                pet_eletronico.vincular_documentos_partes_lote(autores_teste)
                
                # 6. Preencher valores individualizados
                for autor_ind in autores_teste:
                    print(f"\n🛠️ [PASSO 6] Preenchendo valores individualizados para: {autor_ind}")
                    pet_eletronico.preencher_valores_individualizados(
                        data_nascimento=data_nascimento_teste,
                        data_base=data_protocolo_teste,
                        valor_individual=valor_teste
                    )
                
                # 7. Confirmação Final e Rascunho
                print("\n🛠️ [PASSO 7] Confirmando rodapé e finalizando...")
                if pet_eletronico.confirmar_informacoes_gerais():
                    if messagebox.askyesno("Finalizar?", "Deseja testar o salvamento de rascunho?"):
                        if pet_eletronico.finalizar_para_protocolar():
                            print("✅ Rascunho salvo com sucesso.")
                            messagebox.showinfo("Sucesso", "Teste SINCRONIZADO concluído!")
                else:
                    print("❌ Falha na confirmação do rodapé.")
            else:
                print("❌ Falha ao adicionar partes.")
        else:
            print("❌ Falha na categorização inicial.")

    except Exception as e:
        print(f"❌ Erro: {e}")
        messagebox.showerror("Erro", str(e))
    finally:
        input("\nTeste concluído. ENTER para fechar...")
        if 'scraper' in locals(): scraper.fechar_navegador()

if __name__ == "__main__":
    run_test()