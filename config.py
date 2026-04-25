import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import yaml

# --- CONFIGURAÇÃO DE DIRETÓRIOS ---
if getattr(sys, 'frozen', False):
    # Se estiver rodando como .exe, o diretório é onde o .exe está (ou _MEIPASS)
    BASE_DIR = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent)).resolve()
    # Diretório para arquivos graváveis (em AppData do usuário para evitar erro de permissão no Program Files)
    USER_DATA_DIR = Path(os.getenv('APPDATA')) / "RPV Automacao"
else:
    # Se estiver rodando como .py
    BASE_DIR = Path(__file__).parent.resolve()
    USER_DATA_DIR = BASE_DIR

# Nome padronizado para a pasta de dados (sem espaços para evitar problemas de caminho)
APP_NAME = "RPV_Automacao"

if getattr(sys, 'frozen', False):
    # Se estiver rodando como .exe, APPDATA é obrigatório para escrita
    appdata = os.getenv('APPDATA')
    if appdata:
        USER_DATA_DIR = Path(appdata) / APP_NAME
    else:
        # Fallback para pasta do usuário se APPDATA não existir (raro no Windows)
        USER_DATA_DIR = Path.home() / APP_NAME
else:
    USER_DATA_DIR = BASE_DIR

# Carregar variáveis de ambiente (especificando o caminho do .env)
# Primeiro tenta na BASE_DIR, depois tenta na pasta do executável (para modo frozen)
env_path = BASE_DIR / ".env"
if not env_path.exists() and getattr(sys, 'frozen', False):
    # Tentar na pasta do exe
    pasta_exe = Path(sys.executable).parent
    env_path = pasta_exe / ".env"
    import logging
    logging.info(f"Modo executável: Procurando .env em {env_path}")

if env_path.exists():
    load_dotenv(dotenv_path=env_path)
    import logging
    logging.info(f"Arquivo .env carregado com sucesso de: {env_path}")
else:
    if getattr(sys, 'frozen', False):
         import logging
         logging.warning("Arquivo .env NÃO encontrado na pasta do executável.")

# Carregar config.yaml
def load_config():
    config_path = BASE_DIR / "config.yaml"
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            import logging
            logging.error(f"Erro ao carregar config.yaml: {e}")
            return {}
    return {}

yaml_config = load_config()

# Versão do Sistema
VERSION = "1.0.2"

# Repositório GitHub para Atualizações
GITHUB_USER = yaml_config.get('atualizacao', {}).get('github_user', 'Pie-piper')
GITHUB_REPO = yaml_config.get('atualizacao', {}).get('github_repo', 'projeto_automacao_judicial')
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"

# Diretórios Base (Já definido acima no bloco de diretórios)
DOWNLOADS_DIR = USER_DATA_DIR / yaml_config.get('caminhos', {}).get('downloads_dir', 'downloads')
TEMP_DIR = DOWNLOADS_DIR / "temp"
PROCESSOS_DIR = USER_DATA_DIR / yaml_config.get('caminhos', {}).get('processos_dir', 'processos')
LOGS_DIR = USER_DATA_DIR / yaml_config.get('caminhos', {}).get('logs_dir', 'logs')
# TEMPLATES_DIR deve ficar na BASE_DIR pois é apenas leitura e vem com o pacote
TEMPLATES_DIR = BASE_DIR / yaml_config.get('caminhos', {}).get('templates_dir', 'peticionamento/templates')

# Criar diretórios se não existirem
USER_DATA_DIR.mkdir(exist_ok=True, parents=True)
DOWNLOADS_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)
PROCESSOS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
# TEMPLATES_DIR não criamos pois deve existir com arquivos

