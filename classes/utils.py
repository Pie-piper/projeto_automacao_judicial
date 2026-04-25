import locale
import platform
import re
from enum import Enum
from num2words import num2words

def configurar_locale():
    """Configura locale de forma compatível com o SO"""
    try:
        if platform.system() == "Windows":
            locale.setlocale(locale.LC_ALL, 'pt_BR')
        else:
            locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
    except Exception as e:
        print(f"Aviso: Não foi possível configurar locale: {e}")

def formatar_moeda(valor):
    """Formata valor para moeda brasileira (R$ 1.234,56)"""
    if valor is None:
        return "R$ 0,00"
    try:
        # Tenta usar locale
        return locale.currency(valor, grouping=True)
    except (ValueError, TypeError):
        # Fallback manual
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def numero_por_extenso(valor):
    """Converte número para extenso monetário"""
    if valor is None:
        return "zero reais"
    try:
        return num2words(valor, lang='pt_BR', to='currency')
    except Exception as e:
        print(f"Erro ao converter número por extenso: {e}")
        return f"{valor} reais"

def limpar_texto(texto):
    """Remove caracteres especiais que podem quebrar docxtpl"""
    if not texto:
        return ""
    # Remove caracteres de controle, mantém acentos e pontuação básica
    texto = re.sub(r'[^\w\s\.,;:\-\(\)\/]', '', texto)
    return texto.strip()

def configurar_logger(nome_arquivo=None):
    """
    Configura o logger globalmente.
    
    Args:
        nome_arquivo: Caminho do arquivo de log (opcional)
    """
    import logging
    import sys
    
    handlers = [logging.StreamHandler(sys.stdout)]
    if nome_arquivo:
        handlers.append(logging.FileHandler(nome_arquivo, encoding='utf-8'))
        
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=handlers,
        force=True
    )

class TipoProcesso(Enum):
    CUMPRIMENTO = "CUMPRIMENTO"
    AUTOS_PRINCIPAIS = "AUTOS_PRINCIPAIS"
    DESCONHECIDO = "DESCONHECIDO"


def normalizar_numero_processo(numero):
    """Remove pontos, hífens e espaços do número do processo"""
    if not numero:
        return ""
    return re.sub(r'[^\d]', '', numero)

def parse_currency(val) -> float:
    """Converte string de valor monetário brasileiro para float"""
    if not val:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    v_str = str(val).replace('R$', '').strip()
    if ',' in v_str and '.' in v_str:
        v_str = v_str.replace('.', '').replace(',', '.')
    elif ',' in v_str:
        v_str = v_str.replace(',', '.')
    try:
        return float(v_str)
    except ValueError:
        return 0.0

def comparar_datas_recentes(data1, data2):
    """
    Compara duas datas no formato DD/MM/AAAA e retorna a mais recente.
    """
    from datetime import datetime
    try:
        d1 = datetime.strptime(str(data1), "%d/%m/%Y") if data1 else None
        d2 = datetime.strptime(str(data2), "%d/%m/%Y") if data2 else None
        
        if d1 and d2:
            return str(data1) if d1 >= d2 else str(data2)
        return str(data1) if d1 else str(data2) if d2 else None
    except Exception:
        return str(data1) if data1 else str(data2) if data2 else None

def data_por_extenso(data_str):
    """Converte data DD/MM/AAAA para formato extenso (Ex: 21 de maio de 2019)"""
    if not data_str:
        return ""
    try:
        from datetime import datetime
        # Suporta tanto DD/MM/AAAA quanto formatos de banco com Z
        limpo = str(data_str).split('T')[0].strip().replace('.', '/')
        d = datetime.strptime(limpo, "%d/%m/%Y")
        meses = [
            "janeiro", "fevereiro", "março", "abril", "maio", "junho",
            "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"
        ]
        return f"{d.day} de {meses[d.month - 1]} de {d.year}"
    except Exception:
        return str(data_str)

