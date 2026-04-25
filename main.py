# type: ignore
from classes.interface import TkinterInterface  # Nova interface modular baseada em CustomTkinter
from classes.threaded_scraper import ThreadedScraper  # type: ignore
from classes.file_manager import FileManager  # type: ignore
from classes.pdf_extractor import PDFExtractor  # type: ignore
from classes.document_generator import DocumentGenerator  # type: ignore
from classes.pdf_merger import PDFMerger  # type: ignore
from classes.peticionamento_helper import PeticionamentoHelper  # type: ignore
from classes.license_manager import LicenseManager  # type: ignore
from classes.update_manager import UpdateManager  # type: ignore
from classes.word_automation import WordAutomation  # type: ignore
from classes.tribunal_scraper import TribunalScraper  # type: ignore
from classes.peticionamento_eletronico import PeticionamentoEletronico  # type: ignore
from classes import utils  # type: ignore
import config  # type: ignore
import traceback
import queue
import logging
import sys
import os
import time
import re
import threading
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

# --- CONFIGURAÇÃO PLAYWRIGHT ---
if getattr(sys, 'frozen', False):
    bundle_dir = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent)).resolve()
    browsers_path = (bundle_dir / "browsers").resolve()
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_path)
# -------------------------------


def _formatar_numero_processo(numero_norm: str) -> str:
    """Converte dígitos puro (ex: '00003055...') para formato TJSP NNNNNNN-DD.AAAA.J.TR.OOOO."""
    d = re.sub(r'[^\d]', '', str(numero_norm))
    if len(d) == 20:
        return f"{d[0:7]}-{d[7:9]}.{d[9:13]}.{d[13]}.{d[14:16]}.{d[16:20]}"
    return numero_norm  # Retorna como está se não bater o tamanho esperado


def main():
    log_file = config.LOGS_DIR / "automacao.log"
    utils.configurar_logger(str(log_file))
    print("Iniciando sistema...")

    try:
        if getattr(sys, 'frozen', False):
            update_mgr = UpdateManager(config.VERSION)
            tem_update, info = update_mgr.check_for_updates()
            if tem_update:
                temp_interface = TkinterInterface()
                if temp_interface.mostrar_confirmacao("Atualização Disponível", f"Nova versão {info['version']}!"):
                    dest = config.TEMP_DIR / "update_novo.exe"
                    if update_mgr.download_update(info['url'], dest):
                        if update_mgr.launch_updater():
                            sys.exit(0)
                temp_interface.fechar()
    except Exception as e: print(f"Erro na rotina de update: {e}")

    while True:
        interface = TkinterInterface()
        licenca = LicenseManager()
        valid, msg, dias = licenca.check_license()
        
        if not valid:
            if not interface.mostrar_termos_uso():
                interface.fechar(); break
                
            chave = interface.solicitar_ativacao(licenca.machine_id)
            if chave:
                logging.info(f"Tentando ativação com chave: {chave}")
                success, msg_ativ = licenca.activate(chave)
                if success:
                    interface.mostrar_mensagem("Sucesso", "Sistema ativado com sucesso!")
                    valid, msg, dias = licenca.check_license()
                else:
                    interface.mostrar_erro("Falha na Ativação", f"Não foi possível ativar:\n{msg_ativ}")
                    interface.fechar(); break
            else:
                interface.fechar(); break

        if not config.LOGIN_TJSP or not config.SENHA_TJSP:
            interface.mostrar_mensagem("Primeiro Acesso", "Bem-vindo! Por favor, configure suas credenciais do TJSP e E-mail nas Configurações.")
            interface.mostrar_configuracoes()
            if getattr(interface, 'reiniciar_sistema', False):
                try: interface.destroy()
                except: pass
                continue # Recarrega o loop com as novas variáveis do .env
            else:
                interface.fechar(); break
        
        if dias <= 3: interface.mostrar_mensagem("Aviso", f"Licença expira em {dias} dias.")

        try:
            numero_processo = interface.pedir_numero_processo()
            if not numero_processo: interface.fechar(); break
            
            msg_queue = queue.Queue()
            scraper_thread = ThreadedScraper(numero_processo, msg_queue)
            interface.mostrar_janela_progresso(callback_cancelar=scraper_thread.stop)
            scraper_thread.start()
            
            def on_success(): continuar_processamento(scraper_thread, interface)
            def on_error(e): interface.mostrar_erro("Erro", str(e))
            
            interface.processar_queue(msg_queue, scraper_thread, on_success, on_error)
            interface.mainloop()
            
            if getattr(interface, 'reiniciar_sistema', False):
                try: interface.destroy()
                except: pass
                continue
            else: interface.fechar(); break
        except Exception as e:
            interface.mostrar_erro("Erro", str(e))
            interface.fechar(); break