# Configurações do Tribunal
TRIBUNAL_URL = yaml_config.get('tribunal', {}).get('url', "https://esaj.tjsp.jus.br/cpopg/open.do")
TIMEOUT_PADRAO = yaml_config.get('tribunal', {}).get('timeout_padrao', 30000)
TIMEOUT_NAVEGACAO = yaml_config.get('tribunal', {}).get('timeout_navegacao', 45000)
TENTATIVAS_RETRY = yaml_config.get('tribunal', {}).get('tentativas_retry', 3)

# Credenciais (Prioridade: config.yaml > .env > variáveis ambiente)
# Primeiro tenta .env, depois usa yaml que vem no bundle
LOGIN_TJSP = os.getenv("LOGIN_TJSP") or yaml_config.get('credenciais', {}).get('login', "")
SENHA_TJSP = os.getenv("SENHA_TJSP") or yaml_config.get('credenciais', {}).get('senha', "")

# Se credenciais estiverem vazias no modo frozen, tentar ler de arquivo externo na pasta do exe
if getattr(sys, 'frozen', False):
    if not LOGIN_TJSP or not SENHA_TJSP:
        # Tentar ler de arquivo externo config_externa.yaml na pasta do exe
        pasta_exe = Path(sys.executable).parent
        config_externa = pasta_exe / "config_externa.yaml"
        if config_externa.exists():
            try:
                with open(config_externa, 'r', encoding='utf-8') as f:
                    ext_config = yaml.safe_load(f) or {}
                    LOGIN_TJSP = ext_config.get('credenciais', {}).get('login', LOGIN_TJSP)
                    SENHA_TJSP = ext_config.get('credenciais', {}).get('senha', SENHA_TJSP)
            except Exception:
                pass

# Validação de credenciais obrigatórias
# Em modo frozen (.exe), não bloqueia - apenas avisa para não travar a inicialização
if getattr(sys, 'frozen', False):
    if not LOGIN_TJSP or not SENHA_TJSP:
        import logging
        logging.warning("Credenciais do TJSP nao configuradas. Edite config.yaml ou crie config_externa.yaml na pasta do executavel.")
else:
    # Em modo desenvolvimento, ainda exige credenciais
    if not LOGIN_TJSP or not SENHA_TJSP:
        raise ValueError("Credenciais do TJSP nao configuradas. Edite config.yaml ou .env")

# Credenciais de Email (para 2FA - Prioridade: .env > yaml)
EMAIL_USER = os.getenv("EMAIL_USER") or yaml_config.get('email', {}).get('user', "")
EMAIL_PASS = os.getenv("EMAIL_PASS") or yaml_config.get('email', {}).get('password', "")

if not EMAIL_USER or not EMAIL_PASS:
    import logging
    logging.warning("Credenciais de email não configuradas. 2FA pode não funcionar.")

# Chave de Licença (Deve ser a mesma para o gerador e para o app)
# Usando a chave que já está no .env e no gerador como fallback padrão
DEFAULT_LICENSE_KEY = "8vcgDu3dPSnYujPHP12uADCJ2slnAeIcHUZLyhX0WaM="
LICENSE_SECRET_KEY = os.getenv("LICENSE_SECRET_KEY") or DEFAULT_LICENSE_KEY

# Supabase (Configurações fixas para licenciamento SaaS)
SUPABASE_URL = (os.getenv("SUPABASE_URL") or yaml_config.get('supabase', {}).get('url', "https://gfihdhlkgzpdlliscxfg.supabase.co")).strip()
SUPABASE_KEY = (os.getenv("SUPABASE_KEY") or yaml_config.get('supabase', {}).get('key', "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdmaWhkaGxrZ3pwZGxsaXNjeGZnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcwODQ4MDIsImV4cCI6MjA5MjY2MDgwMn0.PPpnP3KbmA9lkkndScWsZUq5IxwVKQ6he6lzrgqXZC4")).strip()

# Configurações IMAP
IMAP_SERVER = yaml_config.get('email', {}).get('imap_server', "mail.gruposobrinhoadv.com.br")
IMAP_PORT = yaml_config.get('email', {}).get('imap_port', 993)
TIMEOUT_2FA = yaml_config.get('email', {}).get('timeout_2fa', 60)