# Palavras que indicam verba, categoria de cálculo ou termos técnicos de processo 
# — NUNCA um nome de pessoa em contexto de Hall de Autores.
PALAVRAS_VERBA = {
    "VALOR", "PARCELA", "PARCELAS", "SALÁRIO", "SALARIO", "PLANTÃO", "PLANTAO",
    "FÉRIAS", "FERIAS", "ABONO", "GRATIFICAÇÃO", "GRATIFICACAO", "ADICIONAL",
    "INDENIZAÇÃO", "INDENIZACAO", "REMUNERAÇÃO", "REMUNERACAO", "VENCIMENTO",
    "SUBSÍDIO", "SUBSIDIO", "HORA", "HORAS", "DIÁRIA", "DIARIA", "ANUAL",
    "MENSAL", "VINCENDA", "VINCENDAS", "VENCIDA", "VENCIDAS", "PRESTAÇÃO",
    "PRESTACAO", "DIFERENÇA", "DIFERENCA", "CORREÇÃO", "CORRECAO", "JUROS",
    "ATUALIZAÇÃO", "ATUALIZACAO", "ENCARGO", "ENCARGOS", "BENEFÍCIO", "BENEFICIO",
    "LEI", "ART", "ARTIGO", "PARÁGRAFO", "PARAGRAFO", "DECRETO",
    "SUBTOTAL", "BRUTO", "LÍQUIDO", "LIQUIDO", "DEVIDO", "DEVIDA",
    "REQUERENTE", "REQUERENTES", "AUTOR", "AUTORES", "EXEQUENTE", "EXEQUENTES",
    "REQUERIDO", "REQUERIDOS", "RÉU", "REU", "REUS", "EXECUTADO", "EXECUTADOS",
    "CPF", "RG", "CNPJ", "ENDEREÇO", "ENDERECO", "NOME", "ESTADO", "CIVIL",
    "PROFISSAO", "PROFISSÃO", "NACIONALIDADE", "BRASILEIRO", "BRASILEIRA",
    "SOLTEIRO", "SOLTEIRA", "CASADO", "CASADA", "DIVORCIADO", "DIVORCIADA",
    "ENFERMEIRO", "ENFERMEIRA", "TÉCNICO", "TECNICO", "MOTORISTA", "AUXILIAR",
}

def parece_nome_pessoa(texto: str) -> bool:
    """
    Heurística para distinguir um nome de pessoa de uma descrição de verba
    ou termos técnicos de processo.
    """
    if not texto:
        return False
        
    texto_upper = texto.upper().strip()
    palavras = texto_upper.split()

    # Se vazio ou muito curto
    if not palavras or len(texto_upper) < 5:
        return False

    # Se começa com número (ex: 12 PARCELAS) → não é nome
    if palavras and palavras[0][0].isdigit():
        return False

    # Frases-gatilho que indicam verba (checagem como substring)
    frases_verba = [
        "VALOR DO", "VALOR DA", "VALOR DE", "VALOR DAS", "VALOR DOS",
        "PARCELAS", "PLANTÃO S/", "PLANTAO S/", "FÉRIAS E", "FERIAS E",
        "ADICIONAL DE", "ADICIONAL DO", "ADICIONAL DA", "LEI Nº", "LEI N.",
        "13° SALÁRIO", "13 SALARIO", "13º SALÁRIO", "ARTIGO ", "ART. ",
        "NOME COMPLETO", "ESTADO CIVIL",
    ]
    for frase in frases_verba:
        if frase in texto_upper:
            return False

    # Contar quantas palavras do texto são palavras de verba/bloqueadas
    preposicoes_nome = {"DE", "DA", "DO", "DOS", "DAS", "E"}
    palavras_bloqueadas_encontradas = sum(
        1 for p in palavras
        if p not in preposicoes_nome and p in PALAVRAS_VERBA
    )
    
    # Se tem 1+ palavra bloqueada em um nome de 2-3 palavras, é suspeito.
    if palavras_bloqueadas_encontradas >= 1:
        return False

    # Nomes muito longos (> 7 palavras) provavelmente são descrições ou lixo
    if len(palavras) > 7:
        return False

    # Mínimo de 2 palavras para ser nome
    if len(palavras) < 2:
        return False

    return True
