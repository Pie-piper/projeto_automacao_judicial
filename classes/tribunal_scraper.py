from playwright.sync_api import sync_playwright, TimeoutError, expect
import time
import logging
import os
import sys
import re
from typing import Optional, Dict, Any, Callable
from pathlib import Path
from classes.pasta_digital_page import PastaDigitalPage

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from classes.imap_handler import ImapHandler
from classes.human_helper import HumanHelper
from classes.selectors import Selectors
from classes import utils
from classes.exceptions import (
    TribunalException, 
    LoginException, 
    PortalIndisponivelException, 
    ProcessoNaoEncontradoException,
    BrowserCrashException
)

class TribunalScraper:
    """
    Classe responsável por toda a interação inicial com o portal e-SAJ/TJSP.
    Realiza login, busca de processos e download de documentos básicos.
    """
    def __init__(self, numero_processo: str):
        self.numero_processo = numero_processo
        self.playwright: Any = None
        self.browser: Any = None
        self.page: Any = None
        self.page_autos: Any = None
        self.contexto_processo: Any = None
        self.url_pasta_digital: str = ""

        # Configurar logger
        try:
            from classes.utils import configurar_logger
            configurar_logger(str(config.LOGS_DIR / f"automacao_{self.numero_processo}.log"))
        except ImportError:
            logging.basicConfig(
                filename=str(config.LOGS_DIR / f"automacao_{self.numero_processo}.log"),
                level=logging.INFO,
                format="%(asctime)s - %(levelname)s - %(message)s"
            )

    def iniciar_navegador(self, headless: bool = False) -> None:
        """
        Inicializa o navegador persistente com argumentos de estabilidade e evasão de bots.
        """
        try:
            self.playwright = sync_playwright().start()
            
            # Argumentos para maior estabilidade e prevenção de conflitos
            args = [
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
                "--disable-renderer-backgrounding",
                "--disable-features=RendererCodeIntegrity",
                "--no-zygote", 
                "--start-maximized"
            ]

            # Diretório de perfil persistente (Centralizado via config)
            user_data_dir = config.USER_DATA_DIR / "browser_profile"
            user_data_dir.mkdir(parents=True, exist_ok=True)

            try:
                self.browser = self.playwright.chromium.launch_persistent_context(
                    user_data_dir=str(user_data_dir),
                    headless=headless,
                    args=args,
                    slow_mo=300, 
                    no_viewport=True,
                    locale='pt-BR',
                    timezone_id='America/Sao_Paulo',
                    accept_downloads=True
                )
            except Exception as e:
                if "user data directory is already in use" in str(e).lower() or "locked" in str(e).lower():
                    logging.warning("⚠️ Perfil do navegador em uso. Tentando usar perfil temporário para evitar crash...")
                    print("⚠️ O perfil do navegador já está em uso por outra instância (talvez o Chrome esteja aberto).")
                    print("💡 Feche todas as janelas do Chrome e tente novamente para manter o login.")
                    # Fallback para perfil temporário se o principal estiver travado e for um teste
                    user_data_dir_alt = config.USER_DATA_DIR / f"browser_profile_tmp_{int(time.time())}"
                    self.browser = self.playwright.chromium.launch_persistent_context(
                        user_data_dir=str(user_data_dir_alt),
                        headless=headless,
                        args=args,
                        slow_mo=300,
                        no_viewport=True
                    )
                else:
                    raise

            # Script para evitar que a ausência do Conpass trave a página
            self.browser.add_init_script("""
                window.Conpass = {
                    init: () => {}, start: () => {}, stop: () => {}
                };
            """)
            
            # Garante que temos uma página válida
            if len(self.browser.pages) > 0:
                self.page = self.browser.pages[0]
            else:
                self.page = self.browser.new_page()

            # Forçar a página a estar em foco
            self.page.bring_to_front()
            
            self.page.set_default_timeout(config.TIMEOUT_PADRAO)
            self.page.set_default_navigation_timeout(config.TIMEOUT_NAVEGACAO)

            logging.info("Navegador iniciado com sucesso.")
            
        except Exception as e:
            logging.error(f"Erro fatal ao iniciar navegador: {e}")
            if "closed" in str(e).lower():
                print("❌ Erro: O navegador foi fechado prematuramente ou já estava aberto.")
                print("👉 Dica: Feche o Google Chrome completamente e pare qualquer outra automação antes de rodar.")
            raise BrowserCrashException("iniciar_navegador", e)

    def tentar(self, func: Callable, descricao: str, tentativas: int = config.TENTATIVAS_RETRY) -> Any:
        """
        Executa uma função com lógica de retry e captura de erro diagnóstica.
        
        Args:
            func: Função a ser executada.
            descricao: Descrição da ação para logs.
            tentativas: Número máximo de tentativas.
        """
        for tentativa in range(1, tentativas + 1):
            try:
                logging.info(f"Tentando: {descricao} (tentativa {tentativa})")
                return func()
            except TribunalException as e_tribunal:
                if getattr(e_tribunal, 'can_retry', False) is False:
                    # Se explicitamente for marcado que não tem retry (ex: Processo Não Encontrado)
                    raise e_tribunal
                
                logging.error(f"Erro em '{descricao}': {e_tribunal}")
                if tentativa == tentativas:
                    raise e_tribunal
                time.sleep(2 * tentativa)
            except Exception as e:
                logging.error(f"Erro em '{descricao}': {e}")

                timestamp = int(time.time())
                screenshot_path = str(config.LOGS_DIR / f"erro_{descricao}_{timestamp}_{tentativa}.png")
                try:
                    if self.page:
                        self.page.screenshot(path=screenshot_path)
                        logging.info(f"Screenshot salvo em {screenshot_path}")
                except Exception as s_e:
                    logging.error(f"Não foi possível salvar screenshot: {s_e}")

                if tentativa == tentativas:
                    raise e
                
                time.sleep(2 * tentativa)

    def acessar_tribunal(self):
        def func():
            print("\n" + "="*80)
            print("🌐 ACESSANDO O TRIBUNAL")
            print("="*80)
            
            if not hasattr(self, 'page') or self.page is None or self.browser is None:
                print("⚠️ Navegador não está ativo, reiniciando...")
                logging.warning("Navegador não está ativo, reiniciando...")
                self.iniciar_navegador(headless=False)
            
            print(f"📍 Navegando para: {config.TRIBUNAL_URL}")
            logging.info(f"Navegando para: {config.TRIBUNAL_URL}")
            
            try:
                self.page.goto(config.TRIBUNAL_URL)
                print("✅ Página carregada")
            except Exception as e:
                if "closed" in str(e).lower() or "target" in str(e).lower():
                    print("⚠️ Navegador foi fechado, reiniciando...")
                    logging.warning("Navegador foi fechado, reiniciando...")
                    self.iniciar_navegador(headless=False)
                    self.page.goto(config.TRIBUNAL_URL)
                    print("✅ Página carregada após reinício")
                else:
                    raise
            
            # Wait for either login button or search field
            print("🔍 Verificando estado da página...")
            try:
                expect(self.page.locator("#pbEntrar, #numeroDigitoAnoUnificado")).to_be_visible(timeout=10000)
            except Exception:
                pass

            if self.page.locator("#pbEntrar").is_visible():
                print("🔐 Página de login detectada")
                logging.info("Página de login detectada, realizando login...")
                self.fazer_login()
            elif self.page.locator("text=Identificar-se").is_visible():
                print("👤 Detectado botão 'Identificar-se' - Usuário não logado")
                logging.info("Usuário não logado. Clicando em 'Identificar-se'...")
                try:
                    self.page.locator("text=Identificar-se").click()
                    print("⏳ Aguardando carreamento do formulário de login...")
                    self.page.wait_for_selector("#pbEntrar", timeout=20000)
                    self.fazer_login()
                except Exception as e:
                    logging.error(f"Falha ao tentar acessar login via 'Identificar-se': {e}")
                    raise
            else:
                if self.page.locator("text=Digite os caracteres").is_visible():
                    print("⚠️ CAPTCHA detectado — aguardando resolução manual...")
                    logging.warning("CAPTCHA detectado — aguardando resolução manual ou retry.")
                    self.page.wait_for_selector("input[id='numeroDigitoAnoUnificado']", timeout=60000)
                else:
                    print("✅ Já está logado, aguardando campo de busca...")
                    self.page.wait_for_selector("input[id='numeroDigitoAnoUnificado']")
            
            print("="*80 + "\n")

        self.tentar(func, "acessar_tribunal")

    def fazer_login(self, max_tentativas: int = 3):
        """
        Realiza o login no e-SAJ com retry automático e reinicialização do browser
        a cada crash de infraestrutura (Target crashed, Session closed, etc.).
        """
        for tentativa in range(1, max_tentativas + 1):
            try:
                print("\n" + "="*80)
                print(f"🔐 INICIANDO LOGIN (tentativa {tentativa}/{max_tentativas})")
                print("="*80)
                logging.info(f"Preenchendo credenciais de login (tentativa {tentativa})...")
                
                # Garantir que o navegador está ativo antes de preencher
                if not hasattr(self, 'page') or self.page is None:
                    logging.warning("Página não disponível antes do login — reiniciando navegador...")
                    self.iniciar_navegador(headless=False)
                    self.page.goto(config.TRIBUNAL_URL)
                
                HumanHelper.esperar_humano(2.0, 4.0)
                HumanHelper.scroll_suave(self.page, 150)
                HumanHelper.esperar_humano(0.5, 1.0)
                
                username_selectors = ["input[name='username']", "input[id='username']", "input[type='text'][name='login']", "input[id='login']"]
                password_selectors = ["input[name='password']", "input[id='password']", "input[type='password']"]
                login_button_selectors = ["input[id='pbEntrar']", "input[type='submit'][value='Entrar']", "input[name='pbEntrar']", "button[type='submit']"]
                
                if not self._preencher_campo(username_selectors, config.LOGIN_TJSP, "usuário"):
                    raise LoginException("Campo de usuário não encontrado no formulário de login")
                
                HumanHelper.esperar_humano(0.8, 1.5)
                
                if not self._preencher_campo(password_selectors, config.SENHA_TJSP, "senha"):
                    raise LoginException("Campo de senha não encontrado no formulário de login")
                
                HumanHelper.esperar_humano(1.0, 2.0)
                
                if not self._clicar_botao(login_button_selectors, "entrar"):
                    raise LoginException("Botão de login ('Entrar') não encontrado ou não clicável")
                
                logging.info("Credenciais enviadas, aguardando resposta...")
                HumanHelper.esperar_humano(3.0, 5.0)

                if self._tratar_status_breakpoint(tentativas=3):
                    logging.info("Status Breakpoint tratado com sucesso (ou página estava ok)")
                else:
                    logging.warning("Não foi possível resolver o status da página via reload, prosseguindo com cautela...")

                if self._verificar_solicitacao_2fa():
                    logging.info("Código 2FA solicitado")
                    self._processar_2fa()
                
                self.page.wait_for_load_state("networkidle", timeout=30000)
                HumanHelper.esperar_humano(2.0, 3.0)
                print("✅ Login realizado com sucesso!")
                print("="*80 + "\n")
                logging.info("Login realizado com sucesso")
                return  # Sucesso — sai do loop de retry
                
            except BrowserCrashException as e:
                logging.error(f"[Tentativa {tentativa}/{max_tentativas}] Crash de browser durante login: {e}")
                self._salvar_screenshot_erro(f"login_crash_{tentativa}")
                if tentativa == max_tentativas:
                    raise LoginException(f"Browser crashou {max_tentativas}x seguidas durante o login: {e}")
                
                espera = 5 * tentativa
                logging.warning(f"⚠️ Reiniciando browser em {espera}s (tentativa {tentativa}/{max_tentativas})...")
                print(f"⚠️ Browser crashou. Reiniciando em {espera}s...")
                self._fechar_navegador_seguro()
                time.sleep(espera)
                self.iniciar_navegador(headless=False)
                self.page.goto(config.TRIBUNAL_URL)
                try:
                    self.page.wait_for_selector("#pbEntrar", timeout=15000)
                except Exception:
                    pass
                
            except LoginException:
                # Erros verdadeiros de credencial/2FA sem causa de crash — não retentar
                self._salvar_screenshot_erro("login")
                raise
            except Exception as e:
                # Qualquer outro erro de infra é tratado como crash retentarável
                logging.error(f"[Tentativa {tentativa}/{max_tentativas}] Erro inesperado no login: {type(e).__name__} - {e}")
                self._salvar_screenshot_erro(f"login_erro_{tentativa}")
                if tentativa == max_tentativas:
                    raise
                
                espera = 5 * tentativa
                logging.warning(f"⚠️ Erro não classificado. Reiniciando browser em {espera}s...")
                print(f"⚠️ Erro no login (não-credencial). Reiniciando em {espera}s...")
                self._fechar_navegador_seguro()
                time.sleep(espera)
                self.iniciar_navegador(headless=False)
                self.page.goto(config.TRIBUNAL_URL)
                try:
                    self.page.wait_for_selector("#pbEntrar", timeout=15000)
                except Exception:
                    pass

    def _preencher_campo(self, selectors, valor, nome_campo):
        composite_selector = ", ".join(selectors)
        try:
            element = self.page.locator(composite_selector).first
            expect(element).to_be_visible(timeout=5000)
            logging.info(f"Preenchendo {nome_campo}")
            HumanHelper.digitar_como_humano(element, valor)
            return True
        except Exception as e:
            logging.debug(f"Campo {nome_campo} não encontrado: {e}")
            return False

    def _clicar_botao(self, selectors, nome_botao):
        composite_selector = ", ".join(selectors)
        try:
            element = self.page.locator(composite_selector).first
            expect(element).to_be_visible(timeout=5000)
            logging.info(f"Clicando em {nome_botao}")
            HumanHelper.mover_mouse_e_clicar(self.page, element)
            return True
        except Exception as e:
            logging.debug(f"Botão {nome_botao} não encontrado: {e}")
            return False

    def _salvar_screenshot_erro(self, contexto):
        try:
            timestamp = int(time.time())
            screenshot_path = str(config.LOGS_DIR / f"erro_{contexto}_{timestamp}.png")
            self.page.screenshot(path=screenshot_path)
            logging.info(f"Screenshot salvo em {screenshot_path}")
        except Exception as e:
            logging.warning(f"Erro ao salvar screenshot: {e}")

    def _verificar_solicitacao_2fa(self):
        """
        Verifica se a página está solicitando o código 2FA.
        Agora de forma condicional: 
        1. Verifica se a URL é de login/cas.
        2. Verifica visibilidade real dos elementos.
        """
        url_atual = self.page.url.lower()
        
        # Se já estivermos em URLs de serviço, ignorar 2FA
        if "cpopg/open.do" in url_atual or "show.do" in url_atual:
            logging.info(f"URL de serviço detectada ({url_atual}), pulando verificação de 2FA.")
            return False

        # Só faz sentido buscar 2FA se estivermos no fluxo de login (CAS)
        if "sajcas/login" not in url_atual and "sajcas/tributos" not in url_atual:
            logging.debug(f"URL atual ({url_atual}) não é de login CAS, pulando 2FA.")
            return False

        code_input_selectors = [
            "input[name='codigo']", 
            "input[id='codigo']", 
            "input[placeholder*='código']", 
            "input[type='text'][maxlength='6']"
        ]
        
        for selector in code_input_selectors:
            locator = self.page.locator(selector)
            if locator.count() > 0 and locator.first.is_visible():
                logging.info(f"Elemento de input 2FA detectado e visível: {selector}")
                return True
        
        # Verificação extra por texto ou botão de envio
        text_selectors = ["text=código", "text=autenticação", "button[id='btnEnviarCodigo']"]
        for selector in text_selectors:
            locator = self.page.locator(selector).first
            if locator.count() > 0 and locator.is_visible():
                logging.info(f"Texto ou botão de 2FA detectado e visível: {selector}")
                return True
                
        return False
    
    def _processar_2fa(self) -> None:
        """
        Coordena a obtenção e submissão do código de Segundo Fator de Autenticação (2FA).
        """
        try:
            logging.info("Iniciando processo de autenticação 2FA...")
            HumanHelper.esperar_humano(2.0, 3.5)
            
            solicitar_button_selectors = ["button[id='btnEnviarCodigo']", "button:has-text('Enviar código')", "button:has-text('Solicitar código')"]
            for selector in solicitar_button_selectors:
                if self.page.locator(selector).count() > 0:
                    logging.info(f"Solicitando código 2FA via botão: {selector}")
                    HumanHelper.mover_mouse_e_clicar(self.page, self.page.locator(selector))
                    HumanHelper.esperar_humano(4.0, 6.0)
                    break
            
            logging.info("Buscando código 2FA no email...")
            HumanHelper.esperar_humano(3.0, 5.0)
            
            try:
                with ImapHandler() as imap:
                    codigo = imap.get_2fa_code()
                
                if not codigo:
                    logging.error("Falha ao obter código 2FA")
                    self._fechar_navegador_seguro()
                    raise LoginException("Não foi possível capturar o código 2FA no email após várias tentativas")
                
                logging.info(f"Código 2FA obtido: {codigo}")
                
            except LoginException:
                raise
            except Exception as e:
                logging.error(f"Erro crítico no IMAP: {e}")
                self._fechar_navegador_seguro()
                raise LoginException(f"Erro ao acessar servidor de email para 2FA: {e}")
            
            HumanHelper.esperar_humano(2.0, 4.0)
            self._inserir_e_confirmar_codigo_2fa(codigo)
            
        except TribunalException:
            raise
        except Exception as e:
            logging.error(f"Erro ao processar 2FA: {e}")
            self._fechar_navegador_seguro()
            raise LoginException(f"Falha inesperada no processo 2FA: {e}")
    
    def _inserir_e_confirmar_codigo_2fa(self, codigo: str) -> None:
        """
        Insere o código de 6 dígitos recebido por e-mail e confirma a autenticação.
        """
        try:
            logging.info("Inserindo código 2FA...")
            HumanHelper.esperar_humano(1.5, 2.5)
            HumanHelper.scroll_suave(self.page, 100)
            
            code_input_selectors = ["input[name='codigo']", "input[id='codigo']", "input[placeholder*='código']", "input[type='text'][maxlength='6']"]
            if not self._preencher_campo(code_input_selectors, codigo, "código 2FA"):
                raise LoginException("Campo de entrada do código 2FA não localizado")
            
            HumanHelper.esperar_humano(1.5, 3.0)
            
            submit_button_selectors = ["button[id='btnEnviarToken']", "button[type='submit']:has-text('Enviar')", "button.spwBotaoDefault", "button:has-text('Enviar')", "button[type='submit']"]
            
            confirmado = False
            for selector in submit_button_selectors:
                if self.page.locator(selector).count() > 0:
                    logging.info(f"Confirmando código via botão: {selector}")
                    try:
                        with self.page.expect_navigation(timeout=45000):
                            HumanHelper.mover_mouse_e_clicar(self.page, self.page.locator(selector))
                        confirmado = True
                        break
                    except TimeoutError:
                        logging.warning("Timeout ao aguardar navegação pós-2FA, tentando clique simples")
                        HumanHelper.mover_mouse_e_clicar(self.page, self.page.locator(selector))
                        confirmado = True
                        break
                    except Exception as e:
                        logging.error(f"Erro ao tentar navegação: {e}")
                        HumanHelper.mover_mouse_e_clicar(self.page, self.page.locator(selector))
                        confirmado = True
                        break
            
            if not confirmado:
                raise LoginException("Botão de confirmação do 2FA não localizado ou indisponível")
            
            logging.info("Aguardando processamento pós-2FA...")
            HumanHelper.esperar_humano(4.0, 6.0)

            if not self._tratar_status_breakpoint(tentativas=3):
                 logging.warning("Página pós-2FA instável, prosseguindo com cautela")
            
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=40000)
                self.page.wait_for_load_state("networkidle", timeout=30000)
            except Exception as e:
                logging.warning(f"Erro ao aguardar estado da página: {e}")
            
            if self._verificar_erro_pagina():
                raise LoginException("Portal reportou erro interno imediatamente após login/2FA")
            
            try:
                self.page.wait_for_selector("input[id='numeroDigitoAnoUnificado']", timeout=2000)
                logging.info("✓ Login completo via 2FA!")
            except Exception:
                pass
            
        except TribunalException:
            raise
        except Exception as e:
            logging.error(f"Erro ao inserir/confirmar código 2FA: {e}")
            self._salvar_screenshot_erro("2fa_confirmacao")
            # Distinguir crash de infra (retentarável) de erro de lógica 2FA
            erro_str = str(e).lower()
            if any(k in erro_str for k in ("target crashed", "session closed", "target closed", "connection refused", "browser has been closed")):
                raise BrowserCrashException("_inserir_e_confirmar_codigo_2fa", e)
            raise LoginException(f"Falha na submissão do 2FA: {e}")

    def _fechar_navegador_seguro(self):
        try:
            logging.info("🔒 Iniciando encerramento forçado do navegador...")
            
            # 1. Tentar fechar páginas específicas primeiro
            for attr in ['page_autos', 'page']:
                if hasattr(self, attr):
                    p = getattr(self, attr)
                    if p:
                        try: p.close()
                        except: pass
            
            # 2. Fechar o contexto (browser) - No Playwright persistente, self.browser é o Context
            if hasattr(self, 'browser') and self.browser:
                try: 
                    # Tenta fechar todas as páginas vinculadas ao contexto antes
                    for p in self.browser.pages:
                        try: p.close()
                        except: pass
                    self.browser.close()
                except: pass
            
            # 3. Parar o motor do Playwright (Crucial para liberar o lock do diretório de perfil)
            if hasattr(self, 'playwright') and self.playwright:
                try: self.playwright.stop()
                except: pass
            
            # 4. Aguardar o SO finalizar o processo Chromium e liberar o lock do perfil.
            # Sem esse delay, uma nova instância pode tentar usar o perfil antes que o
            # processo anterior seja completamente encerrado pelo sistema operacional,
            # resultando em fallback para perfil temporário (abre aba 'about:blank').
            time.sleep(1)
            
            # Limpar referências para evitar vazamento de memória e reuso acidental
            self.page = None
            self.browser = None
            self.playwright = None
            
            logging.info("✅ Navegador e processos Playwright encerrados com sucesso.")
        except Exception as e:
            logging.warning(f"⚠️ Erro ao encerrar processos do navegador: {e}")

    def _verificar_erro_pagina(self):
        erro_selectors = ["text=Código inválido", "text=Código expirado", "text=Erro", "text=STATUS_BREAKPOINT", "text=Ah, não!", "text=Ah, não", ".erro", ".mensagem-erro", "[role='alert']"]
        for selector in erro_selectors:
            if self.page.locator(selector).count() > 0 and self.page.locator(selector).is_visible():
                logging.error(f"Erro detectado na página: {selector}")
                return True
        return False

    def pesquisar_processo(self) -> None:
        """
        Realiza a pesquisa do número unificado (CNJ) no portal portal cpopg.
        Lança ProcessoNaoEncontradoException se o tribunal informar que os autos não existem.
        """
        def func():
            print("\n" + "="*80)
            print("🔎 PESQUISANDO PROCESSO")
            print("="*80)
            
            print(f"📋 Número do processo: {self.numero_processo}")
            
            self._preencher_numero_processo()
            
            print("⏳ Aguardando processamento pós-consulta...")
            self.page.wait_for_timeout(2000)
            
            # Verificação de sucesso via URL
            if "show.do" in self.page.url:
                print("✅ URL de detalhes detectada (show.do)")
            else:
                print(f"ℹ️ URL atual: {self.page.url}")
            
            print("🔍 Verificando mensagens de erro na tela...")
            try:
                # Verificar se apareceu mensagem de erro (timeout curto pois a página já deve estar carregada)
                erro_locator = self.page.locator("text=Não foi possível realizar a consulta")
                if erro_locator.is_visible(timeout=2000):
                    print("❌ ERRO: Tribunal retornou erro na consulta")
                    raise ProcessoNaoEncontradoException(self.numero_processo)
            except ProcessoNaoEncontradoException:
                raise
            except Exception as e:
                logging.debug(f"Aviso silencioso ao verificar mensagem de falha: {e}")
            
            print("✅ Processo encontrado (fluxo de pesquisa concluído)!")
            print("="*80 + "\n")

        self.tentar(func, "pesquisar_processo")

    
    def _preencher_numero_processo(self) -> None:
        """
        Preenche os campos de número unificado e foro no formulário de busca.
        """
        try:
            logging.info(f"Preenchendo número do processo: {self.numero_processo}")
            numero_limpo = self.numero_processo.strip()
            
            # Padrão CNJ TJSP: NNNNNNN-DD.YYYY.8.26.OOOO
            import re
            match_cnj = re.match(r"(?P<principal>\d{7}-\d{2}\.\d{4})\.8\.26\.(?P<foro>\d{4})", numero_limpo)
            
            if match_cnj:
                numero_principal = match_cnj.group("principal")
                foro = match_cnj.group("foro")
            else:
                # Fallback se não for o padrão exato com 8.26
                partes = numero_limpo.split('.')
                if len(partes) >= 4:
                    foro = partes[-1]
                    # Pega tudo exceto as duas últimas partes (.8.26)
                    numero_principal = '.'.join(partes[:-3]) if len(partes) > 4 else '.'.join(partes[:-1])
                else:
                    numero_principal = numero_limpo
                    foro = ""
            
            self.page.wait_for_timeout(1000)
            campo_principal = self.page.locator("#numeroDigitoAnoUnificado")
            
            if campo_principal.count() > 0:
                # Usar digitação humana para disparar eventos AJAX corretamente (keyup, change, blur)
                HumanHelper.digitar_como_humano(campo_principal, numero_principal)
                self.page.wait_for_timeout(500)
                
                # Navegar até o campo de Foro (pulando o 8.26 que já vem preenchido)
                self.page.keyboard.press("Tab")
                self.page.wait_for_timeout(300)
                
                if foro:
                    # O campo foro pode ser o próximo após Tab ou ter um ID específico
                    campo_foro = self.page.locator("#foroNumeroUnificado")
                    if campo_foro.count() > 0:
                        HumanHelper.digitar_como_humano(campo_foro, foro)
                        # Forçar evento de 'blur' final
                        self.page.keyboard.press("Tab")
                        self.page.wait_for_timeout(800)
                
                botao_consultar = self.page.locator("input#botaoConsultarProcessos[type='submit'][value='Consultar']")
                if botao_consultar.count() == 0:
                    botao_consultar = self.page.locator("#botaoConsultarProcessos")
                
                if botao_consultar.count() > 0:
                    try:
                        with self.page.expect_navigation(timeout=60000):
                            HumanHelper.mover_mouse_e_clicar(self.page, botao_consultar)
                    except Exception as nav_error:
                        logging.warning(f"Navegação automática não detectada ({nav_error}). Verificando URL...")
                    
                    self.page.wait_for_load_state("domcontentloaded", timeout=30000)
                else:
                    raise TribunalException("Botão 'Consultar' não localizado no formulário de busca")
            else:
                raise PortalIndisponivelException("O campo de busca de processo não carregou (Portal possivelmente lento)")
                
        except TribunalException:
            raise
        except Exception as e:
            logging.error(f"Erro ao preencher número do processo: {e}")
            raise TribunalException(f"Falha técnica ao interagir com formulário de busca: {e}")

    def abrir_visualizacao_autos(self) -> Any:
        """
        Clica no botão 'Visualizar autos' e captura a nova aba (pop-up) da Pasta Digital.
        Tenta 3 estratégias diferentes para mitigar bloqueios de pop-up e lentidão.
        
        Returns:
            Page: A nova página (aba) referente à Pasta Digital.
            
        Raises:
            PortalIndisponivelException: Se a pasta digital não carregar ou o portal falhar.
            TribunalException: Falhas técnicas na interação.
        """
        try:
            print("\n" + "="*80)
            print("📂 INICIANDO ABERTURA DA VISUALIZAÇÃO DE AUTOS")
            print("="*80)
            logging.info("Iniciando abertura da visualização de autos...")
            
            # Aguarda a página carregar completamente
            try:
                self.page.wait_for_load_state('networkidle', timeout=60000)
            except Exception as e:
                logging.warning(f"Timeout (networkidle) ao aguardar página de detalhes: {e}")
            
            # Informações sobre a página atual
            current_url = self.page.url
            if "show.do" not in current_url:
                logging.warning(f"URL atual ({current_url}) não contém 'show.do' (página de detalhes).")

            self.page_autos = None
            
            # ESTRATÉGIA 1: Clique via Playwright (seletores DOM)
            print("\n🖱️ Estratégia 1: Clique Direto (Playwright)...")
            estrategias = [
                Selectors.BOTAO_VISUALIZAR_AUTOS,
                Selectors.BOTAO_VISUALIZAR_AUTOS_ALT,
                Selectors.BOTAO_VISUALIZAR_AUTOS_URL
            ]
            
            # Aguardar explicitamente o botão aparecer para evitar falha de carregamento assíncrono (Ajax)
            try:
                self.page.wait_for_selector(Selectors.BOTAO_VISUALIZAR_AUTOS, state='attached', timeout=5000)
            except Exception:
                try:
                    self.page.wait_for_selector(Selectors.BOTAO_VISUALIZAR_AUTOS_URL, state='attached', timeout=3000)
                except Exception:
                    logging.info("Botões principais não detectados na espera explícita. Iniciando busca ativa...")
            
            sucesso_abertura = False
            for seletor in estrategias:
                try:
                    locator = self.page.locator(seletor)
                    if locator.count() > 0:
                        with self.page.context.expect_page(timeout=15000) as popup_info:
                            locator.click(force=True)
                        self.page_autos = popup_info.value
                        sucesso_abertura = True
                        break
                except Exception:
                    continue
            
            # ESTRATÉGIA 2: Clique via JavaScript (bypass de pop-up blocker)
            if not sucesso_abertura:
                print("\n🖱️ Estratégia 2: Clique via JavaScript...")
                try:
                    with self.page.context.expect_page(timeout=15000) as popup_info:
                        self.page.evaluate("""
                            () => {
                                let link = document.querySelector('#linkPasta') || document.querySelector('#linkPastaAcessibilidade');
                                if (!link) link = document.querySelector('a[href*="abrirPastaDigital.do"]');
                                if (link) {
                                    link.removeAttribute('aria-hidden');
                                    link.style.display = 'inline';
                                    link.click();
                                    return true;
                                }
                                return false;
                            }
                        """)
                    self.page_autos = popup_info.value
                    sucesso_abertura = True
                except Exception:
                    pass

            # ESTRATÉGIA 3: Navegação direta (extrair href e abrir em nova aba)
            if not sucesso_abertura:
                print("\n🖱️ Estratégia 3: Navegação direta via href...")
                try:
                    href = self.page.evaluate('() => document.querySelector("#linkPasta")?.href')
                    if href:
                        self.page_autos = self.page.context.new_page()
                        self.page_autos.goto(href)
                        sucesso_abertura = True
                except Exception:
                    pass
            
            if not sucesso_abertura:
                raise PortalIndisponivelException("Não foi possível localizar ou abrir o link da Pasta Digital.")

            print("   ✅ Popup capturado!")
            logging.info("Popup aberto com sucesso")
            
            # Aguarda o popup carregar as bases
            self.page_autos.wait_for_load_state('domcontentloaded', timeout=45000)
            self.url_pasta_digital = self.page_autos.url
            
            return self.page_autos
        except TribunalException:
            raise
        except Exception as e:
            logging.error(f"ERRO ao abrir visualização dos autos: {type(e).__name__} - {str(e)}")
            self._salvar_screenshot_erro("abrir_visualizacao_autos")
            raise TribunalException(f"Falha técnica ao acessar Pasta Digital: {e}")

    def processar_todos_documentos(self) -> Dict[str, Any]:
        """
        Orquestra o download sequencial de documentos, gerenciando o fluxo entre 
        autos principais e cumprimento de sentença (fluxo duplo).
        
        Returns:
            Dict[str, ResultadoDownload]: Mapeamento do tipo de documento para seu resultado.
            
        Raises:
            TribunalException: Se ocorrer uma falha crítica que impeça o download.
        """
        try:
            print(f"\n{'='*80}")
            print("🚀 INICIANDO PROCESSAMENTO DE DOCUMENTOS (FLUXO DUPLO)")
            print(f"{'='*80}\n")
            
            from classes.processo_context import ProcessoContext
            context = ProcessoContext(self.numero_processo)
            self.contexto_processo = context
            resultados_gerais: Dict[str, Any] = {}

            # Passo 0: Verificar tipo de processo
            # Requisito 1.1: Rolar até o final para localizar a seção 'Incidentes'
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.5)

            header_incidentes = self.page.locator("h2, h3, div").filter(
                has_text=re.compile(r"Incidentes.*execuções de sentenças", re.IGNORECASE)
            )

            if header_incidentes.count() > 0:
                logging.info("Auto-detecção: Autos Principais (Incidentes presentes)")
                context.tipo_inicial = "autos_principais"
            elif self.page.locator(".processoPrinc").count() > 0:
                context.tipo_inicial = "cumprimento"
                logging.info("Auto-detecção: Cumprimento de Sentença (Link para principal presente)")

            # Passo 1: Extrair vínculos e dados básicos
            if context.tipo_inicial == "cumprimento":
                context.numero_autos_principais = self.extrair_autos_principais()
                # CORREÇÃO BUG 1: Quando o ponto de entrada é o CUMPRIMENTO, NÃO extraímos
                # a data de trânsito em julgado daqui. Ela será extraída dos Autos Principais
                # (o processo de origem), que é o correto para o peticionamento de RPV.
                logging.info("⚠️ Tipo inicial = cumprimento. Data de trânsito será extraída dos Autos Principais.")
            else:
                context.numero_cumprimento = self.extrair_cumprimento_sentenca()
                # Para autos_principais como ponto de entrada, extraímos normalmente
                context.data_transito_julgado = self.extrair_data_transito_julgado()
                context.data_ajuizamento = self.extrair_data_ajuizamento()
                if context.data_ajuizamento:
                    logging.info(f"Data do Ajuizamento extraída da tela: {context.data_ajuizamento}")
                if context.data_transito_julgado:
                    logging.info(f"Data de Trânsito em Julgado extraída da tela: {context.data_transito_julgado}")
                
            # Passo 2: Processar primeiro autos
            self.abrir_visualizacao_autos()
            target_page = self.page_autos if self.page_autos else self.page
            pasta_page = PastaDigitalPage(target_page)
            
            pasta_page.aguardar_carregamento_pasta()
            
            res_inicial = pasta_page.baixar_documentos(tipo_processo=context.tipo_inicial)
            resultados_gerais.update(res_inicial)
            
            # Fechar pasta inicial
            if self.page_autos:
                try: self.page_autos.close()
                except: pass
                self.page_autos = None

            # Passo 3: Processar subordinado se existir
            segundo_numero = context.numero_autos_principais if context.tipo_inicial == "cumprimento" else context.numero_cumprimento
            segundo_tipo = "autos_principais" if context.tipo_inicial == "cumprimento" else "cumprimento"
            
            if segundo_numero:
                 print(f"🔄 PROCESSANDO VÍNCULO: {segundo_numero}")
                 self.clicar_seta_voltar()
                 self.numero_processo = segundo_numero
                 self.pesquisar_processo()
                 
                 # Extrair data de trânsito e ajuizamento do vínculo
                 data_vinculo = self.extrair_data_transito_julgado()
                 data_ajuiz_vinculo = self.extrair_data_ajuizamento()
                 
                 if data_ajuiz_vinculo:
                     logging.info(f"Data de Ajuizamento encontrada no vínculo: {data_ajuiz_vinculo}")
                     if context.tipo_inicial == "cumprimento":
                         context.data_ajuizamento = data_ajuiz_vinculo
                         logging.info(f"✅ Data de Ajuizamento dos Autos Principais adotada: {data_ajuiz_vinculo}")
                 
                 if data_vinculo:
                     logging.info(f"Data de Trânsito encontrada no vínculo: {data_vinculo}")
                     if context.tipo_inicial == "cumprimento":
                         # CORREÇÃO BUG 1: quando partimos do cumprimento, o vínculo é o
                         # processo PRINCIPAL → sua data de trânsito é a correta; usamos ela
                         # diretamente sem comparar com a data do cumprimento.
                         context.data_transito_julgado = data_vinculo
                         logging.info(f"✅ Data de Trânsito dos Autos Principais adotada: {data_vinculo}")
                     else:
                         # Partindo dos autos principais, pegar a mais recente
                         context.data_transito_julgado = utils.comparar_datas_recentes(context.data_transito_julgado, data_vinculo)
                         logging.info(f"Data final selecionada (mais recente): {context.data_transito_julgado}")
                 
                 # Documentos adicionais se faltar algo crítico
                 docs_adicionais = []
                 if "decisao" not in resultados_gerais or resultados_gerais["decisao"].status.name != "SUCESSO":
                     logging.info("🧠 Fallback: Decisão não encontrada no primeiro processo. Solicitando nos Autos Principais...")
                     docs_adicionais.append("decisao")
                 
                 try:
                     self.abrir_visualizacao_autos()
                     target_page2 = self.page_autos if self.page_autos else self.page
                     pasta_page2 = PastaDigitalPage(target_page2)
                     pasta_page2.aguardar_carregamento_pasta()
                     
                     res_vinculado = pasta_page2.baixar_documentos(tipo_processo=segundo_tipo, documentos_adicionais=docs_adicionais)
                     for k, v in res_vinculado.items():
                         if v.status.name == "SUCESSO" or k not in resultados_gerais:
                             resultados_gerais[k] = v
                             
                     if self.page_autos:
                         try: self.page_autos.close()
                         except: pass
                         self.page_autos = None
                 except Exception as e_vinculado:
                     logging.warning(f"Não foi possível acessar Autos Vinculados {segundo_numero}: {e_vinculado}")


            return resultados_gerais
            
        except TribunalException:
            raise
        except Exception as e:
            logging.error(f"Erro no orquestrador de documentos: {e}")
            raise TribunalException(f"Falha no processamento de documentos: {e}")
    def fechar_navegador(self) -> None:
        """
        Encerra o navegador e libera os recursos do Playwright com segurança.
        """
        print("🔒 Fechando navegador...")
        self._fechar_navegador_seguro()

    def _tratar_status_breakpoint(self, tentativas: int = 3) -> bool:
        """
        Verifica se a página capturada pelo Playwright sofreu um crash (STATUS_BREAKPOINT) 
        ou outro erro de renderização do navegador. Tenta recarregar a página 
        para recuperar a sessão se possível.

        Args:
            tentativas: Número máximo de recarregamentos permitidos.

        Returns:
            True se a página estiver estável, False se o erro persistir após as tentativas.
        """
        print(f"🔍 Verificando estabilidade da página (até {tentativas} tentativas)...")
        for tentativa in range(1, tentativas + 1):
            try:
                # 1. Verificar Título da Página
                try:
                    titulo = self.page.title()
                except Exception:
                    titulo = ""
                
                url_atual = self.page.url
                crash_detected = False
                
                if "chrome-error" in url_atual or "chrome-extension" in url_atual:
                     crash_detected = True
                     print(f"❌ URL de erro detectada: {url_atual}")
                     logging.warning(f"URL de erro detectada: {url_atual}")

                # 2. Verificar seletores visíveis de erro
                if not crash_detected:
                    erro_selectors = [
                        "text=STATUS_BREAKPOINT", 
                        "text=Aw, Snap!",
                        "text=Ah, não!",
                        "text=Ah, não",
                        "text=A página falhou",
                        "text=Erro ao carregar",
                        "text=Não foi possível acessar esse site"
                    ]
                    
                    for sel in erro_selectors:
                        if self.page.locator(sel).count() > 0 and self.page.locator(sel).is_visible():
                            print(f"❌ Erro de crash detectado na página: {sel}")
                            logging.warning(f"Erro detectado na página via seletor: {sel}")
                            crash_detected = True
                            break
                
                if crash_detected:
                    print(f"⚠️ Página caiu (STATUS_BREAKPOINT/Aw Snap). Recarregando... ({tentativa}/{tentativas})")
                    logging.warning(f"Crash detectado (Tentativa {tentativa}/{tentativas}). Recarregando página...")
                    
                    def handle_dialog(dialog):
                        try:
                            print(f"   💬 Dialog detectado no reload: {dialog.message}")
                            logging.info(f"Dialog detectado no reload: {dialog.message}")
                            dialog.accept()
                        except Exception:
                            pass
                    
                    self.page.on("dialog", handle_dialog)
                    
                    try:
                        self.page.reload()
                        print("   ⏳ Aguardando página recarregar...")
                        self.page.wait_for_load_state("networkidle", timeout=45000)
                        print("   ✅ Página recarregada")
                    except Exception as e_load:
                        print(f"   ⚠️ Erro durante reload: {e_load}")
                        logging.warning(f"Erro durante reload: {e_load}")
                    finally:
                        pass

                    HumanHelper.esperar_humano(3.0, 5.0)
                    continue
                else:
                    print("✅ Página estável")
                    return True

            except Exception as e:
                print(f"❌ Erro ao verificar status da página: {e}")
                logging.error(f"Erro ao verificar status breakpoint: {e}")
                if tentativa < tentativas:
                    print(f"   🔄 Tentando reload preventivo ({tentativa}/{tentativas})...")
                    logging.warning("Tentando reload preventivo por erro na verificação...")
                    try: self.page.reload() 
                    except: pass
                    time.sleep(5)
                pass
                
        print("❌ Página permanece instável após todas as tentativas")
        return False

    def extrair_autos_principais(self) -> Optional[str]:
        """Extrai o número dos autos principais da tag .processoPrinc."""
        try:
            print("🔍 Buscando vínculo com autos principais...")
            locator = self.page.locator(".processoPrinc")
            if locator.count() > 0:
                numero = locator.first.inner_text().strip()
                print(f"✅ Autos principais encontrados: {numero}")
                return numero
            print("⚠️ Link para autos principais não encontrado.")
            return None
        except Exception as e:
            print(f"❌ Erro ao extrair autos principais: {type(e).__name__} - {e}")
            logging.error(f"Erro ao extrair autos principais: {e}")
            return None

    def extrair_cumprimento_sentenca(self) -> Optional[str]:
        """
        Extrai o número do Cumprimento de Sentença.
        Prioriza a seção 'Incidentes, ações incidentais...' e depois as movimentações.
        """
        try:
            # ESTRATÉGIA 1: Procurar na seção de Incidentes (Mais confiável)
            print("🔍 Buscando vínculo na seção 'Incidentes, ações incidentais...'")
            # Seletor robusto: Links que contenham "Cumprimento de Sentença" (ignora case)
            incidentes_links = self.page.locator("a").filter(has_text=re.compile(r"Cumprimento de Sentença", re.IGNORECASE))
            
            count_inc = incidentes_links.count()
            if count_inc > 0:
                print(f"🔎 Encontrados {count_inc} possíveis links de incidente.")
                # Pega o último (mais recente cronologicamente no e-SAJ)
                # Itera de trás para frente para garantir que pegamos um que tenha o número
                for i in range(count_inc - 1, -1, -1):
                    texto_inc = incidentes_links.nth(i).inner_text().strip()
                    # Regex flexível para número CNJ
                    match_inc = re.search(r'(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})', texto_inc)
                    if match_inc:
                        numero = match_inc.group(1)
                        print(f"✅ Cumprimento de sentença encontrado ({i+1}/{count_inc}): {numero}")
                        return numero

            # ESTRATÉGIA 2: Varre a tabela de movimentações em busca de 'Cumprimento de Sentença Iniciada'
            print("🔍 Buscando vínculo com cumprimento de sentença nas movimentações (fallback)...")
            movimentacoes = self.page.locator(".descricaoMovimentacao")
            count = movimentacoes.count()
            
            for i in range(count):
                texto = movimentacoes.nth(i).inner_text()
                if "Cumprimento de Sentença Iniciada" in texto:
                    span_italic = movimentacoes.nth(i).locator("span[style*='italic']")
                    if span_italic.count() > 0:
                        texto_italic = span_italic.first.inner_text()
                        match = re.search(r'(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})', texto_italic)
                        if match:
                            numero = match.group(1)
                            print(f"✅ Cumprimento de sentença encontrado nas movimentações: {numero}")
                            return numero
            
            print("⚠️ Vínculo com cumprimento de sentença não encontrado.")
            return None
        except Exception as e:
            print(f"❌ Erro ao extrair cumprimento de sentença: {type(e).__name__} - {e}")
            logging.error(f"Erro ao extrair cumprimento de sentença: {e}")
            return None

    def extrair_data_transito_julgado(self) -> Optional[str]:
        """
        Busca a data do Trânsito em Julgado nas movimentações do processo.
        Tenta expandir o histórico se necessário e procura por palavras-chave específicas.

        Returns:
            String com a data (DD/MM/AAAA) ou None se não localizada.
        """
        try:
            print("🔍 Buscando data do Trânsito em Julgado nas movimentações...")
            
            # 1. Expandir movimentações se houver botão recolhido
            link_expandir = self.page.locator("#linkmovimentacoes")
            if link_expandir.count() > 0 and link_expandir.is_visible():
                try:
                    link_expandir.click()
                    self.page.wait_for_timeout(1000)
                except: pass

            # 2. Pegar todas as movimentações disponíveis
            movimentacoes = self.page.locator("#tabelaTodasMovimentacoes tr, #tabelaUltimasMovimentacoes tr")
            count = movimentacoes.count()
            
            keywords = [
                "certidão de sua preclusão",
                "certidão de trânsito em julgado",
                "certidão - trânsito em julgado",
                "transito em julgado",
                "trânsito em julgado",
                "certifico e dou fé",
            ]
            
            for i in range(count):
                tr = movimentacoes.nth(i)
                td_data = tr.locator(".dataMovimentacao")
                td_desc = tr.locator(".descricaoMovimentacao")
                
                if td_data.count() > 0 and td_desc.count() > 0:
                    texto_desc_original = td_desc.first.inner_text().strip()
                    texto_desc = texto_desc_original.lower()
                    
                    for kw in keywords:
                        if kw in texto_desc:
                            # Tentar extrair a data de dentro do texto da movimentação (prioridade)
                            import re
                            from datetime import datetime
                            todas_datas = re.findall(r'\b(\d{2}[/.]\d{2}[/.]\d{4})\b', texto_desc_original)
                            if todas_datas:
                                datas_formatadas = [d.replace('.', '/') for d in todas_datas]
                                datas_validas = []
                                for string_d in datas_formatadas:
                                    try:
                                        datas_validas.append(datetime.strptime(string_d, "%d/%m/%Y").date())
                                    except ValueError:
                                        pass
                                if datas_validas:
                                    data_mais_recente = max(datas_validas)
                                    data_coluna = data_mais_recente.strftime("%d/%m/%Y")
                                    print(f"✅ Data de Trânsito em Julgado extraída do texto: {data_coluna}")
                                    return data_coluna
                            
                            # Fallback: Data da coluna de movimentação
                            data_coluna = td_data.first.inner_text().strip()
                            print(f"✅ Data de Trânsito em Julgado ({kw}) extraída da coluna: {data_coluna}")
                            return data_coluna
                            
            return None
        except Exception as e:
            logging.error(f"Erro ao extrair data do trânsito em julgado: {e}")
            return None

    def extrair_data_ajuizamento(self) -> Optional[str]:
        """
        Busca a data do Ajuizamento (Distribuição) do processo nas movimentações.
        Procura pela movimentação ('Distribuído...' / 'Distribuição') ou pega a movimentação mais antiga.
        """
        try:
            print("🔍 Buscando data do Ajuizamento nas movimentações...")
            
            link_expandir = self.page.locator("#linkmovimentacoes")
            if link_expandir.count() > 0 and link_expandir.is_visible():
                try:
                    link_expandir.click()
                    self.page.wait_for_timeout(1000)
                except: pass

            movimentacoes = self.page.locator("#tabelaTodasMovimentacoes tr")
            if movimentacoes.count() == 0:
                movimentacoes = self.page.locator("#tabelaUltimasMovimentacoes tr")
                
            count = movimentacoes.count()
            
            # Buscar de baixo para cima (mais antigas para mais recentes)
            for i in range(count - 1, -1, -1):
                tr = movimentacoes.nth(i)
                td_data = tr.locator(".dataMovimentacao")
                td_desc = tr.locator(".descricaoMovimentacao")
                
                if td_data.count() > 0 and td_desc.count() > 0:
                    texto_desc = td_desc.first.inner_text().strip().lower()
                    if "distribuído" in texto_desc or "distribuição" in texto_desc:
                        data_coluna = td_data.first.inner_text().strip()
                        print(f"✅ Data de Ajuizamento ('{texto_desc[:30]}...') extraída: {data_coluna}")
                        return data_coluna
            
            # Fallback: a data da linha mais antiga (a última da tabela de movimentações)
            if count > 0:
                tr = movimentacoes.nth(count - 1)
                td_data = tr.locator(".dataMovimentacao")
                if td_data.count() > 0:
                    data_coluna = td_data.first.inner_text().strip()
                    print(f"✅ Data de Ajuizamento (Fallback linha mais antiga) extraída: {data_coluna}")
                    return data_coluna
            
            return None
        except Exception as e:
            logging.error(f"Erro ao extrair data do ajuizamento: {e}")
            return None

    def navegar_ate_pasta_digital(self) -> bool:
        """
        Executa o fluxo completo de navegação assistida:
        Login -> Busca de Processo -> Abertura da Pasta Digital.
        Mantém o navegador visível para intervenção humana.
        """
        try:
            print("\n" + "🚀" * 40)
            print("🤖 INICIANDO NAVEGAÇÃO ASSISTIDA ATÉ A PASTA DIGITAL")
            print("🚀" * 40 + "\n")
            
            # 1. Garantir navegador visível
            if not self.browser:
                self.iniciar_navegador(headless=False)
            
            # 2. Acessar Tribunal (já faz login se necessário)
            self.acessar_tribunal()
            
            # 3. Pesquisar Processo
            self.pesquisar_processo()
            
            # 4. Abrir Pasta Digital
            self.abrir_visualizacao_autos()
            
            print("\n" + "✅" * 40)
            print("🎯 PASTA DIGITAL ABERTA COM SUCESSO!")
            print("📂 Agora você pode baixar os arquivos faltantes manualmente no navegador.")
            print("✅" * 40 + "\n")
            
            return True
        except Exception as e:
            print(f"❌ Erro na navegação assistida: {e}")
            logging.error(f"Erro na navegação assistida: {e}")
            return False

    def clicar_seta_voltar(self) -> None:
        """
        Retorna para a tela de consulta processual, garantindo a limpeza dos campos 
        de busca para evitar sobreposição de números.
        
        Raises:
            TribunalException: Se não conseguir retornar à tela inicial.
        """
        try:
            print("⬅️ Voltando para a tela de consulta...")
            seta = self.page.locator("#setaVoltar, .icon-back")
            if seta.count() > 0:
                seta.first.click()
                self.page.wait_for_load_state("networkidle")
                
                # Limpeza explícita dos campos após voltar
                for seletor in ["#numeroDigitoAnoUnificado", "#foroNumeroUnificado"]:
                    campo = self.page.locator(seletor)
                    if campo.count() > 0:
                        campo.fill("")
            else:
                logging.warning("Botão de voltar não encontrado, forçando navegação para URL base.")
                self.page.goto(os.getenv('TRIBUNAL_URL', '')) # Fallback seguro
                
        except Exception as e:
            logging.error(f"Erro ao clicar na seta de voltar: {e}")
            raise TribunalException(f"Não foi possível retornar à tela de busca: {e}")