# Caminhos de Executáveis
# Agora com detecção automática + fallback para config.yaml + fallback para caminhos comuns
def encontrar_tesseract():
    """Detecta automaticamente o caminho do Tesseract OCR"""
    # Tenta do config.yaml primeiro
    if yaml_config.get('caminhos', {}).get('tesseract_path'):
        return yaml_config['caminhos']['tesseract_path']
    
    # Detecção automática em caminhos comuns do Windows
    caminhos_comuns = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    
    for caminho in caminhos_comuns:
        if Path(caminho).exists():
            return caminho
    
    # Fallback para caminho padrão
    return r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def encontrar_poppler():
    """Detecta automaticamente o caminho do Poppler"""
    # Tenta do config.yaml primeiro
    if yaml_config.get('caminhos', {}).get('poppler_path'):
        return yaml_config['caminhos']['poppler_path']
    
    # Detecção automática em caminhos comuns do Windows
    caminhos_comuns = [
        Path(r"C:\Program Files\poppler-24.02.0\Library\bin"),
        Path(r"C:\Program Files\poppler-23.11.0\Library\bin"),
        Path(r"C:\poppler\Library\bin"),
    ]
    
    for caminho in caminhos_comuns:
        if caminho.exists():
            return str(caminho)
    
    # Fallback para caminho padrão
    return r"C:\Program Files\poppler-24.02.0\Library\bin"

TESSERACT_PATH = encontrar_tesseract()
POPPLER_PATH = encontrar_poppler()

def verificar_caminhos():
    """Verifica existência dos caminhos e registra warnings"""
    import logging
    paths_necessarios = {
        'Tesseract': Path(TESSERACT_PATH),
        'Poppler': Path(POPPLER_PATH),
    }
    for nome, caminho in paths_necessarios.items():
        if not caminho.exists():
            logging.warning(f"{nome} não encontrado em: {caminho}. Algumas funcionalidades podem não funcionar.")

