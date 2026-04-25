class Selectors:
    # Login / Inicial
    BOTAO_CONSULTAR_PROCESSOS = "#botaoConsultarProcessos"
    
    # Menu Hamburguer
    MENU_HAMBURGUER = "a.header__navbar__menu-hamburger"
    
    # Menu Peticionamento
    CLASS_ITEM_MENU = "a.aside-nav__main-menu__list__item__link"
    GENERICO_PROCESSO_DIGITAL = "Peticionamento Eletrônico"
    TEXTO_PETICIONAMENTO_1_GRAU = r"Peticionamento Eletr.nico de 1.? Grau"
    TEXTO_PETICIONAMENTO_INTERMEDIARIA = r"Peticionamento de intermediaria de 1.? Grau Requisit.rios"
    BOTAO_MENU_REQUISITORIOS = "a.aside-nav__main-menu__list__item__link[href*='petpgreq']"
    TEXTO_PETICIONAMENTO_INTERMEDIARIA_ALT = r"Petiç.o Intermedi.ria de 1.? Grau"
    
    # Modais e Popups
    BOTAO_CANCELAR_MODAL_FORM = "dialog button:has-text('Cancelar'), *[role='dialog'] button:has-text('Cancelar')"
    MODAL_AVISO = "#popupModalDiv"
    MENSAGEM_ALERT = "#mensagemAlert"
    BOTAO_OK_MODAL = "dialog#popupModalDiv button:has-text('Ok')"
    
    # Formulário de Peticionamento
    BOTAO_INFORMAR_PROCESSO = "#botaoEditarDadosBasicos" 
    BOTAO_INFORMAR_PROCESSO_NATIVE = "[data-testid='button-div-processo-open']"
    CAMPO_NUMERO_PROCESSO = "#numero_processo"          # Novo ID conforme HTML real do e-SAJ
    BOTAO_SELECIONE_PDF = "button[data-testid='button-file-uploader']"
    INPUT_FILE_UPLOAD = "input[type='file']"

    # Classificação e Dados Suplementares
    BOTAO_CLASSIFICAR = "button[data-testid='button-classificacao-open']"
    BOTAO_CONFIRMAR_TIPO = "button[data-testid='button-classificacao-confirmar']"
    BOTAO_INFORMAR_SUPLEMENTARES = "[data-testid='button-dados-suplementares-open']"
    BOTAO_CONFIRMAR_SUPLEMENTARES = "button[data-testid='button-dados-suplementares-confirmar']"
    CAMPO_VALOR_SUPLEMENTAR = "input[name='valor_valor_incontroverso']" # Guessing based on common patterns, but will use keyboard as requested
    
    # --- Categorização de Documentos Pós-Upload ---
    DOC_TIPO_INPUT_PREFIX = "#select-input-tipo-documento-"
    DOC_PARTE_INPUT_PREFIX = "#select-input-parte-documento-"

    # ============================================
    # PASTA DIGITAL
    # ============================================
    BOTAO_VISUALIZAR_AUTOS = "#linkPasta"
    BOTAO_VISUALIZAR_AUTOS_ALT = "#linkPastaAcessibilidade"
    BOTAO_VISUALIZAR_AUTOS_URL = "a[href*='abrirPastaDigital.do']"
    
    BOTAO_PRIMEIRA_PAGINA = "#primeiraPaginaButton"
    BOTAO_PAGINA_ANTERIOR = "#paginaAnteriorButton"
    CAMPO_PAGINA_ATUAL = "#campoPaginaAtual"
    NUMERO_TOTAL_PAGINAS = "#numTotalPaginas"
    
    ARVORE_PRINCIPAL = "#arvore_principal"
    ARVORE_DEPENDENTES = "#arvore_dependentes"
    ARVORE_APENSOS = "#arvore_apensos"
    
    BOTAO_BAIXAR_PDF = "#salvarButton"
    BOTAO_SALVAR_DOCUMENTO = "#btnDownloadDocumento"
    BOTAO_CANCELAR_MODAL_DOWNLOAD = "#btnCancelarProcessamento"