def continuar_processamento(scraper_thread, interface):
    scraper = None
    try:
        interface.title("Automação Judicial")
        scraper = scraper_thread.get_scraper()
        numero_processo = scraper_thread.numero_processo
        
        if hasattr(scraper_thread, 'resultados_scraping'):
            interface.mostrar_relatorio_downloads(scraper_thread.resultados_scraping, getattr(scraper_thread, 'url_pasta_digital', ""), 
                                               on_abrir_pasta=lambda: threading.Thread(target=scraper.navegar_ate_pasta_digital, daemon=True).start())
        
        # ❗ FECHAMENTO IMEDIATO APÓS DOWNLOADS ❗
        if scraper:
            try:
                logging.info("🧹 Encerrando navegador do scraper imediatamente após downloads...")
                scraper.fechar_navegador()
                scraper = None # Limpa a referência para não tentar fechar de novo no finally
                logging.info("✅ Navegador do scraper encerrado com sucesso.")
            except Exception as e_close:
                logging.warning(f"⚠️ Erro ao tentar encerrar navegador precocemente: {e_close}")

        file_manager = FileManager(numero_processo)
        file_manager.criar_pasta_processo()
        file_manager.mover_documentos_baixados()
        
        try:
            caminho_decisao = file_manager.obter_caminho_arquivo(config.ARQUIVO_DECISAO, "original")
            dados_extraidos = {
                'numero_processo': numero_processo,
                'data_atual': datetime.now().strftime("%d/%m/%Y"),
                'banco': config.BANCO_PADRAO,
                'agencia': config.AGENCIA_PADRAO,
                'conta_corrente': config.CONTA_PADRAO
            }
            
            if caminho_decisao.exists():
                extractor = PDFExtractor(caminho_decisao)
                dados_crus = extractor.extrair_todos_dados()
                dados_extraidos.update({
                    'cidade': dados_crus.get('cidade'),
                    'vara': dados_crus.get('vara'),
                    'valor': dados_crus.get('valor'),
                    'paginas_decisao': dados_crus.get('paginas'),
                    'data_liberacao': dados_crus.get('data_liberacao'),
                    'autor': dados_crus.get('partes', {}).get('autor'),
                    'reu': dados_crus.get('partes', {}).get('reu')
                })
                
                # Data de Nascimento
                docs_pessoais = list(file_manager.pasta_originais.glob("*Documento*Pessoal*.pdf"))
                if docs_pessoais: dados_extraidos['data_nascimento'] = PDFExtractor(docs_pessoais[0]).extrair_data_nascimento()
                
                # Fls Procuração
                caminho_proc = file_manager.obter_caminho_arquivo(config.ARQUIVO_PROCURACAO, "original")
                if caminho_proc.exists(): dados_extraidos['paginas_procuracao'] = PDFExtractor(caminho_proc).extrair_paginas_fls()

            # ─── EXTRAÇÃO DE DADOS DOS DOCUMENTOS ──────────────────────────────────────
            if hasattr(scraper_thread, 'resultados_scraping'):
                res = scraper_thread.resultados_scraping
                
                # 1. Inteligência Trânsito em Julgado (Web vs PDF)
                contexto = getattr(scraper, 'contexto_processo', None) if scraper else None
                d_transito_web = getattr(contexto, 'data_transito_julgado', None)
                d_transito_pdf = None
                
                if 'certidao' in res and res['certidao'].caminho_arquivo:
                    caminho_cert = Path(res['certidao'].caminho_arquivo)
                    if caminho_cert.exists():
                        d_transito_pdf = PDFExtractor(caminho_cert).extrair_data_transito_julgado()
                
                # Aplica a regra: Se iguais, blz. Se diferentes, a mais recente. (comparar_datas_recentes já faz isso)
                d_transito_final = utils.comparar_datas_recentes(d_transito_web, d_transito_pdf)
                if d_transito_final:
                    dados_extraidos['data_transito_julgado'] = d_transito_final
                    logging.info(f"✅ Data Trânsito em Julgado definida via dupla validação: {d_transito_final}")

                # 2. Mapeamento de Folhas (Fls.) para o Espelho
                mapping_fls = {
                    'sentenca': 'paginas_sentenca',
                    'decisao': 'paginas_sentenca',  # Fallback
                    'certidao': 'paginas_certidao',
                    'procuracao': 'paginas_procuracao',
                    'peticao': 'paginas_peticao',
                    'documentopessoal': 'paginas_documento_pessoal',
                    'planilhacalculo': 'paginas_planilha'
                }
                for k, field in mapping_fls.items():
                    if k in res and res[k].metadata:
                        val_fls = res[k].metadata.get('formato_fls')
                        if val_fls:
                            # Limpeza: remove "fls. " para deixar apenas os números (ex: "1/8")
                            val_limpo = re.sub(r'^fls\.\s*', '', str(val_fls), flags=re.IGNORECASE).strip()
                            dados_extraidos[field] = val_limpo
                            
                            # Manter compatibilidade com templates antigos se necessário
                            if field == 'paginas_sentenca':
                                dados_extraidos['paginas_decisao'] = val_limpo
                                
                            logging.info(f"✅ Folhas identificadas para {field}: {val_limpo}")
                        
                        # Extrair data de protocolo se for petição ou planilha
                        if k == 'peticao':
                            dados_extraidos['data_protocolo'] = res[k].metadata.get('data_protocolo', dados_extraidos.get('data_protocolo'))
                        elif k == 'planilhacalculo':
                            val_proto = res[k].metadata.get('data_protocolo')
                            if val_proto:
                                dados_extraidos['data_base'] = val_proto
                                logging.info(f"✅ Data Base definida via protocolo da planilha: {val_proto}")
                
            # Valores Planilha
            caminho_planilha = file_manager.obter_caminho_arquivo(config.ARQUIVO_PLANILHA, "original")
            if caminho_planilha.exists():
                ext_plan = PDFExtractor(caminho_planilha)
                val_exec = ext_plan.extrair_valor_planilha()
                if val_exec:
                    dados_extraidos.update(PeticionamentoHelper(numero_processo).calcular_diferenca_rpv(val_exec))
                
                # Extrair Data Base do Cálculo
                d_base = ext_plan.extrair_data_base_calculo()
                if d_base and not dados_extraidos.get('data_base'):
                    dados_extraidos['data_base'] = d_base
                    dados_extraidos['termo_final_juros'] = d_base # Por padrão, termo final = data base
                    logging.info(f"✅ Data Base (Cálculo) e Termo Final identificados: {d_base}")

                lista_p = ext_plan.extrair_partes_valores_planilha()
                if lista_p:
                    dados_extraidos['lista_autores'] = [p['nome'] for p in lista_p]
                    for i, p in enumerate(lista_p, 1): dados_extraidos[f'valor_unitario_{p["nome"]}'] = p['valor']

            # ─── VINCULO CUMPRIMENTO DE SENTENÇA ──────────────────────────────────────
            # O scraper salva o contexto do processo em scraper.contexto_processo.
            # Precisamos ler esse contexto ANTES de fechar o navegador.
            contexto = getattr(scraper, 'contexto_processo', None) if scraper else None
            num_cumpr = None
            num_autos = None
            
            if contexto:
                num_cumpr = getattr(contexto, 'numero_cumprimento', None)
                num_autos = getattr(contexto, 'numero_autos_principais', None)

                if num_cumpr:
                    dados_extraidos['cumprimento_sentenca'] = _formatar_numero_processo(num_cumpr)
                    logging.info(f"✅ Cumprimento de Sentença identificado: {dados_extraidos['cumprimento_sentenca']}")
                if num_autos:
                    dados_extraidos['numero_processo'] = _formatar_numero_processo(num_autos)
                    logging.info(f"✅ Autos Principais identificados: {dados_extraidos['numero_processo']}")
            
            if not num_cumpr and not num_autos:
                # Fallback: inferir pelo número digitado
                num_norm = re.sub(r'[^\d]', '', numero_processo)
                if num_norm.startswith('000'):
                    dados_extraidos['cumprimento_sentenca'] = numero_processo
                    logging.info(f"✅ Número digitado identificado como Cumprimento: {numero_processo}")
            # ──────────────────────────────────────────────────────────────────────────

            # Lógica Automática RPV/Precatório para o Espelho
            val_float = utils.parse_currency(dados_extraidos.get('valor', 0))
            dados_extraidos['tipo_requisitorio'] = "PRECATÓRIO" if val_float > config.LIMITE_RPV else "RPV"

            # O navegador já foi encerrado acima após os downloads.
            # Caso ainda existisse, o finally ao fim da função cuidaria disso.

            # LOOP DE VALIDAÇÃO (ESPELHO)
            while True:
                try:
                    logging.info("📋 Mostrando análise de placeholders...")
                    dados_validados = interface.mostrar_analise_placeholders(dados_extraidos)
                    logging.info("✅ Análise concluída. Perguntando sobre embargos...")
                except Exception as e:
                    logging.error(f"❌ Erro no análise placeholders: {e}")
                    dados_validados = dados_extraidos.copy()
                
                try:
                    teve_impugnacao_geral = interface.perguntar_embargos()
                    logging.info(f"✅ Embargos respondida: {teve_impugnacao_geral}")
                except Exception as e:
                    logging.error(f"❌ Erro ao perguntar embargos: {e}")
                    teve_impugnacao_geral = False
                
                lista_pendentes_original = dados_validados.get('lista_autores', [])
                if not lista_pendentes_original: lista_pendentes_original = [re.sub(r'\s+e\s+outros.*', '', dados_validados.get('autor', 'Autor'), flags=re.IGNORECASE).strip()]
                logging.info(f"📋 Lista de autores pendentes: {lista_pendentes_original}")
                
                lista_pendentes = lista_pendentes_original.copy()
                restart_required = False
                
                while lista_pendentes:
                    try:
                        logging.info(f"⏳ Abrindo Hall de Autores para {len(lista_pendentes)} autores...")
                        autores_sel = interface.mostrar_hall_autores(lista_pendentes)
                        logging.info(f"✅ Hall de Autores retornou: {autores_sel}")
                    except Exception as e:
                        logging.error(f"❌ Erro no Hall de Autores: {e}")
                        interface.mostrar_erro("Erro", f"Falha no Hall de Autores: {e}")
                        autores_sel = []
                        break  # Sai do loop se der erro
                        
                    if not autores_sel: 
                        logging.info("⏹️ Seleção de autores cancelada pelo usuário.")
                        break
                        
                    # Cálculo de valores individuais e totais para o lote selecionado
                    dados_ciclo = {**dados_validados}
                    autores_formatados = " e ".join(autores_sel)
                    dados_ciclo['autor'] = autores_formatados
                    
                    total_lote = 0.0
                    for i, nome in enumerate(autores_sel, 1):
                        # Pega o valor unitário salvo durante a extração da planilha
                        val_ind = utils.parse_currency(dados_validados.get(f'valor_unitario_{nome}', 0))
                        total_lote += val_ind
                        
                        # Tags individuais para o Word (autor_1, valor_1, valor_extenso_1...)
                        dados_ciclo[f'autor_{i}'] = nome
                        dados_ciclo[f'valor_{i}'] = utils.formatar_moeda(val_ind)
                        dados_ciclo[f'valor_extenso_{i}'] = utils.numero_por_extenso(val_ind)
                    
                    # Atualiza o valor total e extenso para refletir apenas o lote selecionado
                    dados_ciclo['valor'] = utils.formatar_moeda(total_lote)
                    dados_ciclo['valor_extenso'] = utils.numero_por_extenso(total_lote)
                    
                    # Novos placeholders solicitados
                    # Formato: R$ 1.234,56 (Um mil duzentos e trinta e quatro reais e cinquenta e seis centavos)
                    dados_ciclo['valor_total_exequentes'] = f"{dados_ciclo['valor']} ({dados_ciclo['valor_extenso']})"
                    
                    if dados_ciclo.get('data_transito_julgado'):
                        dados_ciclo['data_transito_extenso'] = utils.data_por_extenso(dados_ciclo['data_transito_julgado'])
                    
                    documentos_gerados = [] 
                    substabelecimento_pdf = None 
                    
                    # Geração de Docs
                    continuar_gerando = True
                    while continuar_gerando:
                        tipo_doc = interface.selecionar_tipo_documento()
                        if tipo_doc:
                            output_docx = file_manager.pasta_processados / f"{str(autores_sel[0]).split()[0]}_{tipo_doc}.docx"
                            if not WordAutomation().preencher_documento_docx(config.TEMPLATES_DIR / f"{tipo_doc}.docx", dados_ciclo, output_docx):
                                logging.warning(f"Falha ao preencher documento {tipo_doc}")
                            else:
                                try:
                                    os.startfile(str(output_docx))
                                except Exception as e_open:
                                    logging.warning(f"Nao foi possivel abrir o docx: {e_open}")
                                if not interface.confirmar_documento_gerado(output_docx):
                                    restart_required = True
                                    break
                                documentos_gerados.append(output_docx)
                                output_pdf = file_manager.pasta_processados / f"{output_docx.stem}.pdf"
                                if WordAutomation().converter_docx_para_pdf(output_docx, output_pdf):
                                    if "Substabelecimento" in tipo_doc:
                                        substabelecimento_pdf = output_pdf
                        continuar_gerando = interface.mostrar_confirmacao("Gerar Outro?", "Deseja gerar outro?")

                    if restart_required: break
                    
                    # PETICIONAMENTO
                    if interface.mostrar_confirmacao("Peticionamento", f"Iniciar peticionamento para {len(autores_sel)} autor(es)?"):
                        def thread_pet():
                            nonlocal lista_pendentes
                            logging.info("🤖 Iniciando thread de peticionamento automático...")
                            try:
                                scraper_pet = TribunalScraper(numero_processo)
                                scraper_pet.iniciar_navegador(headless=False)
                                scraper_pet.acessar_tribunal()
                                pet = PeticionamentoEletronico(scraper_pet.page)
                                if pet.navegar_para_peticionamento_intermediaria():
                                    num_alvo = dados_validados.get('cumprimento_sentenca') or numero_processo
                                    if pet.preencher_dados_processo(num_alvo, dados_validados.get('cumprimento_sentenca')):
                                         soma_val = sum(utils.parse_currency(dados_validados.get(f"valor_unitario_{a}", 0)) for a in autores_sel)
                                         total_float = soma_val if soma_val > 0 else utils.parse_currency(dados_validados.get('valor', 0))
                                         
                                         # USAR SELEÇÃO DO ESPELHO
                                         codigo_pet = "1265" if dados_validados.get('tipo_requisitorio') == "PRECATÓRIO" else "1266"
                                         
                                         if pet.preencher_dados_classificacao(codigo_pet):
                                              if pet.abrir_dados_suplementares():
                                                  pet.preencher_natureza_e_valor(total_float, data_ajuizamento=dados_validados.get('data_protocolo'), 
                                                                               data_transito_julgado=dados_validados.get('data_transito_julgado'),
                                                                               teve_impugnacao=teve_impugnacao_geral,
                                                                               entidade=dados_validados.get('entidade_devedora', 'FAZENDA'))
                                                  
                                                  # Busca documento com "PETICAO" no nome; se não encontrar,
                                                  # usa o primeiro documento gerado (ex: Substabelecimento)
                                                  # como peça principal do upload (posição 01).
                                                  pet_p = next((file_manager.pasta_processados/f"{d.stem}.pdf" for d in documentos_gerados if "PETICAO" in d.name.upper()), None)
                                                  if not pet_p and documentos_gerados:
                                                      primeiro_doc = documentos_gerados[0]
                                                      candidato = file_manager.pasta_processados / f"{primeiro_doc.stem}.pdf"
                                                      if candidato.exists():
                                                          pet_p = candidato
                                                          logging.info(f"📄 Usando '{primeiro_doc.name}' como petição principal (01) no upload.")
                                                  
                                                  arquivos = file_manager.preparar_pasta_upload(pet_p, autores_selecionados=autores_sel)
                                                  
                                                  if arquivos and pet.fazer_upload_documentos(arquivos):
                                                      pet.categorizar_documentos_upload(autores_sel)
                                                      if pet.adicionar_partes_polo_ativo(autores_sel):
                                                          pet.vincular_documentos_partes_lote(autores_sel)
                                                          for a in autores_sel:
                                                              pet.preencher_valores_individualizados(
                                                                  data_nascimento=dados_validados.get('data_nascimento'), 
                                                                  data_base=dados_validados.get('data_base'), 
                                                                  valor_individual=total_float/len(autores_sel),
                                                                  banco=dados_validados.get('banco', '001'),
                                                                  agencia=dados_validados.get('agencia', '8058'),
                                                                  conta_completa=dados_validados.get('conta_corrente', '262-3')
                                                              )
                                                          if pet.confirmar_informacoes_gerais() and pet.finalizar_para_protocolar():
                                                              # FASE 6.3: Arquivar documentos após sucesso
                                                              file_manager.arquivar_peticionados(autores_sel)
                                                              lista_pendentes[:] = [x for x in lista_pendentes if x not in autores_sel]
                            except Exception as e:
                                logging.error(f"Erro na thread de peticionamento: {e}", exc_info=True)
                            finally:
                                try:
                                    if 'scraper_pet' in locals() and scraper_pet:
                                        logging.info("🧹 Fechando navegador do peticionamento...")
                                        scraper_pet.fechar_navegador()
                                except Exception as e_close:
                                    logging.warning(f"Erro ao fechar navegador do peticionamento: {e_close}")
                                done_event.set()

                        done_event = threading.Event()
                        threading.Thread(target=thread_pet, daemon=True).start()
                        
                        # BUG 6 FIX: Usar self.after() polling em vez de while/sleep
                        # Evita deadlock, alto CPU e engolimento de excecoes
                        def _aguardar_pet():
                            if not done_event.is_set():
                                try:
                                    interface.update_idletasks()
                                except Exception:
                                    pass
                                interface.after(100, _aguardar_pet)
                        interface.after(100, _aguardar_pet)

                if restart_required: continue
                break 

            if interface.mostrar_confirmacao("Fim", "Deseja realizar nova petição?"): interface.reiniciar_sistema = True; interface.quit()
            else: interface.quit()
        except Exception as e: 
            logging.error(f"Erro fatal no processamento: {e}", exc_info=True)
            interface.mostrar_erro("Erro", str(e)); interface.quit()
    except Exception as e: 
        logging.error(f"Erro externo no processamento: {e}", exc_info=True)
        interface.mostrar_erro("Erro", str(e))
    finally:
        if scraper:
            try:
                logging.info("🧹 Fechando navegador do scraper principal...")
                scraper.fechar_navegador()
            except Exception as e_close:
                logging.warning(f"Erro ao fechar navegador: {e_close}")

if __name__ == "__main__": main()