def verificar_tesseract_version():
    """Verifica versão do Tesseract OCR e idioma português instalado"""
    import logging
    import subprocess
    import os
    
    tesseract_exe = Path(TESSERACT_PATH)
    tessdata_dir = tesseract_exe.parent.parent / "tessdata"
    
    resultado = {
        'instalado': False,
        'versao': None,
        'idioma_portugues': False,
        'problemas': []
    }
    
    if not tesseract_exe.exists():
        resultado['problemas'].append(f"Tesseract não encontrado em: {TESSERACT_PATH}")
        for problema in resultado['problemas']:
            logging.warning(f"[Tesseract] {problema}")
        return resultado
    
    resultado['instalado'] = True
    
    try:
        proc = subprocess.run(
            [str(tesseract_exe), '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if proc.returncode == 0:
            primeira_linha = proc.stdout.split('\n')[0]
            resultado['versao'] = primeira_linha.strip()
            
            # Verificar versão mínima recomendada (5.x)
            if '5.' in primeira_linha:
                logging.info(f"[Tesseract] Versão OK: {primeira_linha.strip()}")
            elif '4.' in primeira_linha:
                resultado['problemas'].append("Tesseract 4.x detectado. Recomenda-se 5.x para melhor precisão.")
                logging.warning(f"[Tesseract] {resultado['problemas'][-1]}")
            else:
                resultado['problemas'].append("Tesseract muito antigo. Atualize para versão 5.x")
                logging.error(f"[Tesseract] {resultado['problemas'][-1]}")
        
    except Exception as e:
        resultado['problemas'].append(f"Erro ao verificar versão: {e}")
        logging.warning(f"[Tesseract] {resultado['problemas'][-1]}")
    
    # Verificar idioma português
    if tessdata_dir.exists():
        lang_file = tessdata_dir / "por.traineddata"
        if lang_file.exists():
            resultado['idioma_portugues'] = True
            logging.info("[Tesseract] Idioma português (por) instalado")
        else:
            resultado['problemas'].append("Idioma português (por.traineddata) não encontrado")
            logging.warning(f"[Tesseract] {resultado['problemas'][-1]}")
            logging.info("[Tesseract] Baixe em: https://github.com/tesseract-ocr/tessdata/raw/main/por.traineddata")
    else:
        resultado['problemas'].append(f"Pasta tessdata não encontrada em: {tessdata_dir}")
        logging.warning(f"[Tesseract] {resultado['problemas'][-1]}")
    
    return resultado

verificar_caminhos()
TESSERACT_INFO = verificar_tesseract_version()

# Nomes de Arquivos
ARQUIVO_DECISAO = yaml_config.get('arquivos', {}).get('decisao', "DECISAO.pdf")
ARQUIVO_PLANILHA = yaml_config.get('arquivos', {}).get('planilha', "PLANILHA_DE_CALCULO.pdf")
ARQUIVO_PROCURACAO = yaml_config.get('arquivos', {}).get('procuracao', "PROCURACAO.pdf")

# Parâmetros
LIMITE_RPV = yaml_config.get('parametros', {}).get('limite_rpv', 16904.80)
TAMANHO_MINIMO_PDF = yaml_config.get('parametros', {}).get('tamanho_minimo_pdf', 100)
IMAP_SEARCH_LIMIT = yaml_config.get('email', {}).get('search_limit', 10)

# Dados Padrão para o Espelho (Escritório)
BANCO_PADRAO = yaml_config.get('escritorio', {}).get('banco', "001")
AGENCIA_PADRAO = yaml_config.get('escritorio', {}).get('agencia', "8058")
CONTA_PADRAO = yaml_config.get('escritorio', {}).get('conta', "262-3")
CNPJ_PADRAO = yaml_config.get('escritorio', {}).get('cnpj', "37.610.350/0001-80")

# Prefixos para nomes de arquivos baixados
PREFIXOS = {
    'instrumentoprocuracao': '03_PROCURACAO',
    'decisao': '04_DECISAO',
    'planilhacalculo': '02_PLANILHA',
    'peticao': '01_PETICAO',
    'diversos': '05_DOC_DIVERSO'
}

# Arquivos necessários para verificação
ARQUIVOS_NECESSARIOS = [
    ARQUIVO_DECISAO,
    ARQUIVO_PLANILHA,
    ARQUIVO_PROCURACAO,
    "CNPJ.pdf",
    "Contrato_Social.pdf"
]

# --- LIMPEZA DE ARQUIVOS ANTIGOS ---
# Diretório de screenshots
SCREENSHOTS_DIR = USER_DATA_DIR / yaml_config.get('caminhos', {}).get('screenshots_dir', 'screenshots_erro')
SCREENSHOTS_DIR.mkdir(exist_ok=True)

def limpar_arquivos_antigos():
    """Remove screenshots e logs de erro com mais de 7 dias para poupar espaço no disco."""
    import time
    dias_limite = 7
    agora = time.time()
    limite_tempo = agora - (dias_limite * 86400)

    # Considera tanto o LOGS_DIR atual quanto a pasta SCREENSHOTS_DIR
    diretorios_para_limpar = [LOGS_DIR, SCREENSHOTS_DIR]
    
    for dir_path in diretorios_para_limpar:
        if not dir_path.exists():
            continue
        try:
            # Varre arquivos png e log
            for ext in ("*.png", "*.log"):
                for arquivo in dir_path.glob(ext):
                    if arquivo.is_file():
                        try:
                            if arquivo.stat().st_mtime < limite_tempo:
                                arquivo.unlink()
                        except Exception:
                            pass
        except Exception:
            pass

# Executa a limpeza silenciosamente toda vez que o config é carregado
limpar_arquivos_antigos()