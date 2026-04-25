"""
Utilitário para conversão de valores numéricos para extenso em português brasileiro.
"""

from num2words import num2words
import re

def valor_por_extenso(valor):
    """
    Converte um valor numérico para extenso em português brasileiro.
    
    Args:
        valor: float ou string representando valor monetário
        
    Returns:
        str: Valor por extenso (ex: "dezesseis mil duzentos e noventa e seis reais e setenta e cinco centavos")
    """
    try:
        # Se for string, tentar converter
        if isinstance(valor, str):
            # Remove R$, espaços, e converte vírgula para ponto
            valor_limpo = re.sub(r'[R$\s]', '', valor)
            valor_limpo = valor_limpo.replace('.', '').replace(',', '.')
            valor = float(valor_limpo)
        
        # Converter para float se necessário
        valor = float(valor)
        
        # Separar reais e centavos
        reais = int(valor)
        centavos = int(round((valor - reais) * 100))
        
        # Converter para extenso
        if reais == 0:
            texto_reais = "zero reais"
        elif reais == 1:
            texto_reais = "um real"
        else:
            texto_reais = num2words(reais, lang='pt_BR') + " reais"
        
        if centavos == 0:
            return texto_reais
        elif centavos == 1:
            texto_centavos = "um centavo"
        else:
            texto_centavos = num2words(centavos, lang='pt_BR') + " centavos"
        
        return f"{texto_reais} e {texto_centavos}"
        
    except Exception as e:
        print(f"Erro ao converter valor para extenso: {e}")
        return "[VALOR POR EXTENSO]"


def formatar_valor_brasileiro(valor):
    """
    Formata valor numérico para padrão brasileiro (R$ 1.234,56).
    
    Args:
        valor: float
        
    Returns:
        str: Valor formatado
    """
    try:
        valor = float(valor)
        return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    except:
        return "R$ 0,00"
