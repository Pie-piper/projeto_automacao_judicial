from playwright.sync_api import Page, expect
from classes.selectors import Selectors
import logging
import time
import re
from pathlib import Path
from typing import Optional
from classes.human_helper import HumanHelper
from classes.exceptions import (
    TribunalException, 
    PeticionamentoException, 
    DocumentoInvalidoException,
    PortalIndisponivelException
)
from typing import Dict, Any, List

class PeticionamentoEletronico:
    """
    Controlador do fluxo de peticionamento eletrônico no portal e-SAJ.
    Gerencia a navegação, preenchimento de formulários, inclusão de partes
    e upload de documentos.
    """
    def __init__(self, page: Page):
        self.page = page
        self.logger = logging.getLogger("PeticionamentoEletronico")
        self.screenshots_dir = Path("screenshots_erro")
        self.screenshots_dir.mkdir(exist_ok=True)

    def capturar_screenshot(self, nome_erro: str) -> None:
        """
        Captura um screenshot da tela atual para fins de diagnóstico.
        
        Args:
            nome_erro: Identificador textual para o arquivo de imagem.
        """
        try:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            caminho = self.screenshots_dir / f"peticionamento_{nome_erro}_{timestamp}.png"
            self.page.screenshot(path=str(caminho), full_page=True)
            self.logger.info(f"📸 Screenshot de erro salvo em: {caminho}")
        except Exception as e:
            self.logger.error(f"Erro ao capturar screenshot: {e}")

    def _verificar_recuperar_rota(self) -> bool:
        """
        Verifica se a página foi redirecionada inesperadamente para o painel (tarefas-adv)
        ou se o SPA congelou no painel mesmo com a URL alterada ("SPA Ghosting").
        """
        try:
            url_atual = self.page.url.lower()
            
            # Caso 1: A URL mostra explicitamente que o robô caiu
            caiu_para_painel = "tarefas-adv/pet" in url_atual and "novo" not in url_atual
            
            # Caso 2: SPA Ghosting (URL certa, mas a tela visualmente presa no Painel do Advogado)
            tela_travada_no_painel = False
            if "petpgreq" in url_atual or "intermediaria" in url_atual:
                # Se o logo "Painel do advogado" estiver visível E não tivermos o formulário
                if self.page.locator("text='Painel do advogado'").first.is_visible(timeout=1000) and self.page.locator("text='Peticionamento'").count() > 0:
                    tela_travada_no_painel = True

            if caiu_para_painel or tela_travada_no_painel:
                self.logger.warning("🚨 Desalinhamento Detectado (Queda de Sessão ou SPA Ghosting preendendo no Painel).")
                
                if tela_travada_no_painel:
                     self.logger.info("Forçando F5 (Reload) para o e-SAJ renderizar o formulário...")
                     self.page.reload(wait_until="networkidle")
                     time.sleep(3)
                     if not self.page.locator("text='Painel do advogado'").first.is_visible():
                         self.logger.info("A tela de peticionamento foi destravada!")
                         return True # Foi resolvido com reload
                
                # Se ainda estiver ruim ou já caiu explícito, refaz o fluxo do zero pelo menu
                self.logger.info("Retomando interação obrigatória via menu lateral...")
                self.page.keyboard.press("Escape")
                time.sleep(1)
                return self.navegar_para_peticionamento_intermediaria()
                
        except Exception as e:
            self.logger.warning(f"Erro ao verificar rota: {e}")
        return False

    def navegar_para_peticionamento_intermediaria(self) -> bool:
        """
        Navega até a tela de peticionamento intermediário de 1º Grau via menu lateral.
        Esta abordagem é obrigatória para evitar detecção de robôs por navegação direta.

        Returns:
            True se a navegação foi bem-sucedida.
            
        Raises:
            PortalIndisponivelException: Se o menu não carregar ou elementos estiverem ausentes.
        """
        try:
            self.logger.info("Iniciando navegação (Interação via Menu Lateral)...")
            
            # Ancoragem no Painel do Advogado
            if "tarefas-adv/pet" not in self.page.url:
                self.logger.info("Acessando root do Painel do Advogado...")
                self.page.goto("https://esaj.tjsp.jus.br/tarefas-adv/pet/", wait_until="networkidle")
                time.sleep(2)

            # 1. Menu Hambúrguer
            menu_btn = self.page.locator("span.glyph-hamburger").first
            menu_btn.wait_for(state="visible", timeout=10000)
            menu_btn.click()
            time.sleep(1)

            # 2. Peticionamento Eletrônico
            self.page.locator("button.aside-nav__main-menu__list__item__link", 
                              has_text="Peticionamento Eletrônico").first.click()
            time.sleep(1)

            # 3. 1º Grau
            self.page.locator("button.aside-nav__main-menu__list__item__link", 
                              has_text="Peticionamento Eletrônico de 1º Grau").first.click()
            time.sleep(1)

            # 4. Requisitórios
            self.page.locator("a.aside-nav__main-menu__list__item__link", 
                              has_text=re.compile(r"Peticionamento de intermediaria de 1º Grau Requisitórios", re.IGNORECASE)).first.click()
            
            # 5. Validação de URL
            self.page.wait_for_url(re.compile(r".*(petpgreq|intermediaria|cadastro).*"), timeout=20000)
            self.logger.info(f"✅ Navegação concluída: {self.page.url}")
            return True
            
        except Exception as nav_err:
            self.capturar_screenshot("erro_navegacao_menu")
            raise PortalIndisponivelException(f"Falha na navegação via menu: {nav_err}")

    def preencher_dados_processo(self, numero_processo: str, numero_cumprimento: Optional[str] = None, tentativas: int = 0) -> bool:
        """
        Lida com o modal inicial e preenche o número do processo com maior estabilidade.
        
        Args:
            numero_processo: O número do processo alvo.
            tentativas: Contador interno de recuperação recursiva.
            
        Returns:
            True se for bem-sucedido.
            
        Raises:
            PeticionamentoException: Se esgotar as tentativas de preenchimento.
        """
        if tentativas > 2:
            self.logger.error("❌ Limite de tentativas de recuperação atingido no preenchimento do processo.")
            raise PeticionamentoException("Preenchimento do Processo", "Limite de retentativas atingido ao referenciar processo.")

        try:
            self.logger.info("Tratando modais e preenchendo processo...")
            
            HumanHelper.esperar_humano(1.0, 2.0)

            # --- VERIFICAÇÃO DE REDIRECIONAMENTO ANTES DE MEXER NA TELA ---
            if self._verificar_recuperar_rota():
                self.logger.info("🔄 Retomando preenchimento após queda (início preencher_dados_processo)...")
                return self.preencher_dados_processo(numero_processo, numero_cumprimento, tentativas + 1)

            # 5. Tratamento de Modais Bloqueantes (Ex: "INSTALAR PLUG-IN" do Web Signer)
            try:
                self.logger.info("Aguardando possível carregamento do modal 'INSTALAR PLUG-IN' (até 8s)...")
                # Modal customizado chato: "INSTALAR PLUG-IN"
                try:
                    # Esperamos ativamente que o modal apareça. Se no prazo ele não renderizar, ele não aparecerá mais.
                    plugin_modal = self.page.locator("text='INSTALAR PLUG-IN'").first
                    plugin_modal.wait_for(state="visible", timeout=8000)
                    
                    self.logger.info("Modal 'INSTALAR PLUG-IN' detectado! Tentando fechar (Cancelar)...")
                    btn_cancelar_plugin = self.page.locator("div").filter(has=self.page.locator("text='INSTALAR PLUG-IN'")).locator("button", has_text="Cancelar").last
                    if btn_cancelar_plugin.is_visible(timeout=2000):
                        btn_cancelar_plugin.click()
                        self.logger.info("Botão Cancelar clicado com sucesso.")
                    else:
                        self.page.keyboard.press("Escape")
                        self.logger.info("Fechado via ESC.")
                except Exception:
                    self.logger.info("Nenhum modal 'INSTALAR PLUG-IN' foi exibido neste carregamento.")

                # Tratamento auxiliar de Modais nativos (Role="dialog")
                try:
                    modal_cancel = self.page.locator(Selectors.BOTAO_CANCELAR_MODAL_FORM)
                    if modal_cancel.count() > 0 and modal_cancel.first.is_visible(timeout=1000):
                        modal_cancel.first.click()
                        self.logger.info("Modal genérico fechado.")
                except Exception:
                    pass

            except Exception as e_modal:
                self.logger.warning(f"Aviso ao tratar modais: {e_modal}")

            HumanHelper.esperar_humano(1.0, 2.0)

            # Passo A: Clicar em "Informar" (IDs: #botaoEditarDadosBasicos ou fallback textual)
            self.logger.info("Buscando botão para informar/editar dados do processo...")
            # Aguarda um pouco para garantir que a página "hidratou" (JS carregado)
            time.sleep(3)
            self.capturar_screenshot("antes_de_informar")
            
            # Prioridade para o seletor nativo data-testid que o usuário forneceu
            btn_selectors = [
                "[data-testid='button-div-processo-open']",
                Selectors.BOTAO_INFORMAR_PROCESSO_NATIVE,
                Selectors.BOTAO_INFORMAR_PROCESSO, 
                "button:has-text('Informar')", 
                "div[role='button']:has-text('Informar')",
                "span:has-text('Informar')"
            ]
            
            botao_clicado = False
            for selector in btn_selectors:
                btn = self.page.locator(selector).first
                if btn.is_visible(timeout=2000):
                    self.logger.info(f"Clicando no botão abrir/editar processo (seletor: {selector})...")
                    # No novo e-SAJ, às vezes o clique falha se for muito rápido, então movemos o mouse
                    HumanHelper.mover_mouse_e_clicar(self.page, btn)
                    time.sleep(2)
                    self.capturar_screenshot("apos_clique_informar")
                    botao_clicado = True
                    break
            
            if not botao_clicado:
                 self.logger.warning("Nenhum botão de abertura (Informar) visível. Trocando estratégia para clique por texto...")
                 try:
                     # Força um clique genérico em qualquer lugar que tenha a palavra "Informar" e um ícone de edição (ou o bloco de processo)
                     texto_informar = self.page.locator("text='Informar'").first
                     if texto_informar.is_visible(timeout=2000):
                         texto_informar.click(force=True)
                         botao_clicado = True
                         time.sleep(2)
                 except Exception:
                    pass

            # Aguardar campo estar habilitado/visível
            campo_proc = self.page.locator(Selectors.CAMPO_NUMERO_PROCESSO)
            try:
                campo_proc.wait_for(state="visible", timeout=5000)
            except Exception:
                self.logger.warning("Campo de número do processo não apareceu. Tentando clicar no lápis/editar final...")
                # Fallback final: procurar qualquer ícone de edição (lápis) no bloco de processo
                any_edit = self.page.locator(".glyph-edit").first
                if any_edit.is_visible(timeout=2000):
                    any_edit.click()
                    campo_proc.wait_for(state="visible", timeout=3000)

            HumanHelper.esperar_humano(1.0, 2.0)
            
            # Passo B: Preencher Número do Processo
            # Máscaras de React/MUI do e-SAJ frequentemente conflitam com o .fill() do Playwright
            self.logger.info(f"Preenchendo campo de processo (digitando pausadamente) com {numero_processo}")
            campo_proc.click(force=True)
            self.page.keyboard.press("Control+A")
            self.page.keyboard.press("Backspace")
            time.sleep(0.5)
            
            # Na maioria das máscaras web, extrair os números e deixá-los preencher sozinhos é o mais seguro
            numero_limpo = re.sub(r'\D', '', numero_processo)
            self.page.keyboard.type(numero_limpo, delay=50)
            
            time.sleep(1)
            self.page.keyboard.press("Tab") # Forçar disparo da busca de autos
            
            HumanHelper.esperar_humano(2.0, 4.0)
            
            # --- VERIFICAÇÃO DE REDIRECIONAMENTO APÓS BUSCA DE PROCESSO (MAIOR RISCO DE ERRO DO ESAJ) ---
            if self._verificar_recuperar_rota():
                self.logger.info("🔄 Retomando preenchimento após queda (durante a busca do processo no e-SAJ)...")
                return self.preencher_dados_processo(numero_processo, numero_cumprimento, tentativas + 1)
            
            # --- MODAL: SELECIONE O PROCESSO (Quando digita número do cumprimento direto) ---
            try:
                modal_selecione = self.page.locator("h2, span, div").filter(has_text="SELECIONE O PROCESSO")
                if modal_selecione.first.is_visible(timeout=5000):
                    self.logger.info("Modal 'SELECIONE O PROCESSO' detectado.")
                    
                    radio_processo = self.page.locator("input[type='radio']").first
                    if radio_processo.count() > 0:
                        radio_processo.click(force=True)
                        HumanHelper.esperar_humano(0.5, 1.0)
                        
                        btn_selecionar = self.page.locator("button[data-testid='modal-processos-dependentes-button-select'], button:has-text('Selecionar')").first
                        if btn_selecionar.count() > 0:
                            btn_selecionar.click(force=True)
                            self.logger.info("Modal 'SELECIONE O PROCESSO' confirmado.")
                            HumanHelper.esperar_humano(1.0, 2.0)
            except Exception as e_modal_selecione:
                self.logger.warning(f"Erro ao tratar modal Selecione o Processo: {e_modal_selecione}")

            # --- MODAL: CUMPRIMENTO DE SENTENÇA (Quando digita autos principais) ---
            try:
                # O usuário disse: h2 "Cumprimento de sentença", radio value="N", botão span "Confirmar"
                modal_cumprimento = self.page.locator("h2, span, p").filter(has_text=re.compile(r"Cumprimento de senten.a", re.IGNORECASE))
                if modal_cumprimento.first.is_visible(timeout=5000) or self.page.locator("text='Existe cumprimento de sentença cadastrado para esse credor?'").is_visible():
                    self.logger.info("Modal 'Cumprimento de sentença' detectado.")
                    
                    if numero_cumprimento and numero_processo != numero_cumprimento:
                        # Se temos o cumprimento, clicar em SIM
                        self.logger.info("Temos número de cumprimento em mãos, selecionando 'Sim'.")
                        radio_sim = self.page.locator("input[type='radio'][value='S']")
                        if radio_sim.count() > 0:
                            radio_sim.first.click(force=True)
                            HumanHelper.esperar_humano(0.5, 1.0)
                            
                            # Preenche o número do cumprimento
                            campo_cump = self.page.locator("#processo-cumprimento-sentenca, input[name='processo-cumprimento-sentenca'], input[data-testid='input-processo-cumprimento-sentenca-numero']")
                            if campo_cump.count() > 0:
                                campo_cump.first.click(force=True)
                                cump_limpo = re.sub(r'\D', '', numero_cumprimento)
                                self.page.keyboard.type(cump_limpo, delay=50)
                                HumanHelper.esperar_humano(1.0, 1.5)
                            
                            # Confirmar
                            btn_confirmar = self.page.locator("button, span").filter(has_text="Confirmar")
                            if btn_confirmar.count() > 0:
                                btn_confirmar.first.click(force=True)
                                self.logger.info("Modal 'Cumprimento de Sentença' confirmado com SIM.")
                                HumanHelper.esperar_humano(1.0, 2.0)
                    else:
                        self.logger.info("Não temos número de cumprimento, selecionando 'Não'.")
                        radio_nao = self.page.locator("input[type='radio'][value='N']")
                        
                        if radio_nao.count() > 0:
                            radio_nao.first.click(force=True)
                            HumanHelper.esperar_humano(0.5, 1.0)
                            
                            btn_confirmar = self.page.locator("button, span").filter(has_text="Confirmar")
                            if btn_confirmar.count() > 0:
                                btn_confirmar.first.click(force=True)
                                self.logger.info("Modal 'Cumprimento de sentença' confirmado com NÃO.")
                                HumanHelper.esperar_humano(1.0, 2.0)
            except Exception as e_modal:
                self.logger.warning(f"Erro ao tratar modal Cumprimento de Sentença: {e_modal}")
            
            # Verificar se fomos para o login (Indica falha crítica de sessão)
            if "login" in self.page.url:
                self.logger.error("❌ Sessão interrompida após preencher processo.")
                raise PortalIndisponivelException("Sessão expirada ou interrompida durante o preenchimento do processo.")

            return True

        except Exception as e:
            if self._verificar_recuperar_rota():
                self.logger.info("🔄 Queda de tela detectada no tratamento de erro do Processo! Re-tentando do menu...")
                return self.preencher_dados_processo(numero_processo, numero_cumprimento, tentativas + 1)
                
            self.logger.error(f"Erro ao preencher dados do processo: {e}")
            self.capturar_screenshot("preencher_dados_processo")
            raise PeticionamentoException("Preenchimento do Processo", str(e))

    def preencher_dados_classificacao(self, tipo_peticao: str = "1266", tentativas: int = 0) -> bool:
        """
        Realiza apenas o fluxo de Classificação.
        
        Args:
            tipo_peticao: O código ou nome do tipo de petição.
            tentativas: Contador interno.
            
        Raises:
            PeticionamentoException: Se a etapa falhar após as tentativas.
        """
        if tentativas > 2:
             self.logger.error("❌ Limite de tentativas de recuperação atingido na classificação.")
             raise PeticionamentoException("Classificação", "Falha crítica após limite de tentativas.")

        try:
            self.logger.info("Iniciando preenchimento da Classificação (Simplificado)...")
            
            if self._verificar_recuperar_rota():
                self.logger.info("🔄 Retomando preenchimento após queda (preencher_dados_classificacao)...")
                return self.preencher_dados_classificacao(tipo_peticao, tentativas + 1)
            
            HumanHelper.esperar_humano(1.0, 2.0)
            
            # 1. Clicar em Classificar
            self.logger.info(f"Tentando clicar no botão Classificar: {Selectors.BOTAO_CLASSIFICAR}")
            botao_class = self.page.locator(Selectors.BOTAO_CLASSIFICAR)
            botao_class.wait_for(state='visible', timeout=10000)
            botao_class.scroll_into_view_if_needed()
            
            HumanHelper.mover_mouse_e_clicar(self.page, botao_class)
            HumanHelper.esperar_humano(1.5, 2.5)
            
            # 2. Navegação via Teclado
            self.logger.info(f"Digitando Tipo de Petição via Teclado: {tipo_peticao}")
            self.page.keyboard.press("Tab")
            HumanHelper.esperar_humano(0.3, 0.6)
            self.page.keyboard.type(tipo_peticao, delay=100)
            HumanHelper.esperar_humano(1.2, 1.8)
            self.page.keyboard.press("Enter")
            HumanHelper.esperar_humano(1.0, 1.5)
            
            # 3. Clicar em Confirmar
            self.logger.info("Clicando em Confirmar Classificação...")
            botao_confirmar = self.page.locator(Selectors.BOTAO_CONFIRMAR_TIPO)
            botao_confirmar.wait_for(state='visible', timeout=5000)
            HumanHelper.mover_mouse_e_clicar(self.page, botao_confirmar)

            HumanHelper.esperar_humano(1.5, 3.0)
            return True
            
        except Exception as e:
            if self._verificar_recuperar_rota():
                self.logger.info("🔄 Queda de tela detectada no preenchimento de Classificação! Re-tentando...")
                return self.preencher_dados_classificacao(tipo_peticao, tentativas + 1)
            self.logger.error(f"Erro na etapa de classificação: {e}")
            raise PeticionamentoException("Classificação", str(e))

    def abrir_dados_suplementares(self, tentativas: int = 0) -> bool:
        """
        Clica em Informar para abrir a seção de Dados Suplementares.
        
        Raises:
            PeticionamentoException: Ao exceder tentativas.
        """
        if tentativas > 2:
             self.logger.error("❌ Limite de tentativas de recuperação atingido ao abrir suplementares.")
             raise PeticionamentoException("Abertura Dados Suplementares", "Não foi possível abrir o modal de Dados Suplementares.")

        try:
            self.logger.info("Clicando em Informar (Dados Suplementares)...")
            
            if self._verificar_recuperar_rota():
                self.logger.info("🔄 Retomando preenchimento após queda (abrir_dados_suplementares)...")
                # A classificação já foi feita? Em teoria o e-SAJ salva e abre assim que a URL for reaberta.
                return self.abrir_dados_suplementares(tentativas + 1)

            informar_btns = self.page.locator(Selectors.BOTAO_INFORMAR_SUPLEMENTARES)
            informar_btns.wait_for(state='visible', timeout=10000)
            
            count = informar_btns.count()
            if count > 1:
                self.logger.info(f"Encontrados {count} botões Informar. Clicando no último...")
                HumanHelper.mover_mouse_e_clicar(self.page, informar_btns.last)
            else:
                HumanHelper.mover_mouse_e_clicar(self.page, informar_btns)
                
            HumanHelper.esperar_humano(1.0, 2.0)
            return True
        except Exception as e:
            if self._verificar_recuperar_rota():
                self.logger.info("🔄 Queda de tela detectada ao abrir dados suplementares! Re-tentando...")
                return self.abrir_dados_suplementares(tentativas + 1)
            self.logger.error(f"Erro ao abrir dados suplementares: {e}")
            raise PeticionamentoException("Abertura Dados Suplementares", str(e))

    def fazer_upload_documentos(self, lista_arquivos: List[str], tentativas: int = 0) -> bool:
        """
        Realiza o upload dos documentos PDFs organizados.
        Usa expect_file_chooser para interceptar o diálogo de arquivos do Windows.
        
        Args:
            lista_arquivos: Lista de caminhos absolutos dos PDFs.
            tentativas: Contador interno.
            
        Raises:
            PeticionamentoException: Se falhar após tentativas.
        """
        if tentativas > 1:
             self.logger.error("❌ Limite de tentativas de recuperação atingido no upload.")
             raise PeticionamentoException("Upload de Documentos", "Limite de retentativas atingido ao enviar PDFs.")

        try:
            self.logger.info(f"Iniciando upload de {len(lista_arquivos)} documentos...")
            
            if self._verificar_recuperar_rota():
                self.logger.info("🔄 Retomando upload após queda (fazer_upload_documentos)...")
                return self.fazer_upload_documentos(lista_arquivos, tentativas + 1)
            
            # 1. Preparar para interceptar o diálogo de arquivo
            with self.page.expect_file_chooser() as fc_info:
                botao_upload = self.page.locator(Selectors.BOTAO_SELECIONE_PDF)
                botao_upload.wait_for(state='visible', timeout=10000)
                
                # O clique dispara o diálogo
                self.logger.info("Clicando no botão Selecionar PDF e interceptando diálogo...")
                HumanHelper.mover_mouse_e_clicar(self.page, botao_upload)
            
            file_chooser = fc_info.value
            # 2. Definir os arquivos diretamente (Playwright lida com o 'Abrir' do Windows internamente)
            file_chooser.set_files(lista_arquivos)
            
            self.logger.info("✅ Upload de arquivos concluído com sucesso via FileChooser.")
            HumanHelper.esperar_humano(2, 3)
            
            return True
        except Exception as e:
            if self._verificar_recuperar_rota():
                self.logger.info("🔄 Queda de tela detectada no upload de documentos! Re-tentando...")
                return self.fazer_upload_documentos(lista_arquivos, tentativas + 1)
            self.logger.error(f"Erro ao fazer upload: {e}")
            self.capturar_screenshot("upload_documentos")
            raise PeticionamentoException("Upload de Documentos", str(e))

    def _normalizar_nome(self, nome: str) -> str:
        """
        Normaliza um nome para comparação robusta:
        Remove acentos, converte para minúsculas, remove espaços extras e pontuação.
        Ex: 'DANIELLE' -> 'daniele', 'Daniele Albano' -> 'daniele albano'
        """
        import unicodedata
        if not nome: return ""
        # Decodifica acentos
        n = unicodedata.normalize('NFKD', str(nome)).encode('ASCII', 'ignore').decode('ASCII')
        # Minúsculas e limpeza de caracteres não-alfanuméricos (exceto espaços)
        n = re.sub(r'[^a-zA-Z0-9\s]', '', n.lower())
        # Redução de letras repetidas (danielle -> daniele) - Fallback para variações comuns
        n = re.sub(r'(.)\1+', r'\1', n)
        # Remove espaços extras
        n = " ".join(n.split())
        return n

    def categorizar_documentos_upload(self, autores_selecionados: Optional[List[str]] = None) -> bool:
        """
        Categoriza os documentos iterando por cada linha de upload de forma dinâmica.
        Se o documento contiver o nome de um Requerente específico, vincula apenas a ele.
        """
        try:
            self.logger.info(f"Iniciando categorização dinâmica. Autores: {autores_selecionados}")
            
            # Aguarda o carregamento das linhas de documentos
            self.page.wait_for_selector("[data-testid^='select-tipo-documento-']", timeout=10000)
            time.sleep(2) # Pausa técnica para hidratação final do grid

            # Identifica quantas linhas existem na tela
            todos_selects = self.page.locator("[data-testid^='select-tipo-documento-']")
            total_documentos = todos_selects.count()
            self.logger.info(f"Detectados {total_documentos} documentos para categorizar.")

            # Normalizar autores para match facilitado
            autores_norm = []
            if autores_selecionados:
                for a in autores_selecionados:
                    autores_norm.append({
                        "original": a,
                        "primeiro_nome": self._normalizar_nome(a.split(" ")[0]),
                        "curto": self._normalizar_nome(a[:4]), # Primeiras 4 letras conforme pedido
                        "completo": self._normalizar_nome(a)
                    })

            for i in range(total_documentos):
                try:
                    # Garantir visibilidade e foco na linha
                    selector_container = f"[data-testid='select-tipo-documento-{i}']"
                    container = self.page.locator(selector_container).first
                    
                    if not container.is_visible():
                        container.scroll_into_view_if_needed()
                        time.sleep(0.5)

                    # 1. Identificar Tipo do Documento (Extraído do contexto visual da linha)
                    # Subimos no DOM para capturar o texto de toda a 'linha' do grid que contém o arquivo
                    texto_linha = self.page.evaluate(fr"""(i) => {{
                        let el = document.querySelector(`[data-testid='select-tipo-documento-${{i}}']`);
                        if (!el) return "";
                        // Sobe até encontrar o container que agrupa as colunas (ou limite de 5 níveis)
                        let cur = el;
                        for (let j=0; j<5; j++) {{
                            if (!cur.parentElement) break;
                            cur = cur.parentElement;
                            let t = cur.innerText.toUpperCase();
                            // Se achou o nome com extensão ou padrão de numeração, este é o container da linha
                            if (t.includes(".PDF") || t.includes(".DOC") || /\d+ -/.test(t)) break;
                        }}
                        return cur.innerText.toUpperCase();
                    }}""", i)
                    
                    if not texto_linha:
                        # Fallback de extração de texto via seletor Playwright
                        linha = container.locator("xpath=ancestor::div[contains(@class,'MuiGrid-container')]").first
                        if linha.count() == 0:
                             linha = container.locator("xpath=../../..").first
                        texto_linha = str(linha.inner_text().upper()) if linha.count() > 0 else ""
                    
                    self.logger.info(f"🔍 Linha {i+1} - Texto Capturado: '{texto_linha.replace('\n', ' ')}'")

                    # Classificação baseada em Regex para maior flexibilidade
                    tipo_doc = "Outros Documentos" 
                    if re.search(r"PETI", texto_linha): 
                        tipo_doc = "Petição"
                    elif re.search(r"PROCURA|SUBST", texto_linha): 
                        tipo_doc = "Procuração"
                    elif re.search(r"PLANILHA|CALCULO", texto_linha): 
                        tipo_doc = "Planilha de Cálculos"
                    elif re.search(r"DECIS|SENTEN|HOMO", texto_linha): 
                        tipo_doc = "Cópias Extraídas de Outros Processos"
                    elif re.search(r"CONTRA", texto_linha): 
                        tipo_doc = "Contrato"
                    
                    self.logger.info(f"📌 Classificado como: {tipo_doc}")

                    # Preencher Tipo do Documento
                    container.click(force=True)
                    time.sleep(1)
                    input_tipo = self.page.locator(f"{Selectors.DOC_TIPO_INPUT_PREFIX}{i}").first
                    input_tipo.fill(tipo_doc)
                    time.sleep(0.8)
                    
                    # Selecionar no Popover
                    opcao = self.page.locator(f"li[role='option']:has-text('{tipo_doc}')").first
                    if opcao.is_visible(timeout=2000):
                        opcao.click()
                    else:
                        self.page.keyboard.press("Enter")
                    time.sleep(0.5)

                    # 2. Preencher Partes do Documento
                    selector_parte_container = f"[data-testid='select-parte-documento-{i}']"
                    parte_container = self.page.locator(selector_parte_container).first
                    
                    if parte_container.is_visible(timeout=2000):
                        parte_container.click(force=True)
                        time.sleep(1)
                        
                        if autores_norm:
                            autor_especifico = None
                            # Se for Planilha, Procuração ou Contrato, tentamos match pelo nome no arquivo
                            if tipo_doc in ["Planilha de Cálculos", "Procuração", "Contrato"]:
                                texto_norm_linha = self._normalizar_nome(texto_linha)
                                for a_info in autores_norm:
                                    if a_info["primeiro_nome"] in texto_norm_linha or a_info["curto"] in texto_norm_linha:
                                        autor_especifico = a_info["original"]
                                        break
                                        
                            autores_vincular = [autor_especifico] if autor_especifico else autores_selecionados # type: ignore
                            
                            for autor in autores_vincular:
                                # Digitar apenas as primeiras 4 letras conforme pedido pelo usuário
                                input_parte = self.page.locator(f"{Selectors.DOC_PARTE_INPUT_PREFIX}{i}").first
                                prefixo_nome = autor[:4]
                                self.logger.info(f"Vinculando {autor} (digitando '{prefixo_nome}')...")
                                input_parte.fill(prefixo_nome) 
                                time.sleep(1)
                                
                                # Match na opção que aparece
                                autor_norm_val = self._normalizar_nome(autor)
                                options = self.page.locator("li[role='option']")
                                found = False
                                for j in range(options.count()):
                                    opt = options.nth(j)
                                    if autor_norm_val in self._normalizar_nome(opt.inner_text()):
                                        opt.click()
                                        found = True
                                        break
                                
                                if not found:
                                    self.page.keyboard.press("Enter")
                                time.sleep(0.5)
                        else:
                            # Fallback genérico: pega o primeiro que aparecer
                            self.page.keyboard.press("ArrowDown")
                            self.page.keyboard.press("Enter")
                            
                        # Garantir que fechou o select de partes
                        self.page.keyboard.press("Escape")
                        time.sleep(1)

                except Exception as row_err:
                    self.logger.warning(f"⚠️ Erro ao processar linha {i}: {row_err}")
                    # Tenta continuar para a próxima linha
                    continue

            # 3. Finalizar a seção de documentos clicando em 'Confirmar' no painel lateral/inferior
            self.logger.info("Tentando localizar botão Confirmar da seção de documentos...")
            btn_confirmar_docs = self.page.locator("button:has-text('Confirmar'), span:has-text('Confirmar')").last
            if btn_confirmar_docs.is_visible(timeout=3000):
                self.logger.info("Clicando em Confirmar (Seção de Documentos)...")
                btn_confirmar_docs.click(force=True)
                time.sleep(2)

            self.logger.info("✅ Categorização de documentos finalizada.")
            return True
        except Exception as e:
            self.logger.error(f"Erro na etapa de classificação: {e}")
            self.capturar_screenshot("classificacao_falha")
            raise PeticionamentoException("Classificação de Peças", str(e))

    def adicionar_partes_polo_ativo(self, autores_selecionados: List[str]) -> bool:
        """
        Adiciona os autores selecionados ao Polo Ativo no sistema e-SAJ,
        pesquisando pelos IDs recomendados (0 a 5) e clicando em "Incluir esta parte".
        
        Args:
            autores_selecionados: Nomes a serem incluídos.
            
        Returns:
            True se finalizada a etapa de checagem.
        """
        try:
            if not autores_selecionados: return True
            self.logger.info(f"Adicionando {len(autores_selecionados)} partes ao Polo Ativo...")
            
            # Normalizar nomes selecionados para comparação
            autores_alvo = [self._normalizar_nome(a) for a in autores_selecionados]
            
            # 1. Tentar encontrar os botões sugeridos pelo usuário (IDs 0 a 5)
            # e-SAJ costuma renderizar 'incluir-parte-0', 'incluir-parte-1', etc.
            partes_incluidas_count = 0
            
            # Aumentamos o range de segurança (até 8) e verificamos na tela
            for i in range(8):
                try:
                    btn_id = f"button[data-testid='incluir-parte-{i}']"
                    btn = self.page.locator(btn_id).first
                    
                    if btn.count() > 0 and btn.is_visible():
                        # Antes de clicar, verificar se o nome nesta caixa é o que queremos
                        # O nome costuma estar em um <p> dentro da div pai do botão
                        container = btn.locator("xpath=ancestor::div[1]").first
                        texto_caixa_norm = self._normalizar_nome(container.inner_text())
                        
                        alvo_encontrado = None
                        for original, norm in zip(autores_selecionados, autores_alvo):
                            pa = norm.split()
                            pp = texto_caixa_norm.split()
                            match = (norm in texto_caixa_norm or texto_caixa_norm in norm)
                            if not match and len(pa) >= 1 and len(pp) >= 1 and pa[0] == pp[0]:
                                match = True
                            if match:
                                alvo_encontrado = original
                                break
                        
                        if alvo_encontrado:
                            self.logger.info(f"Clicando para incluir ({btn_id}): {alvo_encontrado}")
                            btn.click(force=True)
                            partes_incluidas_count += 1
                            # Espera para o e-SAJ processar e liberar os links de valores
                            time.sleep(2)
                        else:
                            self.logger.debug(f"ID {i} ignorado (nome '{texto_caixa_norm[:20]}' não selecionado).")
                    
                except Exception as e_id:
                    self.logger.debug(f"Erro ao verificar ID {i}: {e_id}")
                    continue

            # 2. Fallback: Busca genérica em caixas sugeridas (caso o ID não seja linear)
            if partes_incluidas_count < len(autores_selecionados):
                self.logger.info("Executando fallback para buscar partes sugeridas fora da ordem de ID linear...")
                caixas_partes = self.page.locator("[data-testid='partes-sugeridas'] > div")
                count = caixas_partes.count()
                
                for i in range(count):
                    caixa = caixas_partes.nth(i)
                    texto_caixa_norm = self._normalizar_nome(caixa.inner_text())
                    
                    alvo_encontrado = None
                    for original, norm in zip(autores_selecionados, autores_alvo):
                        pa = norm.split()
                        pp = texto_caixa_norm.split()
                        match = (norm in texto_caixa_norm or texto_caixa_norm in norm)
                        if not match and len(pa) >= 1 and len(pp) >= 1 and pa[0] == pp[0]:
                            match = True
                        if match:
                           alvo_encontrado = original
                           break
                    
                    if alvo_encontrado:
                        btn = caixa.locator("button, p").filter(has_text=re.compile(r"Incluir|Incluir esta parte", re.IGNORECASE)).first
                        if btn.count() > 0 and btn.is_visible():
                            self.logger.info(f"Clicando para incluir (Fallback): {alvo_encontrado}")
                            btn.click(force=True)
                            partes_incluidas_count += 1
                            time.sleep(2)

            self.logger.info(f"✅ Polo Ativo processado. {partes_incluidas_count} partes incluídas.")
            return True
        except Exception as e:
            self.logger.error(f"Erro no Polo Ativo: {e}")
            self.capturar_screenshot("polo_ativo")
            return False

    def preencher_natureza_e_valor(self, valor, data_ajuizamento: Optional[str] = None, data_transito_julgado: Optional[str] = None, teve_impugnacao: bool = False, entidade: str = "FAZENDA DO ESTADO DE SÃO PAULO"):
        """
        Preenche o campo de entidade devedora, natureza e o valor nos dados suplementares 
        seguindo a lógica de navegação por teclado (5 Tabs). 
        Preenche também os novos campos de datas (Ajuizamento, Transito) e Impugnação.
        """
        try:
            self.logger.info(f"Iniciando preenchimento de dados suplementares: R$ {valor} | Entidade: {entidade}")
            
            # O sistema TJSP abre o modal de Dados Suplementares ao clicar em Informar.
            # O usuário informou que devemos apertar Tab 5 vezes para chegar no campo Entidade Devedora.
            
            self.logger.info("Executando 5 Tabs para chegar na Entidade Devedora...")
            for _ in range(5):
                self.page.keyboard.press("Tab")
                HumanHelper.esperar_humano(0.2, 0.4)
            
            # 1. Preencher Entidade Devedora
            self.logger.info(f"Digitando Entidade Devedora: {entidade}")
            self.page.keyboard.type(entidade, delay=100)
            HumanHelper.esperar_humano(0.8, 1.2)
            self.page.keyboard.press("Enter")
            HumanHelper.esperar_humano(0.5, 0.8)
            
            # 2. Navegação para Natureza
            self.logger.info("Navegando para campo Natureza...")
            self.page.keyboard.press("Tab")
            HumanHelper.esperar_humano(0.3, 0.6)
            
            # Digitar 'alimentar' e Enter
            self.page.keyboard.type("alimentar", delay=100)
            HumanHelper.esperar_humano(0.5, 0.8)
            self.page.keyboard.press("Enter")
            HumanHelper.esperar_humano(0.8, 1.2)
            
            # 3. Navegação para Valor
            # "pressionar tab duas vezes e preencher com o valor da planilha calculo"
            self.logger.info(f"Navegando para campo Valor e preenchendo: {valor}")
            self.page.keyboard.press("Tab")
            HumanHelper.esperar_humano(0.2, 0.4)
            self.page.keyboard.press("Tab")
            HumanHelper.esperar_humano(0.5, 0.8)
            
            # Converter valor para string formatada (ex: 1.234,56)
            valor_str = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            self.page.keyboard.type(valor_str, delay=100)
            HumanHelper.esperar_humano(1.0, 1.5)
            
            # --- NOVOS CAMPOS DADOS SUPLEMENTARES - PROCESSO DE CONHECIMENTO ---
            if data_ajuizamento:
                self.logger.info(f"Preenchendo Data Ajuizamento: {data_ajuizamento}")
                try:
                    campo_ajuizamento = self.page.locator("input[name='data_ajuizamento']").first
                    if campo_ajuizamento.count() == 0:
                        campo_ajuizamento = self.page.locator("#data_ajuizamento").first
                    
                    if campo_ajuizamento.count() > 0:
                        campo_ajuizamento.click(force=True)
                        campo_ajuizamento.fill(data_ajuizamento)
                        HumanHelper.esperar_humano(0.5, 0.8)
                except Exception as e:
                    self.logger.warning(f"Erro ao preencher data_ajuizamento: {e}")

            if data_transito_julgado:
                self.logger.info(f"Preenchendo Data Trânsito Julgado: {data_transito_julgado}")
                try:
                    campo_transito = self.page.locator("input[name='data_transito_julgado']").first
                    if campo_transito.count() == 0:
                        campo_transito = self.page.locator("#data_transito_julgado").first
                    
                    if campo_transito.count() > 0:
                        campo_transito.click(force=True)
                        campo_transito.fill(data_transito_julgado)
                        HumanHelper.esperar_humano(0.5, 0.8)
                except Exception as e:
                    self.logger.warning(f"Erro ao preencher data_transito_julgado: {e}")

            self.logger.info(f"Opostos embargos/impugnação? {'Sim' if teve_impugnacao else 'Não'}")
            try:
                if teve_impugnacao:
                    radio_emb_s = self.page.locator("input[name='embargos_devedor_impugnacao'][value='S']").first
                    if radio_emb_s.count() > 0:
                        radio_emb_s.click(force=True)
                        HumanHelper.esperar_humano(0.5, 1.0)
                        
                        if data_transito_julgado:
                            campo_data_emb = self.page.locator("input[name='data_embargos_devedor']").first
                            if campo_data_emb.count() == 0:
                                campo_data_emb = self.page.locator("#data_embargos_devedor").first
                            if campo_data_emb.count() > 0:
                                campo_data_emb.click(force=True)
                                campo_data_emb.fill(data_transito_julgado)
                                HumanHelper.esperar_humano(0.5, 0.8)
                else:
                    radio_emb_n = self.page.locator("input[name='embargos_devedor_impugnacao'][value='N']").first
                    if radio_emb_n.count() > 0:
                        radio_emb_n.click(force=True)
                        HumanHelper.esperar_humano(0.5, 1.0)
                        
                        if data_transito_julgado:
                            campo_data_decurso = self.page.locator("input[name='data_decurso_prazo']").first
                            if campo_data_decurso.count() == 0:
                                campo_data_decurso = self.page.locator("#data_decurso_prazo").first
                            if campo_data_decurso.count() > 0:
                                campo_data_decurso.click(force=True)
                                campo_data_decurso.fill(data_transito_julgado)
                                HumanHelper.esperar_humano(0.5, 0.8)
            except Exception as e:
                self.logger.warning(f"Erro ao preencher embargos: {e}")

            # --- INDENIZATÓRIO E VALOR INCONTROVERSO ---
            self.logger.info("Ajustando 'Valor Incontroverso' e 'Natureza do Crédito'")
            try:
                incontroverso_nao = self.page.locator("input[value='N'][name*='incontroverso']").first
                if incontroverso_nao.count() > 0:
                    incontroverso_nao.click(force=True)
                    HumanHelper.esperar_humano(0.5, 0.8)
                    
                # <input class="jss234" name="natureza_credito" type="radio" value="I">
                natureza_cred = self.page.locator("input[name='natureza_credito'][value='I']").first
                if natureza_cred.count() > 0:
                    natureza_cred.click(force=True)
                    HumanHelper.esperar_humano(0.5, 0.8)
            except Exception as e_ind:
                self.logger.warning(f"Erro ao ajustar Incontroverso ou Natureza Crédito: {e_ind}")

            # 4. Confirmar
            # "e clicar no botao confirmar Confirmar" (Classe jss278)
            self.logger.info("Clicando em Confirmar Dados Suplementares...")
            botao_confirmar = self.page.locator(Selectors.BOTAO_CONFIRMAR_SUPLEMENTARES)
            botao_confirmar.wait_for(state="visible", timeout=5000)
            HumanHelper.mover_mouse_e_clicar(self.page, botao_confirmar)
            
            HumanHelper.esperar_humano(1.5, 3.0)
            return True
            
        except Exception as e:
            self.logger.error(f"Erro ao preencher natureza e valor: {e}")
            self.capturar_screenshot("natureza_valor")
            return False

    def vincular_documentos_partes_lote(self, autores_selecionados: List[str]) -> bool:
        """
        Retorna ao grid de documentos e vincula os autores selecionados preenchendo o input PARTE.
        Para cada documento, adiciona todos os autores passados localizando-os na lista do react-select.
        """
        try:
            if not autores_selecionados:
                self.logger.info("Nenhuma parte para vincular.")
                return True
                
            self.logger.info(f"Retornando ao grid de documentos para vincular os autores: {autores_selecionados}")
            # Aguarda a tela estabilizar após incluir as partes
            HumanHelper.esperar_humano(3.0, 5.0)
            
            # Tentar garantir que estamos no topo do grid
            self.page.locator("div[data-testid^='div-tipo-documento-0']").first.scroll_into_view_if_needed()
            
            linhas = self.page.locator("div[data-testid^='div-partes-']")
            count = linhas.count()
            self.logger.info(f"Encontrados {count} documentos para vinculação de partes.")
            
            for i in range(count):
                self.logger.info(f"Vinculando partes no documento linha {i}...")
                try:
                    container_parte = self.page.locator(f"div[data-testid='select-partes-{i}']").first
                    if container_parte.is_visible(timeout=2000):
                        container_parte.scroll_into_view_if_needed()
                        
                        # Identificar o tipo do documento (para lógica de quem vincular)
                        container_pai = self.page.locator(f"div[data-testid='div-tipo-documento-{i}']").locator("xpath=ancestor::div[1]").first
                        nome_arquivo = container_pai.inner_text().upper() if container_pai.count() > 0 else ""
                        nome_arquivo_norm = self._normalizar_nome(nome_arquivo)

                        autores_para_vincular = []
                        if "planilha" in nome_arquivo_norm or "peticao" in nome_arquivo_norm or "substabel" in nome_arquivo_norm:
                            autores_para_vincular = autores_selecionados
                        else:
                            dono_encontrado = False
                            for autor in autores_selecionados:
                                parte_nome = self._normalizar_nome(autor)
                                if parte_nome in nome_arquivo_norm or self._normalizar_nome(autor.split(" ")[0]) in nome_arquivo_norm:
                                    autores_para_vincular.append(autor)
                                    dono_encontrado = True
                            if not dono_encontrado:
                                autores_para_vincular = autores_selecionados
                        
                        autores_para_vincular = list(set(autores_para_vincular))
                        
                        for autor in autores_para_vincular:
                            # Utiliza apenas as 4 primeiras letras do nome para evitar problemas de variação (ex: Danielle vs Daniele)
                            primeiro_nome = str(autor).split(" ")[0]
                            nome_pesquisa = primeiro_nome[:4] if len(primeiro_nome) > 4 else primeiro_nome
                            
                            # Clicar no select para ativar a digitação
                            container_parte.click(force=True)
                            HumanHelper.esperar_humano(1.0, 1.5)
                            
                            # Digitar o início do nome
                            self.page.keyboard.type(nome_pesquisa, delay=100)
                            HumanHelper.esperar_humano(1.5, 2.5)
                            
                            # Pressionar Enter para selecionar a parte sugerida pelo dropdown do eSAJ
                            self.page.keyboard.press("Enter")
                            HumanHelper.esperar_humano(0.5, 1.5)
                            
                        # Fechar dropdown "Selecione a opção" caso ele fique aberto (click forçado fora ou ESC)
                        self.page.keyboard.press("Escape")
                        HumanHelper.esperar_humano(0.5, 1.0)
                
                except Exception as row_error:
                    self.logger.warning(f"Erro ao vincular parte na linha {i}: {row_error}")
            
            return True
        except Exception as e:
            self.logger.error(f"Erro na vinculação em lote de documentos a partes: {e}")
            self.capturar_screenshot("vinculacao_documentos")
            return False

    def confirmar_informacoes_gerais(self) -> bool:
        """
        Clica no botão 'Confirmar' no rodapé para validar as informações inseridas.
        Inclui tratamento para overlays (modais) e fallback de clique via JavaScript.
        """
        try:
            self.logger.info("Clicando no botão de confirmação geral (Rodapé)...")
            
            # 1. Aguardar que qualquer fundo de modal (backdrop) desapareça
            try:
                self.page.locator(".modal-backdrop, .overlay").wait_for(state="hidden", timeout=5000)
            except:
                pass # Se não existir, segue em frente
            
            # 2. Lista de seletores possíveis para o botão de confirmação no rodapé
            seletores_confirmar = [
                "button[data-testid='footer-confirmar-1']",
                "button[data-testid='footer-confirmar']",
                "button:has-text('Confirmar')",
                "input[value='Confirmar']", # Suporte para inputs antigos
                ".css-12uqy48", 
                "#pbConfirmar",
                "#btnConfirmar"
            ]
            
            btn_confirmar = None
            for selector in seletores_confirmar:
                loc = self.page.locator(selector).first
                if loc.count() > 0:
                    try:
                        loc.wait_for(state="attached", timeout=2000)
                        btn_confirmar = loc
                        self.logger.info(f"Botão de confirmação localizado via: {selector}")
                        break
                    except:
                        continue
            
            if not btn_confirmar:
                btn_confirmar = self.page.locator("footer button, .footer button").filter(has_text=re.compile(r"Confirmar", re.IGNORECASE)).first
            
            # 3. Tentativa de clique com Scroll
            try:
                btn_confirmar.scroll_into_view_if_needed()
                # Tenta um clique curto (10s)
                btn_confirmar.click(timeout=10000)
                self.logger.info("✅ Clique no rodapé realizado com sucesso via Playwright.")
            except Exception as click_err:
                self.logger.warning(f"⚠️ Falha no clique padrão ({click_err}). Tentando Clique Híbrido (JS)...")
                
                # Fallback: Clique via JavaScript (ignora bloqueios de overlays)
                # O seletor usado aqui é o resolve_selector_do_locator se disponível ou o primeiro seletor que funcionou
                self.page.evaluate("""(selector) => {
                    const btn = document.querySelector(selector) || 
                                Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Confirmar'));
                    if (btn) {
                        btn.scrollIntoView();
                        btn.click();
                        return true;
                    }
                    return false;
                }""", seletores_confirmar[0])
                self.logger.info("✅ Tentativa de clique via JavaScript enviada.")

            # 4. Pequena pausa para o e-SAJ processar
            time.sleep(3)
            
            # Verificação de Sucesso: Se o botão sumiu ou a página mudou, consideramos sucesso
            try:
                if btn_confirmar.count() == 0 or not btn_confirmar.is_visible(timeout=1000):
                    self.logger.info("Botão de confirmação não está mais visível. Sucesso presumido.")
                    return True
            except:
                return True # Provável navegação de página
                
            return True
        except Exception as e:
            self.logger.error(f"Erro crítico ao confirmar Rodapé: {e}")
            self.capturar_screenshot("confirmar_geral_critico")
            raise PeticionamentoException("Confirmação Geral", str(e))

    def finalizar_para_protocolar(self) -> bool:
        """
        Finaliza a preparação da petição clicando em 'Salvar para continuar depois'
        ou 'Finalizar para protocolar depois'.
        """
        try:
            self.logger.info("Finalizando: Localizando botão de salvamento no rodapé...")
            
            # Prioridade: Finalizar para protocolar > Salvar para continuar
            seletores = [
                "button:has-text('Finalizar para protocolar depois')",
                "button:has-text('Salvar para continuar depois')",
                ".css-12uqy48" # Fallback para a classe mostrada no print
            ]
            
            btn_final = None
            for sel in seletores:
                loc = self.page.locator(sel).first
                if loc.count() > 0:
                    btn_final = loc
                    self.logger.info(f"Botão de finalização identificado via: {sel}")
                    break
            
            if not btn_final:
                raise PeticionamentoException("Finalizar", "Nenhum botão de finalização encontrado no rodapé.")

            # 1. Aguardar o botão ficar habilitado (Importante: e-SAJ trava botões até validar campos)
            self.logger.info("Aguardando o botão de finalização ficar habilitado (status check)...")
            for _ in range(10): # Tenta por até 5 segundos
                if not btn_final.is_disabled():
                    break
                time.sleep(0.5)
            
            # 2. Clique Híbrido
            try:
                btn_final.scroll_into_view_if_needed()
                btn_final.click(timeout=8000)
                self.logger.info("✅ Petição finalizada com sucesso via clique padrão.")
            except Exception as e:
                self.logger.warning(f"⚠️ Falha no clique padrão ({e}). Tentando forçar via JS...")
                # Fallback JS: Força o clique obtendo o elemento do locator Playwright e usando evaluate
                btn_final.evaluate("el => el.click()")
                self.logger.info("✅ Comando de finalização enviado via JavaScript.")

            time.sleep(5) # Tempo para processamento do portal
            return True
        except Exception as e:
            self.logger.error(f"Erro ao finalizar: {e}")
            self.capturar_screenshot("erro_finalizacao_saida")
            raise PeticionamentoException("Finalizar Protocolo", str(e))

    def preencher_valores_individualizados(self, data_nascimento: Optional[str] = None, data_base: Optional[str] = None, valor_individual: Optional[float] = None, banco: str = "001", agencia: str = "8058", conta_completa: str = "262-3") -> bool:
        """
        Preenche a aba 'Informar Valores Individualizados' com dados da parte e do advogado.
        
        Args:
            data_nascimento: Data no formato DD/MM/AAAA.
            data_base: Data no formato DD/MM/AAAA.
            valor_individual: Valor financeiro associado à parte.
            banco: Código do banco (ex: 001).
            agencia: Número da agência.
            conta_completa: Conta com dígito (ex: 262-3).
            
        Returns:
            True se finalizou ou superou a etapa.
        """
        try:
            self.logger.info("Iniciando preenchimento de Valores Individualizados...")
            
            # 1. Clicar em "Informar valores individualizados"
            # Aguarda o link aparecer (ele surge após a inclusão da parte)
            btn_informar_valores = self.page.locator("span, a, p").filter(has_text="Informar valores individualizados").first
            try:
                btn_informar_valores.wait_for(state="visible", timeout=12000)
            except Exception:
                self.logger.warning("Link 'Informar valores individualizados' não apareceu.")
                raise PeticionamentoException("Valores Individualizados", "Link de valores não carregou (formulário da parte não expandiu).")

            self.logger.info("Botão encontrado. Clicando...")
            btn_informar_valores.click(force=True)
            time.sleep(2) # Espera abertura do modal
            
            # 2. Preencher Data de Nascimento (se existir)
            if data_nascimento:
                self.logger.info(f"Preenchendo Data de Nascimento do requerente: {data_nascimento}")
                try:
                    campo_nasc = self.page.locator("input[name*='nascimento']").first
                    if campo_nasc.count() == 0:
                         campo_nasc = self.page.locator("input[id*='nasc']").first
                    if campo_nasc.count() > 0:
                        campo_nasc.fill(data_nascimento)
                        HumanHelper.esperar_humano(0.5, 1.0)
                    else:
                        self.logger.warning("Campo 'Data de Nascimento' não encontrado na tela.")
                except Exception as e:
                    self.logger.warning(f"Erro ao tentar preencher Data de Nascimento: {e}")
            
            # 3. Preencher Requisição (Total)
            self.logger.info("Preenchendo Requisição: Total")
            try:
                campo_req = self.page.locator("input[id*='requisicao']").first
                if campo_req.count() == 0:
                    campo_req = self.page.locator("input[aria-labelledby='requisicao-label']").first
                if campo_req.count() > 0:
                     campo_req.click(force=True)
                     campo_req.fill("Total")
                     HumanHelper.esperar_humano(0.5, 0.8)
                     self.page.keyboard.press("Enter")
                     HumanHelper.esperar_humano(0.5, 0.8)
            except Exception as e:
                 self.logger.warning(f"Erro ao preencher Requisição: {e}")
                 
            # 3.1 Houve expedição de RPV? = NÃO
            self.logger.info("Preenchendo Expedição de RPV: NÃO")
            try:
                radio_exp_rpv_n = self.page.locator("input[name='expedicao_rpv'][value='N']").first
                if radio_exp_rpv_n.count() == 0:
                    radio_exp_rpv_n = self.page.locator("[data-testid='radio-expedicao-rpv-nao']").first
                if radio_exp_rpv_n.count() > 0:
                    radio_exp_rpv_n.click(force=True)
                    HumanHelper.esperar_humano(0.5, 0.8)
            except Exception as e:
                self.logger.warning(f"Erro ao marcar Expedição de RPV (Não): {e}")

            # 4. Preencher Levantamento (Crédito em conta do Banco do Brasil)
            self.logger.info(f"Preenchendo Levantamento: Crédito em conta do Banco do Brasil")
            try:
                campo_lev = self.page.locator("input[id*='levantamento']").first
                if campo_lev.count() == 0:
                     campo_lev = self.page.locator("input[aria-labelledby='levantamento-label']").first
                if campo_lev.count() > 0:
                     campo_lev.click(force=True)
                     campo_lev.fill("Crédito em conta do Banco do Brasil")
                     HumanHelper.esperar_humano(0.8, 1.2)
                     self.page.keyboard.press("Enter")
                     HumanHelper.esperar_humano(0.5, 0.8)
            except Exception as e:
                 self.logger.warning(f"Erro ao preencher Levantamento: {e}")

            # 5. Preencher Tipo de Conta (Conta Corrente)
            self.logger.info("Preenchendo Tipo de conta: Conta Corrente")
            try:
                campo_tipo_conta = self.page.locator("input[id*='tipo-conta']").first
                if campo_tipo_conta.count() == 0:
                      campo_tipo_conta = self.page.locator("input[aria-labelledby='tipo-conta-label']").first
                if campo_tipo_conta.count() > 0:
                      campo_tipo_conta.click(force=True)
                      campo_tipo_conta.fill("Conta Corrente")
                      HumanHelper.esperar_humano(0.5, 0.8)
                      self.page.keyboard.press("Enter")
                      HumanHelper.esperar_humano(0.5, 0.8)
            except Exception as e:
                 self.logger.warning(f"Erro ao preencher Tipo de Conta: {e}")

            # 6. Dados Bancários
            self.logger.info(f"Preenchendo Banco: {banco}, Agência: {agencia}, Conta: {conta_completa}")
            try:
                 # Tratar Conta e Dígito (Ex: 262-3)
                 conta_numero = conta_completa
                 conta_dv = ""
                 if "-" in conta_completa:
                     conta_numero, conta_dv = [x.strip() for x in conta_completa.split("-", 1)]
                 
                 self.page.locator("input#banco").first.fill(str(banco))
                 HumanHelper.esperar_humano(0.2, 0.4)
                 self.page.locator("input#agencia").first.fill(str(agencia))
                 HumanHelper.esperar_humano(0.2, 0.4)
                 
                 # Alguns campos de conta no e-SAJ limpam se não houver interação real
                 campo_num_conta = self.page.locator("input#conta").first
                 campo_num_conta.click()
                 campo_num_conta.fill(str(conta_numero))
                 HumanHelper.esperar_humano(0.2, 0.4)
                 
                 campo_dv = self.page.locator("input#digito_verificador").first
                 if campo_dv.count() > 0:
                     campo_dv.fill(str(conta_dv))
                 HumanHelper.esperar_humano(0.5, 1.0)
            except Exception as e:
                 self.logger.warning(f"Erro ao preencher dados bancários ({banco} / {agencia} / {conta_completa}): {e}")

            # 7. Dados do advogado e CNPJ
            self.logger.info("Preenchendo dados do advogado (CNPJ titular)")
            try:
                 radio_adv_sim = self.page.locator("input.jss742[name='flag_dados_advogado'][value='S']").first
                 if radio_adv_sim.count() == 0:
                     radio_adv_sim = self.page.locator("input[name='flag_dados_advogado'][value='S']").first
                 if radio_adv_sim.count() > 0:
                     radio_adv_sim.click(force=True)
                     HumanHelper.esperar_humano(0.8, 1.2)
                 campo_cnpj = self.page.locator("input#cpf_cnpj_titular").first
                 if campo_cnpj.count() > 0:
                      campo_cnpj.fill("37.610.350/0001-80")
                      HumanHelper.esperar_humano(0.5, 1.0)
            except Exception as e:
                 self.logger.warning(f"Erro ao preencher dados de titularidade CNPJ do advogado: {e}")

            # 8. Data Base
            if data_base:
                self.logger.info(f"Preenchendo Data base: {data_base}")
                try:
                     campo_db = self.page.locator("input#data_base").first
                     if campo_db.count() == 0:
                          campo_db = self.page.locator("input[name='data_base']").first
                     if campo_db.count() > 0:
                          campo_db.fill(data_base)
                          HumanHelper.esperar_humano(0.5, 0.8)
                except Exception as e:
                     self.logger.warning(f"Erro ao preencher Data Base: {e}")

            # 9. Total deste Requerente
            if valor_individual is not None:
                self.logger.info(f"Preenchendo Total deste Requerente: {valor_individual}")
                try:
                    campo_total = self.page.locator("input#total_requerente").first
                    if campo_total.count() > 0:
                        valor_str = f"{valor_individual:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                        campo_total.fill(valor_str)
                        HumanHelper.esperar_humano(0.5, 1.0)
                except Exception as e:
                    self.logger.warning(f"Erro ao preencher Total deste Requerente: {e}")

            # 10. Honorários sucumbenciais = SIM
            self.logger.info("Preenchendo Honorários Sucumbenciais: SIM")
            try:
                radio_hon_s = self.page.locator("input[name='honorarios_sucumbenciais'][value='S']").first
                if radio_hon_s.count() > 0:
                    radio_hon_s.click(force=True)
                    HumanHelper.esperar_humano(0.5, 1.0)
            except Exception as e:
                self.logger.warning(f"Erro ao marcar Honorários Sucumbenciais: {e}")

            # 11. Honorários contratuais = NÃO
            self.logger.info("Preenchendo Honorários Contratuais: NÃO")
            try:
                radio_hon_c_n = self.page.locator("input[name='honorarios_contratuais'][value='N']").first
                if radio_hon_c_n.count() > 0:
                    radio_hon_c_n.click(force=True)
                    HumanHelper.esperar_humano(0.5, 1.0)
            except Exception as e:
                self.logger.warning(f"Erro ao marcar Honorários Contratuais: {e}")

            # 12. Clicar em Confirmar (dentro do modal de valores individualizados)
            self.logger.info("Clicando em Confirmar Valores Individualizados...")
            try:
                # Tenta localizar o botão de confirmar do modal de forma mais específica
                btn_modal = self.page.locator("button").filter(has_text=re.compile(r"^Confirmar$", re.IGNORECASE)).last
                if btn_modal.count() == 0:
                    btn_modal = self.page.locator("span").filter(has_text="Confirmar").last
                
                if btn_modal.count() > 0:
                    btn_modal.click(force=True)
                    # Espera o modal sumir (o texto do link de abertura deve ficar oculto ou o modal em si)
                    time.sleep(2)
                    HumanHelper.esperar_humano(1.0, 2.0)
                else:
                    self.logger.warning("Botão 'Confirmar' do modal não encontrado.")
            except Exception as e:
                self.logger.warning(f"Erro ao clicar em Confirmar (Modal): {e}")
                # Forçar fechamento do modal se possível (ESC)
                self.page.keyboard.press("Escape")

            return True

        except Exception as e:
            self.logger.error(f"Erro fatal em preencher_valores_individualizados: {e}")
            raise PeticionamentoException("Valores Individualizados", str(e))
