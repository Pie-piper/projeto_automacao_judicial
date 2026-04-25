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
    Controlador do fluxo de peticionamento eletrÃ´nico no portal e-SAJ.
    Gerencia a navegaÃ§Ã£o, preenchimento de formulÃ¡rios, inclusÃ£o de partes
    e upload de documentos.
    """
    def __init__(self, page: Page):
        self.page = page
        self.logger = logging.getLogger("PeticionamentoEletronico")
        self.screenshots_dir = Path("screenshots_erro")
        self.screenshots_dir.mkdir(exist_ok=True)

    def capturar_screenshot(self, nome_erro: str) -> None:
        """
        Captura um screenshot da tela atual para fins de diagnÃ³stico.
        
        Args:
            nome_erro: Identificador textual para o arquivo de imagem.
        """
        try:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            caminho = self.screenshots_dir / f"peticionamento_{nome_erro}_{timestamp}.png"
            self.page.screenshot(path=str(caminho), full_page=True)
            self.logger.info(f"ðŸ“¸ Screenshot de erro salvo em: {caminho}")
        except Exception as e:
            self.logger.error(f"Erro ao capturar screenshot: {e}")

    def _verificar_recuperar_rota(self) -> bool:
        """
        Verifica se a pÃ¡gina foi redirecionada inesperadamente para o painel (tarefas-adv)
        ou se o SPA congelou no painel mesmo com a URL alterada ("SPA Ghosting").
        """
        try:
            url_atual = self.page.url.lower()
            
            # Caso 1: A URL mostra explicitamente que o robÃ´ caiu
            caiu_para_painel = "tarefas-adv/pet" in url_atual and "novo" not in url_atual
            
            # Caso 2: SPA Ghosting (URL certa, mas a tela visualmente presa no Painel do Advogado)
            tela_travada_no_painel = False
            if "petpgreq" in url_atual or "intermediaria" in url_atual:
                # Se o logo "Painel do advogado" estiver visÃ­vel E nÃ£o tivermos o formulÃ¡rio
                if self.page.locator("text='Painel do advogado'").first.is_visible(timeout=1000) and self.page.locator("text='Peticionamento'").count() > 0:
                    tela_travada_no_painel = True

            if caiu_para_painel or tela_travada_no_painel:
                self.logger.warning("ðŸš¨ Desalinhamento Detectado (Queda de SessÃ£o ou SPA Ghosting preendendo no Painel).")
                
                if tela_travada_no_painel:
                     self.logger.info("ForÃ§ando F5 (Reload) para o e-SAJ renderizar o formulÃ¡rio...")
                     self.page.reload(wait_until="networkidle")
                     time.sleep(3)
                     if not self.page.locator("text='Painel do advogado'").first.is_visible():
                         self.logger.info("A tela de peticionamento foi destravada!")
                         return True # Foi resolvido com reload
                
                # Se ainda estiver ruim ou jÃ¡ caiu explÃ­cito, refaz o fluxo do zero pelo menu
                self.logger.info("Retomando interaÃ§Ã£o obrigatÃ³ria via menu lateral...")
                self.page.keyboard.press("Escape")
                time.sleep(1)
                return self.navegar_para_peticionamento_intermediaria()
                
        except Exception as e:
            self.logger.warning(f"Erro ao verificar rota: {e}")
        return False

    def navegar_para_peticionamento_intermediaria(self) -> bool:
        """
        Navega atÃ© a tela de peticionamento intermediÃ¡rio de 1Âº Grau via menu lateral.
        Esta abordagem Ã© obrigatÃ³ria para evitar detecÃ§Ã£o de robÃ´s por navegaÃ§Ã£o direta.

        Returns:
            True se a navegaÃ§Ã£o foi bem-sucedida.
            
        Raises:
            PortalIndisponivelException: Se o menu nÃ£o carregar ou elementos estiverem ausentes.
        """
        try:
            self.logger.info("Iniciando navegaÃ§Ã£o (InteraÃ§Ã£o via Menu Lateral)...")
            
            # Ancoragem no Painel do Advogado
            if "tarefas-adv/pet" not in self.page.url:
                self.logger.info("Acessando root do Painel do Advogado...")
                self.page.goto("https://esaj.tjsp.jus.br/tarefas-adv/pet/", wait_until="networkidle")
                time.sleep(2)

            # 1. Menu HambÃºrguer
            menu_btn = self.page.locator("span.glyph-hamburger").first
            menu_btn.wait_for(state="visible", timeout=10000)
            menu_btn.click()
            time.sleep(1)

            # 2. Peticionamento EletrÃ´nico
            self.page.locator("button.aside-nav__main-menu__list__item__link", 
                              has_text="Peticionamento EletrÃ´nico").first.click()
            time.sleep(1)

            # 3. 1Âº Grau
            self.page.locator("button.aside-nav__main-menu__list__item__link", 
                              has_text="Peticionamento EletrÃ´nico de 1Âº Grau").first.click()
            time.sleep(1)

            # 4. RequisitÃ³rios
            self.page.locator("a.aside-nav__main-menu__list__item__link", 
                              has_text=re.compile(r"Peticionamento de intermediaria de 1Âº Grau RequisitÃ³rios", re.IGNORECASE)).first.click()
            
            # 5. ValidaÃ§Ã£o de URL
            self.page.wait_for_url(re.compile(r".*(petpgreq|intermediaria|cadastro).*"), timeout=20000)
            self.logger.info(f"âœ… NavegaÃ§Ã£o concluÃ­da: {self.page.url}")
            return True
            
        except Exception as nav_err:
            self.capturar_screenshot("erro_navegacao_menu")
            raise PortalIndisponivelException(f"Falha na navegaÃ§Ã£o via menu: {nav_err}")

    def preencher_dados_processo(self, numero_processo: str, tentativas: int = 0) -> bool:
        """
        Lida com o modal inicial e preenche o nÃºmero do processo com maior estabilidade.
        
        Args:
            numero_processo: O nÃºmero do processo alvo.
            tentativas: Contador interno de recuperaÃ§Ã£o recursiva.
            
        Returns:
            True se for bem-sucedido.
            
        Raises:
            PeticionamentoException: Se esgotar as tentativas de preenchimento.
        """
        if tentativas > 2:
            self.logger.error("âŒ Limite de tentativas de recuperaÃ§Ã£o atingido no preenchimento do processo.")
            raise PeticionamentoException("Preenchimento do Processo", "Limite de retentativas atingido ao referenciar processo.")

        try:
            self.logger.info("Tratando modais e preenchendo processo...")
            
            HumanHelper.esperar_humano(1.0, 2.0)

            # --- VERIFICAÃ‡ÃƒO DE REDIRECIONAMENTO ANTES DE MEXER NA TELA ---
            if self._verificar_recuperar_rota():
                self.logger.info("ðŸ”„ Retomando preenchimento apÃ³s queda (inÃ­cio preencher_dados_processo)...")
                return self.preencher_dados_processo(numero_processo, tentativas + 1)

            # 5. Tratamento de Modais Bloqueantes (Ex: "INSTALAR PLUG-IN" do Web Signer)
            try:
                self.logger.info("Aguardando possÃ­vel carregamento do modal 'INSTALAR PLUG-IN' (atÃ© 8s)...")
                # Modal customizado chato: "INSTALAR PLUG-IN"
                try:
                    # Esperamos ativamente que o modal apareÃ§a. Se no prazo ele nÃ£o renderizar, ele nÃ£o aparecerÃ¡ mais.
                    plugin_modal = self.page.locator("text='INSTALAR PLUG-IN'").first
                    plugin_modal.wait_for(state="visible", timeout=8000)
                    
                    self.logger.info("Modal 'INSTALAR PLUG-IN' detectado! Tentando fechar (Cancelar)...")
                    btn_cancelar_plugin = self.page.locator("div").filter(has=self.page.locator("text='INSTALAR PLUG-IN'")).locator("button", has_text="Cancelar").last
                    if btn_cancelar_plugin.is_visible(timeout=2000):
                        btn_cancelar_plugin.click()
                        self.logger.info("BotÃ£o Cancelar clicado com sucesso.")
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
                        self.logger.info("Modal genÃ©rico fechado.")
                except Exception:
                    pass

            except Exception as e_modal:
                self.logger.warning(f"Aviso ao tratar modais: {e_modal}")

            HumanHelper.esperar_humano(1.0, 2.0)

            # Passo A: Clicar em "Informar" (IDs: #botaoEditarDadosBasicos ou fallback textual)
            self.logger.info("Buscando botÃ£o para informar/editar dados do processo...")
            # Aguarda um pouco para garantir que a pÃ¡gina "hidratou" (JS carregado)
            time.sleep(3)
            self.capturar_screenshot("antes_de_informar")
            
            # Prioridade para o seletor nativo data-testid que o usuÃ¡rio forneceu
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
                    self.logger.info(f"Clicando no botÃ£o abrir/editar processo (seletor: {selector})...")
                    # No novo e-SAJ, Ã s vezes o clique falha se for muito rÃ¡pido, entÃ£o movemos o mouse
                    HumanHelper.mover_mouse_e_clicar(self.page, btn)
                    time.sleep(2)
                    self.capturar_screenshot("apos_clique_informar")
                    botao_clicado = True
                    break
            
            if not botao_clicado:
                 self.logger.warning("Nenhum botÃ£o de abertura (Informar) visÃ­vel. Trocando estratÃ©gia para clique por texto...")
                 try:
                     # ForÃ§a um clique genÃ©rico em qualquer lugar que tenha a palavra "Informar" e um Ã­cone de ediÃ§Ã£o (ou o bloco de processo)
                     texto_informar = self.page.locator("text='Informar'").first
                     if texto_informar.is_visible(timeout=2000):
                         texto_informar.click(force=True)
                         botao_clicado = True
                         time.sleep(2)
                 except Exception:
                    pass

            # Aguardar campo estar habilitado/visÃ­vel
            campo_proc = self.page.locator(Selectors.CAMPO_NUMERO_PROCESSO)
            try:
                campo_proc.wait_for(state="visible", timeout=5000)
            except Exception:
                self.logger.warning("Campo de nÃºmero do processo nÃ£o apareceu. Tentando clicar no lÃ¡pis/editar final...")
                # Fallback final: procurar qualquer Ã­cone de ediÃ§Ã£o (lÃ¡pis) no bloco de processo
                any_edit = self.page.locator(".glyph-edit").first
                if any_edit.is_visible(timeout=2000):
                    any_edit.click()
                    campo_proc.wait_for(state="visible", timeout=3000)

            HumanHelper.esperar_humano(1.0, 2.0)
            
            # Passo B: Preencher NÃºmero do Processo
            # MÃ¡scaras de React/MUI do e-SAJ frequentemente conflitam com o .fill() do Playwright
            self.logger.info(f"Preenchendo campo de processo (digitando pausadamente) com {numero_processo}")
            campo_proc.click(force=True)
            self.page.keyboard.press("Control+A")
            self.page.keyboard.press("Backspace")
            time.sleep(0.5)
            
            # Na maioria das mÃ¡scaras web, extrair os nÃºmeros e deixÃ¡-los preencher sozinhos Ã© o mais seguro
            numero_limpo = re.sub(r'\D', '', numero_processo)
            self.page.keyboard.type(numero_limpo, delay=50)
            
            time.sleep(1)
            self.page.keyboard.press("Tab") # ForÃ§ar disparo da busca de autos
            
            HumanHelper.esperar_humano(2.0, 4.0)
            
            # --- VERIFICAÃ‡ÃƒO DE REDIRECIONAMENTO APÃ“S BUSCA DE PROCESSO (MAIOR RISCO DE ERRO DO ESAJ) ---
            if self._verificar_recuperar_rota():
                self.logger.info("ðŸ”„ Retomando preenchimento apÃ³s queda (durante a busca do processo no e-SAJ)...")
                return self.preencher_dados_processo(numero_processo, tentativas + 1)
            
            # --- NOVO MODAL: Cumprimento de SentenÃ§a ---
            try:
                # O usuÃ¡rio disse: h2 "Cumprimento de sentenÃ§a", radio value="N", botÃ£o span "Confirmar"
                modal_cumprimento = self.page.locator("h2, span, p").filter(has_text="Cumprimento de sentenÃ§a")
                if modal_cumprimento.first.is_visible(timeout=5000):
                    self.logger.info("Modal 'Cumprimento de sentenÃ§a' detectado.")
                    radio_nao = self.page.locator("input[type='radio'][value='N']")
                        
                    if radio_nao.count() > 0:
                        radio_nao.first.click(force=True)
                        HumanHelper.esperar_humano(0.5, 1.0)
                        
                        btn_confirmar = self.page.locator("button, span").filter(has_text="Confirmar")
                        if btn_confirmar.count() > 0:
                            btn_confirmar.first.click(force=True)
                            self.logger.info("Modal 'Cumprimento de sentenÃ§a' confirmado (NÃƒO).")
                            HumanHelper.esperar_humano(1.0, 2.0)
            except Exception as e_modal:
                self.logger.warning(f"Erro ao tratar modal Cumprimento de SentenÃ§a: {e_modal}")
            
            # Verificar se fomos para o login (Indica falha crÃ­tica de sessÃ£o)
            if "login" in self.page.url:
                self.logger.error("âŒ SessÃ£o interrompida apÃ³s preencher processo.")
                raise PortalIndisponivelException("SessÃ£o expirada ou interrompida durante o preenchimento do processo.")

            return True

        except Exception as e:
            if self._verificar_recuperar_rota():
                self.logger.info("ðŸ”„ Queda de tela detectada no tratamento de erro do Processo! Re-tentando do menu...")
                return self.preencher_dados_processo(numero_processo, tentativas + 1)
                
            self.logger.error(f"Erro ao preencher dados do processo: {e}")
            self.capturar_screenshot("preencher_dados_processo")
            raise PeticionamentoException("Preenchimento do Processo", str(e))

    def preencher_dados_classificacao(self, tipo_peticao: str = "1266", tentativas: int = 0) -> bool:
        """
        Realiza apenas o fluxo de ClassificaÃ§Ã£o.
        
        Args:
            tipo_peticao: O cÃ³digo ou nome do tipo de petiÃ§Ã£o.
            tentativas: Contador interno.
            
        Raises:
            PeticionamentoException: Se a etapa falhar apÃ³s as tentativas.
        """
        if tentativas > 2:
             self.logger.error("âŒ Limite de tentativas de recuperaÃ§Ã£o atingido na classificaÃ§Ã£o.")
             raise PeticionamentoException("ClassificaÃ§Ã£o", "Falha crÃ­tica apÃ³s limite de tentativas.")

        try:
            self.logger.info("Iniciando preenchimento da ClassificaÃ§Ã£o (Simplificado)...")
            
            if self._verificar_recuperar_rota():
                self.logger.info("ðŸ”„ Retomando preenchimento apÃ³s queda (preencher_dados_classificacao)...")
                return self.preencher_dados_classificacao(tipo_peticao, tentativas + 1)
            
            HumanHelper.esperar_humano(1.0, 2.0)
            
            # 1. Clicar em Classificar
            self.logger.info(f"Tentando clicar no botÃ£o Classificar: {Selectors.BOTAO_CLASSIFICAR}")
            botao_class = self.page.locator(Selectors.BOTAO_CLASSIFICAR)
            botao_class.wait_for(state='visible', timeout=10000)
            botao_class.scroll_into_view_if_needed()
            
            HumanHelper.mover_mouse_e_clicar(self.page, botao_class)
            HumanHelper.esperar_humano(1.5, 2.5)
            
            # 2. NavegaÃ§Ã£o via Teclado
            self.logger.info(f"Digitando Tipo de PetiÃ§Ã£o via Teclado: {tipo_peticao}")
            self.page.keyboard.press("Tab")
            HumanHelper.esperar_humano(0.3, 0.6)
            self.page.keyboard.type(tipo_peticao, delay=100)
            HumanHelper.esperar_humano(1.2, 1.8)
            self.page.keyboard.press("Enter")
            HumanHelper.esperar_humano(1.0, 1.5)
            
            # 3. Clicar em Confirmar
            self.logger.info("Clicando em Confirmar ClassificaÃ§Ã£o...")
            botao_confirmar = self.page.locator(Selectors.BOTAO_CONFIRMAR_TIPO)
            botao_confirmar.wait_for(state='visible', timeout=5000)
            HumanHelper.mover_mouse_e_clicar(self.page, botao_confirmar)

            HumanHelper.esperar_humano(1.5, 3.0)
            return True
            
        except Exception as e:
            if self._verificar_recuperar_rota():
                self.logger.info("ðŸ”„ Queda de tela detectada no preenchimento de ClassificaÃ§Ã£o! Re-tentando...")
                return self.preencher_dados_classificacao(tipo_peticao, tentativas + 1)
            self.logger.error(f"Erro na etapa de classificaÃ§Ã£o: {e}")
            raise PeticionamentoException("ClassificaÃ§Ã£o", str(e))

    def abrir_dados_suplementares(self, tentativas: int = 0) -> bool:
        """
        Clica em Informar para abrir a seÃ§Ã£o de Dados Suplementares.
        
        Raises:
            PeticionamentoException: Ao exceder tentativas.
        """
        if tentativas > 2:
             self.logger.error("âŒ Limite de tentativas de recuperaÃ§Ã£o atingido ao abrir suplementares.")
             raise PeticionamentoException("Abertura Dados Suplementares", "NÃ£o foi possÃ­vel abrir o modal de Dados Suplementares.")

        try:
            self.logger.info("Clicando em Informar (Dados Suplementares)...")
            
            if self._verificar_recuperar_rota():
                self.logger.info("ðŸ”„ Retomando preenchimento apÃ³s queda (abrir_dados_suplementares)...")
                # A classificaÃ§Ã£o jÃ¡ foi feita? Em teoria o e-SAJ salva e abre assim que a URL for reaberta.
                return self.abrir_dados_suplementares(tentativas + 1)

            informar_btns = self.page.locator(Selectors.BOTAO_INFORMAR_SUPLEMENTARES)
            informar_btns.wait_for(state='visible', timeout=10000)
            
            count = informar_btns.count()
            if count > 1:
                self.logger.info(f"Encontrados {count} botÃµes Informar. Clicando no Ãºltimo...")
                HumanHelper.mover_mouse_e_clicar(self.page, informar_btns.last)
            else:
                HumanHelper.mover_mouse_e_clicar(self.page, informar_btns)
                
            HumanHelper.esperar_humano(1.0, 2.0)
            return True
        except Exception as e:
            if self._verificar_recuperar_rota():
                self.logger.info("ðŸ”„ Queda de tela detectada ao abrir dados suplementares! Re-tentando...")
                return self.abrir_dados_suplementares(tentativas + 1)
            self.logger.error(f"Erro ao abrir dados suplementares: {e}")
            raise PeticionamentoException("Abertura Dados Suplementares", str(e))

    def fazer_upload_documentos(self, lista_arquivos: List[str], tentativas: int = 0) -> bool:
        """
        Realiza o upload dos documentos PDFs organizados.
        Usa expect_file_chooser para interceptar o diÃ¡logo de arquivos do Windows.
        
        Args:
            lista_arquivos: Lista de caminhos absolutos dos PDFs.
            tentativas: Contador interno.
            
        Raises:
            PeticionamentoException: Se falhar apÃ³s tentativas.
        """
        if tentativas > 1:
             self.logger.error("âŒ Limite de tentativas de recuperaÃ§Ã£o atingido no upload.")
             raise PeticionamentoException("Upload de Documentos", "Limite de retentativas atingido ao enviar PDFs.")

        try:
            self.logger.info(f"Iniciando upload de {len(lista_arquivos)} documentos...")
            
            if self._verificar_recuperar_rota():
                self.logger.info("ðŸ”„ Retomando upload apÃ³s queda (fazer_upload_documentos)...")
                return self.fazer_upload_documentos(lista_arquivos, tentativas + 1)
            
            # 1. Preparar para interceptar o diÃ¡logo de arquivo
            with self.page.expect_file_chooser() as fc_info:
                botao_upload = self.page.locator(Selectors.BOTAO_SELECIONE_PDF)
                botao_upload.wait_for(state='visible', timeout=10000)
                
                # O clique dispara o diÃ¡logo
                self.logger.info("Clicando no botÃ£o Selecionar PDF e interceptando diÃ¡logo...")
                HumanHelper.mover_mouse_e_clicar(self.page, botao_upload)
            
            file_chooser = fc_info.value
            # 2. Definir os arquivos diretamente (Playwright lida com o 'Abrir' do Windows internamente)
            file_chooser.set_files(lista_arquivos)
            
            self.logger.info("âœ… Upload de arquivos concluÃ­do com sucesso via FileChooser.")
            HumanHelper.esperar_humano(2, 3)
            
            return True
        except Exception as e:
            if self._verificar_recuperar_rota():
                self.logger.info("ðŸ”„ Queda de tela detectada no upload de documentos! Re-tentando...")
                return self.fazer_upload_documentos(lista_arquivos, tentativas + 1)
            self.logger.error(f"Erro ao fazer upload: {e}")
            self.capturar_screenshot("upload_documentos")
            raise PeticionamentoException("Upload de Documentos", str(e))

    def _normalizar_nome(self, nome: str) -> str:
        """
        Normaliza um nome para comparaÃ§Ã£o robusta:
        Remove acentos, converte para minÃºsculas, remove espaÃ§os extras e pontuaÃ§Ã£o.
        Ex: 'DANIELLE' -> 'daniele', 'Daniele Albano' -> 'daniele albano'
        """
        import unicodedata
        if not nome: return ""
        # Decodifica acentos
        n = unicodedata.normalize('NFKD', str(nome)).encode('ASCII', 'ignore').decode('ASCII')
        # MinÃºsculas e limpeza de caracteres nÃ£o-alfanumÃ©ricos (exceto espaÃ§os)
        n = re.sub(r'[^a-zA-Z0-9\s]', '', n.lower())
        # ReduÃ§Ã£o de letras repetidas (danielle -> daniele) - Fallback para variaÃ§Ãµes comuns
        n = re.sub(r'(.)\1+', r'\1', n)
        # Remove espaÃ§os extras
        n = " ".join(n.split())
        return n

    def categorizar_documentos_upload(self, autores_selecionados: Optional[List[str]] = None) -> bool:
        """
        Categoriza os documentos iterando por cada linha de upload. Se o documento contiver o nome 
        de um Requerente especÃ­fico (ex: Planilha, ProcuraÃ§Ã£o), vincula apenas a ele. SenÃ£o, vincula a todos.
        
        Args:
            autores_selecionados: Lista opcional de nomes dos requerentes selecionados.
            
        Returns:
            True se finalizado.
            
        Raises:
            PeticionamentoException: Se ocorrer erro crÃ­tico na classificaÃ§Ã£o das peÃ§as.
        """
        try:
            self.logger.info(f"Iniciando categorizaÃ§Ã£o dinÃ¢mica. Autores: {autores_selecionados}")
            
            # Normalizar autores selecionados para facilitar o match
            autores_norm = []
            if autores_selecionados:
                for a in autores_selecionados:
                    autores_norm.append({
                        "original": a,
                        "primeiro_nome": self._normalizar_nome(a.split(" ")[0]),
                        "completo": self._normalizar_nome(a)
                    })

            for i in range(30): # MÃ¡ximo razoÃ¡vel de documentos
                try:
                    # 1. Tipo do Documento
                    selector_container = f"[data-testid='select-tipo-documento-{i}']"
                    container = self.page.locator(selector_container).first
                    if container.count() == 0: 
                        break # Fim das linhas
                    
                    # Identificar o nome do arquivo subindo no DOM para pegar a linha inteira via JS
                    texto_linha = self.page.evaluate(f"""(i) => {{
                        let el = document.querySelector(`[data-testid='select-tipo-documento-${{i}}']`);
                        if (!el) return "";
                        let parent = el.closest('.MuiGrid-container') || el.closest('tr') || el.parentElement.parentElement.parentElement.parentElement.parentElement;
                        return parent ? parent.innerText.toUpperCase() : "";
                    }}""", i)
                    
                    if not texto_linha:
                        linha = container.locator("xpath=ancestor::div[4]").first
                        texto_linha = str(linha.inner_text().upper()) if linha.count() > 0 else ""
                    
                    tipo_doc = "Outros Documentos" # Fallback funcional
                    if "PETI" in texto_linha: tipo_doc = "PetiÃ§Ã£o"
                    elif "PROCURA" in texto_linha or "SUBST" in texto_linha: tipo_doc = "ProcuraÃ§Ã£o"
                    elif "PLANILHA" in texto_linha: tipo_doc = "Planilha de CÃ¡lculos"
                    elif "DECIS" in texto_linha: tipo_doc = "CÃ³pias ExtraÃ­das de Outros Processos"
                    elif "CONTRA" in texto_linha: tipo_doc = "Contrato"
                    
                    self.logger.info(f"Linha {i} identificada como '{texto_linha[:40]}'. Tipo designado: {tipo_doc}")
                    
                    # InteraÃ§Ã£o robusta com o MuiSelect
                    container.click(force=True)
                    time.sleep(1)
                    input_tipo = self.page.locator(f"{Selectors.DOC_TIPO_INPUT_PREFIX}{i}").first
                    input_tipo.fill(tipo_doc)
                    time.sleep(1)
                    # No e-SAJ, apÃ³s digitar, precisamos clicar na opÃ§Ã£o que aparece no dropdown (popover)
                    self.page.locator(f"li[role='option']:has-text('{tipo_doc}')").first.click()
                    time.sleep(0.5)
                    
                    # 2. SeleÃ§Ã£o das Partes
                    selector_parte_container = f"[data-testid='select-parte-documento-{i}']"
                    parte_container = self.page.locator(selector_parte_container).first
                    
                    if parte_container.is_visible(timeout=3000):
                        parte_container.click(force=True)
                        time.sleep(1)
                        
                        if autores_norm:
                            autor_especifico = None
                            # Se for Planilha, ProcuraÃ§Ã£o ou Contrato, tentamos achar o dono do arquivo
                            if tipo_doc in ["Planilha de CÃ¡lculos", "ProcuraÃ§Ã£o", "Contrato"]:
                                texto_norm_linha = self._normalizar_nome(texto_linha)
                                for a_info in autores_norm:
                                    if a_info["primeiro_nome"] in texto_norm_linha:
                                        autor_especifico = a_info["original"]
                                        break
                                        
                            autores_vincular = [autor_especifico] if autor_especifico else autores_selecionados # type: ignore
                            
                            for autor in autores_vincular:
                                # Digitar o nome no input do select
                                input_parte = self.page.locator(f"{Selectors.DOC_PARTE_INPUT_PREFIX}{i}").first
                                input_parte.type(autor.split(" ")[0], delay=100)
                                time.sleep(1)
                                
                                # Tenta achar a opÃ§Ã£o que mais se aproxima (Fuzzy match manual via labels do MUI)
                                autor_norm_val = self._normalizar_nome(autor)
                                options = self.page.locator("li[role='option']")
                                found_option = False
                                for j in range(options.count()):
                                    opt = options.nth(j)
                                    if autor_norm_val in self._normalizar_nome(opt.inner_text()) or self._normalizar_nome(opt.inner_text()) in autor_norm_val:
                                        opt.click()
                                        found_option = True
                                        break
                                
                                if not found_option:
                                    self.page.keyboard.press("Enter") # Fallback se nÃ£o achar o texto exato
                                time.sleep(0.5)
                        else:
                            self.page.keyboard.press("ArrowDown")
                            self.page.keyboard.press("Enter")
                            
                        self.page.keyboard.press("Escape")
                        time.sleep(1)
                        
                except Exception as row_error:
                    self.logger.warning(f"Erro ao categorizar linha {i}: {row_error}")
                    continue
            return True
        except Exception as e:
            self.logger.error(f"Erro na etapa de classificaÃ§Ã£o: {e}")
            self.capturar_screenshot("classificacao")
            raise PeticionamentoException("ClassificaÃ§Ã£o de PeÃ§as", str(e))

    def adicionar_partes_polo_ativo(self, autores_selecionados: List[str]) -> bool:
        """
        Adiciona os autores selecionados ao Polo Ativo no sistema e-SAJ,
        pesquisando pelos IDs recomendados (0 a 5) e clicando em "Incluir esta parte".
        
        Args:
            autores_selecionados: Nomes a serem incluÃ­dos.
            
        Returns:
            True se finalizada a etapa de checagem.
        """
        try:
            if not autores_selecionados: return True
            self.logger.info(f"Adicionando {len(autores_selecionados)} partes ao Polo Ativo...")
            
            # Normalizar nomes selecionados para comparaÃ§Ã£o
            autores_alvo = [self._normalizar_nome(a) for a in autores_selecionados]
            
            # 1. Tentar encontrar os botÃµes sugeridos pelo usuÃ¡rio (IDs 0 a 5)
            # e-SAJ costuma renderizar 'incluir-parte-0', 'incluir-parte-1', etc.
            partes_incluidas_count = 0
            
            # Aumentamos o range de seguranÃ§a (atÃ© 8) e verificamos na tela
            for i in range(8):
                try:
                    btn_id = f"button[data-testid='incluir-parte-{i}']"
                    btn = self.page.locator(btn_id).first
                    
                    if btn.count() > 0 and btn.is_visible():
                        # Antes de clicar, verificar se o nome nesta caixa Ã© o que queremos
                        # O nome costuma estar em um <p> dentro da div pai do botÃ£o
                        container = btn.locator("xpath=ancestor::div[1]").first
                        texto_caixa_norm = self._normalizar_nome(container.inner_text())
                        
                        alvo_encontrado = None
                        for original, norm in zip(autores_selecionados, autores_alvo):
                            if norm in texto_caixa_norm or texto_caixa_norm in norm:
                                alvo_encontrado = original
                                break
                        
                        if alvo_encontrado:
                            self.logger.info(f"Clicando para incluir ({btn_id}): {alvo_encontrado}")
                            btn.click(force=True)
                            partes_incluidas_count += 1
                            # Espera para o e-SAJ processar e liberar os links de valores
                            time.sleep(2)
                        else:
                            self.logger.debug(f"ID {i} ignorado (nome '{texto_caixa_norm[:20]}' nÃ£o selecionado).")
                    
                except Exception as e_id:
                    self.logger.debug(f"Erro ao verificar ID {i}: {e_id}")
                    continue

            # 2. Fallback: Busca genÃ©rica em caixas sugeridas (caso o ID nÃ£o seja linear)
            if partes_incluidas_count < len(autores_selecionados):
                self.logger.info("Executando fallback para buscar partes sugeridas fora da ordem de ID linear...")
                caixas_partes = self.page.locator("[data-testid='partes-sugeridas'] > div")
                count = caixas_partes.count()
                
                for i in range(count):
                    caixa = caixas_partes.nth(i)
                    texto_caixa_norm = self._normalizar_nome(caixa.inner_text())
                    
                    alvo_encontrado = None
                    for original, norm in zip(autores_selecionados, autores_alvo):
                        if norm in texto_caixa_norm or texto_caixa_norm in norm:
                           alvo_encontrado = original
                           break
                    
                    if alvo_encontrado:
                        btn = caixa.locator("button, p").filter(has_text=re.compile(r"Incluir|Incluir esta parte", re.IGNORECASE)).first
                        if btn.count() > 0 and btn.is_visible():
                            self.logger.info(f"Clicando para incluir (Fallback): {alvo_encontrado}")
                            btn.click(force=True)
                            partes_incluidas_count += 1
                            time.sleep(2)

            self.logger.info(f"âœ… Polo Ativo processado. {partes_incluidas_count} partes incluÃ­das.")
            return True
        except Exception as e:
            self.logger.error(f"Erro no Polo Ativo: {e}")
            self.capturar_screenshot("polo_ativo")
            return False

    def preencher_natureza_e_valor(self, valor, data_ajuizamento: Optional[str] = None, data_transito_julgado: Optional[str] = None, teve_impugnacao: bool = False):
        """
        Preenche o campo de entidade devedora, natureza e o valor nos dados suplementares 
        seguindo a lÃ³gica de navegaÃ§Ã£o por teclado (5 Tabs). 
        Preenche tambÃ©m os novos campos de datas (Ajuizamento, Transito) e ImpugnaÃ§Ã£o.
        """
        try:
            self.logger.info(f"Iniciando preenchimento de dados suplementares: R$ {valor}")
            
            # O sistema TJSP abre o modal de Dados Suplementares ao clicar em Informar.
            # O usuÃ¡rio informou que devemos apertar Tab 5 vezes para chegar no campo Entidade Devedora.
            
            self.logger.info("Executando 5 Tabs para chegar na Entidade Devedora...")
            for _ in range(5):
                self.page.keyboard.press("Tab")
                HumanHelper.esperar_humano(0.2, 0.4)
            
            # 1. Preencher Entidade Devedora
            self.logger.info("Digitando Entidade Devedora: FAZENDA DO ESTADO DE SÃƒO PAULO")
            self.page.keyboard.type("FAZENDA DO ESTADO DE SÃƒO PAULO", delay=100)
            HumanHelper.esperar_humano(0.8, 1.2)
            self.page.keyboard.press("Enter")
            HumanHelper.esperar_humano(0.5, 0.8)
            
            # 2. NavegaÃ§Ã£o para Natureza
            self.logger.info("Navegando para campo Natureza...")
            self.page.keyboard.press("Tab")
            HumanHelper.esperar_humano(0.3, 0.6)
            
            # Digitar 'alimentar' e Enter
            self.page.keyboard.type("alimentar", delay=100)
            HumanHelper.esperar_humano(0.5, 0.8)
            self.page.keyboard.press("Enter")
            HumanHelper.esperar_humano(0.8, 1.2)
            
            # 3. NavegaÃ§Ã£o para Valor
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
                self.logger.info(f"Preenchendo Data TrÃ¢nsito Julgado: {data_transito_julgado}")
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

            self.logger.info(f"Opostos embargos/impugnaÃ§Ã£o? {'Sim' if teve_impugnacao else 'NÃ£o'}")
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

            # --- INDENIZATÃ“RIO E VALOR INCONTROVERSO ---
            self.logger.info("Ajustando 'Valor Incontroverso' e 'Natureza do CrÃ©dito'")
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
                self.logger.warning(f"Erro ao ajustar Incontroverso ou Natureza CrÃ©dito: {e_ind}")

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

    def categorizar_documentos_upload(self, autores_selecionados: Optional[list] = None):
        """
        Categoriza os documentos no grid de upload:
        - Seleciona 'Tipo do Documento' baseado no nome do arquivo.
        - Seleciona 'Parte' (Autor) se disponÃ­vel.
        """
        try:
            self.logger.info("Iniciando categorizaÃ§Ã£o dinÃ¢mica de documentos no grid...")
            
            # Localiza todas as linhas de documentos no grid
            linhas = self.page.locator("div[data-testid^='div-tipo-documento-']")
            count = linhas.count()
            self.logger.info(f"Encontradas {count} linhas de documentos para categorizar.")
            
            for i in range(count):
                try:
                    # 1. Identificar o tipo do documento pelo nome do arquivo
                    # O nome costuma estar em um span ou div anterior no mesmo container pai
                    container_pai = self.page.locator(f"div[data-testid='div-tipo-documento-{i}']").locator("xpath=ancestor::div[1]").first
                    nome_arquivo = container_pai.inner_text().upper()
                    
                    self.logger.info(f"Categorizando linha {i}: {nome_arquivo[:40]}...")
                    
                    # Normalize the filename within the loop for robust keyword matching
                    nome_norm = self._normalizar_nome(nome_arquivo)
                    self.logger.debug(f"Processando nome normalizado: {nome_norm}")
                    
                    # Decidir o tipo conforme exigÃªncia exata (conforme imagem do usuÃ¡rio)
                    tipo_doc = "Documentos Diversos"
                    if "peticao" in nome_norm or "substabel" in nome_norm:
                        tipo_doc = "PetiÃ§Ã£o"
                    elif "planilha" in nome_norm or "calculo" in nome_norm:
                        tipo_doc = "Planilha de CÃ¡lculos"
                    elif "procuracao" in nome_norm:
                        tipo_doc = "ProcuraÃ§Ã£o"
                    elif "acordao" in nome_norm:
                        tipo_doc = "AcÃ³rdÃ£o"
                    elif "sentenca" in nome_norm or "decisao" in nome_norm:
                        tipo_doc = "CÃ³pias ExtraÃ­das de Outros Processos"
                    elif "documento pessoal" in nome_norm or "identidade" in nome_norm or "rg" in nome_norm or "cpf" in nome_norm:
                        tipo_doc = "Documento de IdentificaÃ§Ã£o"
                    elif "contrato" in nome_norm:
                        tipo_doc = "Contrato"
                    
                    # --- ABA 1: TIPO DO DOCUMENTO ---
                    input_tipo = self.page.locator(f"#select-input-tipo-documento-{i}").first
                    if input_tipo.is_visible():
                        self.logger.info(f"Selecionando Tipo: {tipo_doc}")
                        container_tipo = self.page.locator(f"div[data-testid='select-tipo-documento-{i}']").first
                        container_tipo.click(force=True)
                        input_tipo.fill(tipo_doc)
                        opcao = self.page.locator(f"li[role='option']:has-text('{tipo_doc}')").first
                        opcao.click(force=True)

                    # --- ABA 2: PARTE (OPCIONAL NESTA ETAPA) ---
                    if autores_selecionados:
                        # Tenta vincular o documento a um autor se o nome do autor estiver no arquivo
                        autor_vinculo = None
                        autores_norm = [self._normalizar_nome(a) for a in autores_selecionados]
                        nome_arquivo_norm = self._normalizar_nome(nome_arquivo)
                        
                        for original, norm in zip(autores_selecionados, autores_norm):
                            if norm in nome_arquivo_norm or nome_arquivo_norm in norm:
                                autor_vinculo = original
                                break

                        if autor_vinculo:
                            input_parte = self.page.locator(f"#select-input-parte-{i}").first
                            if input_parte.count() > 0 and input_parte.is_visible():
                                self.logger.info(f"Vinculando Ã  parte: {autor_vinculo}")
                                container_parte = self.page.locator(f"div[data-testid='select-parte-{i}']").first
                                container_parte.click(force=True)
                                input_parte.fill(autor_vinculo)
                                self.page.locator(f"li[role='option']").filter(has_text=re.compile(f"{autor_vinculo.split(' ')[0]}", re.I)).first.click(force=True)

                except Exception as row_error:
                    self.logger.warning(f"Erro na linha {i}: {row_error}")
                    continue
            
            return True
        except Exception as e:
            self.logger.error(f"Erro na categorizaÃ§Ã£o: {e}")
            self.capturar_screenshot("categorizacao")
            return False

    def confirmar_informacoes_gerais(self) -> bool:
        """
        Clica no botÃ£o 'Confirmar' no rodapÃ© (footer-confirmar-1) para validar as informaÃ§Ãµes inseridas.
        
        Returns:
            True se o botÃ£o foi clicado.
            
        Raises:
            PeticionamentoException: Se houver falha ao confirmar.
        """
        try:
            self.logger.info("Clicando no botÃ£o de confirmaÃ§Ã£o geral (RodapÃ©)...")
            btn_confirmar = self.page.locator("button[data-testid='footer-confirmar-1']").first
            btn_confirmar.wait_for(state="visible", timeout=10000)
            btn_confirmar.click(force=True)
            time.sleep(3)
            return True
        except Exception as e:
            self.logger.error(f"Erro ao clicar em Confirmar RodapÃ©: {e}")
            self.capturar_screenshot("confirmar_geral")
            raise PeticionamentoException("ConfirmaÃ§Ã£o Geral", str(e))

    def finalizar_para_protocolar(self) -> bool:
        """
        Finaliza a preparaÃ§Ã£o da petiÃ§Ã£o clicando em 'Salvar para continuar depois'.
        
        Returns:
            True se a petiÃ§Ã£o foi salva com sucesso.
            
        Raises:
            PeticionamentoException: Se a finalizaÃ§Ã£o falhar.
        """
        try:
            self.logger.info("Finalizando: Clicando em 'Salvar para continuar depois'...")
            # Busca pelo texto ou ID conhecido
            btn = self.page.locator("button").filter(has_text="Salvar para continuar depois").first
            if btn.count() == 0:
                btn = self.page.locator(".css-12uqy48").first # Fallback class
            
            btn.wait_for(state="visible", timeout=10000)
            btn.click(force=True)
            time.sleep(5)
            self.logger.info("Processo finalizado com sucesso.")
            return True
        except Exception as e:
            self.logger.error(f"Erro ao finalizar: {e}")
            raise PeticionamentoException("Finalizar Protocolo", str(e))

    def preencher_valores_individualizados(self, data_nascimento: Optional[str] = None, data_base: Optional[str] = None, valor_individual: Optional[float] = None) -> bool:
        """
        Preenche a aba 'Informar Valores Individualizados' com dados da parte e do advogado.
        
        Args:
            data_nascimento: Data no formato DD/MM/AAAA.
            data_base: Data no formato DD/MM/AAAA.
            valor_individual: Valor financeiro associado Ã  parte.
            
        Returns:
            True se finalizou ou superou a etapa.
        """
        try:
            self.logger.info("Iniciando preenchimento de Valores Individualizados...")
            
            # 1. Clicar em "Informar valores individualizados"
            # Aguarda o link aparecer (ele surge apÃ³s a inclusÃ£o da parte)
            btn_informar_valores = self.page.locator("span, a, p").filter(has_text="Informar valores individualizados").first
            try:
                btn_informar_valores.wait_for(state="visible", timeout=12000)
            except Exception:
                self.logger.warning("Link 'Informar valores individualizados' nÃ£o apareceu.")
                raise PeticionamentoException("Valores Individualizados", "Link de valores nÃ£o carregou (formulÃ¡rio da parte nÃ£o expandiu).")

            self.logger.info("BotÃ£o encontrado. Clicando...")
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
                        self.logger.warning("Campo 'Data de Nascimento' nÃ£o encontrado na tela.")
                except Exception as e:
                    self.logger.warning(f"Erro ao tentar preencher Data de Nascimento: {e}")
            
            # 3. Preencher RequisiÃ§Ã£o (Total)
            self.logger.info("Preenchendo RequisiÃ§Ã£o: Total")
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
                 self.logger.warning(f"Erro ao preencher RequisiÃ§Ã£o: {e}")
                 
            # 4. Preencher Levantamento (CrÃ©dito em conta do Banco)
            self.logger.info("Preenchendo Levantamento: CrÃ©dito em conta do Banco")
            try:
                campo_lev = self.page.locator("input[id*='levantamento']").first
                if campo_lev.count() == 0:
                     campo_lev = self.page.locator("input[aria-labelledby='levantamento-label']").first
                if campo_lev.count() > 0:
                     campo_lev.click(force=True)
                     campo_lev.fill("CrÃ©dito em conta do Banco")
                     HumanHelper.esperar_humano(0.5, 0.8)
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

            # 6. Dados BancÃ¡rios
            self.logger.info("Preenchendo Banco, AgÃªncia, Conta e DV")
            try:
                 self.page.locator("input#banco").first.fill("001")
                 HumanHelper.esperar_humano(0.2, 0.4)
                 self.page.locator("input#agencia").first.fill("8058")
                 HumanHelper.esperar_humano(0.2, 0.4)
                 self.page.locator("input#conta").first.fill("262")
                 HumanHelper.esperar_humano(0.2, 0.4)
                 self.page.locator("input#digito_verificador").first.fill("3")
                 HumanHelper.esperar_humano(0.5, 1.0)
            except Exception as e:
                 self.logger.warning(f"Erro ao preencher dados bancÃ¡rios (001 / 8058 / 262-3): {e}")

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

            # 10. HonorÃ¡rios sucumbenciais = SIM
            self.logger.info("Preenchendo HonorÃ¡rios Sucumbenciais: SIM")
            try:
                radio_hon_s = self.page.locator("input[name='honorarios_sucumbenciais'][value='S']").first
                if radio_hon_s.count() > 0:
                    radio_hon_s.click(force=True)
                    HumanHelper.esperar_humano(0.5, 1.0)
            except Exception as e:
                self.logger.warning(f"Erro ao marcar HonorÃ¡rios Sucumbenciais: {e}")

            # 11. HonorÃ¡rios contratuais = NÃƒO
            self.logger.info("Preenchendo HonorÃ¡rios Contratuais: NÃƒO")
            try:
                radio_hon_c_n = self.page.locator("input[name='honorarios_contratuais'][value='N']").first
                if radio_hon_c_n.count() > 0:
                    radio_hon_c_n.click(force=True)
                    HumanHelper.esperar_humano(0.5, 1.0)
            except Exception as e:
                self.logger.warning(f"Erro ao marcar HonorÃ¡rios Contratuais: {e}")

            # 12. Clicar em Confirmar (dentro do modal de valores individualizados)
            self.logger.info("Clicando em Confirmar Valores Individualizados...")
            try:
                btn_confirmar = self.page.locator("span").filter(has_text="Confirmar").last
                if btn_confirmar.count() > 0:
                    btn_confirmar.click(force=True)
                    HumanHelper.esperar_humano(1.5, 3.0)
            except Exception as e:
                self.logger.warning(f"Erro ao clicar em Confirmar: {e}")

            return True

        except Exception as e:
            self.logger.error(f"Erro fatal em preencher_valores_individualizados: {e}")
            raise PeticionamentoException("Valores Individualizados", str(e))
