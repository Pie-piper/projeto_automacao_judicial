import pdfplumber
import re
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import classes.utils as utils

# --- CONFIGURAÇÃO DE LOG ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PDFExtractor")

class PDFExtractor:
    def __init__(self, caminho_pdf: Path):
        self.caminho_pdf = caminho_pdf
        self.logger = logging.getLogger(f"PDFExtractor_{caminho_pdf.name}")

    def extrair_todos_dados(self) -> Dict[str, Any]:
        """Extrai todos os dados possíveis do PDF."""
        try:
            with pdfplumber.open(self.caminho_pdf) as pdf:
                texto_completo = ""
                for page in pdf.pages:
                    texto_completo += page.extract_text() or ""
                
                # Extrair metadados básicos
                dados = {
                    'cidade': self.extrair_cidade(texto_completo),
                    'vara': self.extrair_vara(texto_completo),
                    'valor': self.extrair_valor(texto_completo),
                    'partes': self.extrair_partes(texto_completo),
                    'paginas': self.extrair_intervalo_paginas(texto_completo),
                    'data_liberacao': self.extrair_data_liberacao(texto_completo)
                }
                return dados
        except Exception as e:
            self.logger.error(f"Erro ao abrir PDF {self.caminho_pdf}: {e}")
            return {}

    def extrair_cidade(self, texto):
        """Busca a comarca no texto"""
        match = re.search(r'COMARCA DE\s+([A-ZÀ-Ú ]+)', texto, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    def extrair_vara(self, texto):
        """Busca a vara no texto"""
        match = re.search(r'(\d+ª\s+VARA\s+[A-ZÀ-Ú ]+)', texto, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    def extrair_data_liberacao(self, texto):
        """
        Extrai a data de liberação dos autos (carimbo lateral).
        Ex: "Este documento é cópia do original, liberado nos autos em 18/11/2024 às 17:35"
        """
        match = re.search(r'liberado nos autos em\s*(\d{2}/\d{2}/\d{4})', texto, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    def extrair_intervalo_paginas(self, texto):
        """Busca o intervalo de páginas se disponível no texto."""
        match = re.search(r'fls\.\s*(\d+)\s*a\s*(\d+)', texto, flags=re.IGNORECASE)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
        return None

    def extrair_partes(self, texto):
        """Extrai exequente e executado"""
        partes = {'autor': None, 'reu': None}
        
        # Limpar texto para facilitar regex (remover quebras e excesso de espaços)
        texto_limpo = re.sub(r'\s+', ' ', texto)
        
        # Padrões comuns no TJSP
        # REQUERENTE: [NOME]
        pattern = r'(?:EXEQUENTE|REQUERENTE|AUTOR)[A-Z]*\s*[:\.]?\s*([A-ZÀ-Ú ]+?)(?:\s+[A-Z]{2,}:|$)'
        match_autor = re.search(pattern, texto_limpo, flags=re.IGNORECASE)
        partes['autor'] = match_autor.group(1).strip() if match_autor else None
        
        # Réu removido conforme solicitação
        partes['reu'] = None 
        
        return partes
    
    def extrair_valor(self, texto):
        """Extrai valor do processo com regex robusta"""
        match = re.search(r'R\$\s*([0-9\.\s]+,\d{2})', texto)
        if match:
            valor_str = match.group(1)
            valor_str = re.sub(r'[^0-9,]', '', valor_str)
            valor_str = valor_str.replace(',', '.')
            try:
                return float(valor_str)
            except ValueError:
                pass
    
    def extrair_valor_planilha(self):
        """
        Extrai o valor TOTAL da Planilha de Cálculo, DESCONTANDO honorários se necessário.
        REQUISITO 5.2: Descontar honorários sucumbenciais do valor bruto do autor.
        """
        try:
            with pdfplumber.open(self.caminho_pdf) as pdf:
                texto_completo = ""
                for page in pdf.pages:
                    texto_completo += page.extract_text() or ""
                
                valor_bruto = 0.0
                
                # 1. Padrão Especial: Tabela "Total das Partes"
                linhas = texto_completo.split('\n')
                for linha in linhas:
                    if 'Total das Partes' in linha or 'TOTAL DAS PARTES' in linha.upper():
                        numeros = re.findall(r'\b\d{1,3}(?:\.\d{3})*,\d{2}\b', linha)
                        if numeros:
                            valor_str = numeros[-1].replace('.', '').replace(',', '.')
                            try:
                                valor_bruto = float(valor_str)
                                break
                            except ValueError: pass
                
                if valor_bruto == 0.0:
                    # Padrão 1: SUBTOTAL, TOTAL BRUTO ou TOTAL seguido de R$ e valor
                    pattern1 = r'(?:SUBTOTAL|TOTAL\s*BRUTO|TOTAL DEVIDO PELA EXECUTADA|TOTAL|TOTAL GERAL)\s*R?\$?\s*([\d.,]+)'
                    match = re.search(pattern1, texto_completo, re.IGNORECASE)
                    if match:
                        valor_str = match.group(1).replace('.', '').replace(',', '.')
                        try: valor_bruto = float(valor_str)
                        except: pass
                
                if valor_bruto > 0:
                    # 2. Detectar Honorários (Sucumbência) para DESCONTO
                    valor_honorarios = self.extrair_valor_honorarios(texto_completo)
                    if valor_honorarios > 0 and valor_honorarios < valor_bruto:
                        self.logger.info(f"   💰 Honorários detectados: R$ {valor_honorarios:.2f}. Descontando do Bruto: R$ {valor_bruto:.2f}")
                        return valor_bruto - valor_honorarios
                    
                    return valor_bruto
                    
        except Exception as e:
            self.logger.error(f"Erro ao extrair valor da planilha: {e}")
        return None

    def extrair_valor_honorarios(self, texto_ocr: str = "") -> float:
        """Busca o valor de honorários sucumbenciais (patrono) na planilha."""
        texto = (texto_ocr or "").upper()
        if not texto:
            try:
                with pdfplumber.open(self.caminho_pdf) as pdf:
                    for page in pdf.pages: texto += (page.extract_text() or "").upper() + "\n"
            except: pass
        
        # Padrões comuns para honorários advocatícios / sucumbência
        padroes = [
            r'(?:HONORÁRIOS|HONORARIOS|SUCUMBÊNCIA|SUCUMBENCIA|DEVIDO AO PATRONO).*?R?\$?\s*([\d.,]+)',
            r'TOTAL\s+HONOR[ÁA]RIOS.*?R?\$?\s*([\d.,]+)'
        ]
        
        for p in padroes:
            match = re.search(p, texto, re.IGNORECASE)
            if match:
                try:
                    valor_str = match.group(1).replace('.', '').replace(',', '.')
                    return float(valor_str)
                except: continue
        return 0.0

    def extrair_data_transito_julgado(self):
        """
        Extrai a data de trânsito em julgado da Certidão.
        REQUISITO: A data pode estar no texto ou na informação do topo (carimbo).
        """
        try:
             with pdfplumber.open(self.caminho_pdf) as pdf:
                 # 1. Tentar carimbo do topo (mais fácil/confiável segundo o cliente)
                 primeira_pag = pdf.pages[0]
                 area_topo = (0, 0, primeira_pag.width, primeira_pag.height * 0.3)
                 texto_topo = primeira_pag.crop(area_topo).extract_text() or ""
                 
                 match_topo = re.search(r'Tr[âa]nsito em [Jj]ulgado em:?\s*(\d{2}/\d{2}/\d{4})', texto_topo, re.IGNORECASE)
                 if match_topo:
                     self.logger.info(f"✅ Data trânsito encontrada no topo: {match_topo.group(1)}")
                     return match_topo.group(1)
                 
                 # 2. Tentar texto completo
                 texto_completo = ""
                 for page in pdf.pages:
                     texto_completo += page.extract_text() or ""
                 
                 match_texto = re.search(r'Certifico.*?tr[âa]nsito em julgado.*?em\s*(\d{2}/\d{2}/\d{4})', texto_completo, re.IGNORECASE | re.DOTALL)
                 if match_texto:
                     self.logger.info(f"✅ Data trânsito encontrada no texto: {match_texto.group(1)}")
                     return match_texto.group(1)
                 
                 # Fallback genérico
                 match_generico = re.search(r'tr[âa]nsito em julgado.*?(\d{2}/\d{2}/\d{4})', texto_completo, re.IGNORECASE | re.DOTALL)
                 if match_generico:
                     return match_generico.group(1)
        except Exception as e:
            self.logger.warning(f"Erro ao extrair data de trânsito: {e}")
        return None

    def extrair_partes_valores_planilha(self):
        """Extrai a lista de exequentes e seus valores individuais da Planilha de Cálculo."""
        lista_exequentes = []
        try:
            with pdfplumber.open(self.caminho_pdf) as pdf:
                texto_completo = ""
                for page in pdf.pages:
                    texto_completo += page.extract_text() or ""
                
                linhas = texto_completo.split('\n')
                for linha in linhas:
                    linha = linha.strip()
                    match = re.search(r'^([A-ZÀ-Ú ]{5,})\s+.*?([\d,]{1,15}(?:\.\d{3})*,\d{2})$', linha)
                    if match:
                        nome = match.group(1).strip()
                        valor_str = match.group(2).replace('.', '').replace(',', '.')
                        if "TOTAL" not in nome.upper() and len(nome.split()) >= 2:
                            try:
                                valor = float(valor_str)
                                lista_exequentes.append({'nome': nome, 'valor': valor})
                            except ValueError: pass
        except Exception as e:
            self.logger.error(f"Erro ao extrair partes da planilha: {e}")
        return lista_exequentes

    def extrair_paginas_fls(self):
        """Extrai o intervalo de folhas (fls.) do documento."""
        paginas = []
        try:
            with pdfplumber.open(self.caminho_pdf) as pdf:
                for page in pdf.pages:
                    area_topo = (0, 0, page.width, page.height * 0.2)
                    texto_topo = page.crop(area_topo).extract_text() or ""
                    match = re.search(r'fls\.?\s*(\d+)', texto_topo, flags=re.IGNORECASE)
                    if match: paginas.append(int(match.group(1)))
            if paginas:
                min_p, max_p = min(paginas), max(paginas)
                return str(min_p) if min_p == max_p else f"{min_p}-{max_p}"
        except Exception as e:
            self.logger.warning(f"Erro ao extrair numeração de folhas: {e}")
        return None

    def extrair_data_nascimento(self):
        """Extrai a data de nascimento de um documento pessoal."""
        try:
            with pdfplumber.open(self.caminho_pdf) as pdf:
                texto = ""
                for page in pdf.pages: texto += page.extract_text() or ""
                match = re.search(r'(?:Nasc.*?|Nascimento.*?|Data\s+de\s+nasc.*?)\s*(\d{2}/\d{2}/\d{4})', texto, re.IGNORECASE)
                if match: return match.group(1)
        except Exception as e:
            self.logger.warning(f"Erro ao extrair data nascimento: {e}")
        return None

    def analisar_homologacao(self, texto_ocr: str = "") -> str:
        """
        Analisa o texto da decisão para identificar se a impugnação foi acolhida ou rejeitada.
        """
        texto = (texto_ocr or "").upper()
        if not texto:
            try:
                with pdfplumber.open(self.caminho_pdf) as pdf:
                    for page in pdf.pages: texto += (page.extract_text() or "").upper() + "\n"
            except: pass

        # Palavras-chave para status
        if any(w in texto for w in ["ACOLHO A IMPUGNACAO", "ACOLHO A MANIFESTACAO", "PROCEDENTE A IMPUGNACAO"]):
            return "acolhida"
        if any(w in texto for w in ["REJEITO A IMPUGNACAO", "IMPROCEDENTE A IMPUGNACAO", "REJEITO A MANIFESTACAO"]):
            return "rejeitada"
        
        return "nao_detectada"

    def extrair_data_base_calculo(self) -> Optional[str]:
        """
        Extrai a data base / data do cálculo da planilha.
        Busca por termos como "Data-base", "Atualizado até", "Cálculo elaborado em".
        """
        try:
            with pdfplumber.open(self.caminho_pdf) as pdf:
                texto_completo = ""
                for page in pdf.pages:
                    texto_completo += page.extract_text() or ""
                
                # Padrões comuns em planilhas judiciais (Melhorado para aceitar MM/AAAA e labels curtas)
                padroes = [
                    r'(?:Data[- ](?:do )?c[áa]lculo|Data[- ]base|C[áa]lculo elaborado em|Elaborado em|Atualizado at[ée])\s*:?\s*(\d{2}/\d{2}/\d{4}|\d{2}/\d{4})',
                    r'(\d{2}/\d{2}/\d{4}|\d{2}/\d{4})\s*-\s*Data-base',
                    r'VALORES ATUALIZADOS AT[ÉE]\s*(\d{2}/\d{2}/\d{4}|\d{2}/\d{4})'
                ]
                
                for padrao in padroes:
                    match = re.search(padrao, texto_completo, re.IGNORECASE)
                    if match:
                        data_encontrada = match.group(1)
                        # Se vier apenas MM/AAAA, padroniza para 01/MM/AAAA para evitar erros de data
                        if len(data_encontrada) == 7: 
                            data_encontrada = f"01/{data_encontrada}"
                            
                        self.logger.info(f"✅ Data base encontrada: {data_encontrada}")
                        return data_encontrada
                
                # Fallback: se houver muitas datas, a mais recente pode ser a base do cálculo
                todas_datas = re.findall(r'\b(\d{2}/\d{2}/\d{4})\b', texto_completo)
                if todas_datas:
                    # Filtra datas que parecem ser do ano do processo ou próximo
                    from datetime import datetime
                    datas_val = []
                    for d_str in todas_datas:
                        try:
                            d_obj = datetime.strptime(d_str, "%d/%m/%Y")
                            # Ignora datas muito antigas (mais de 20 anos)
                            if d_obj.year > (datetime.now().year - 20):
                                datas_val.append(d_str)
                        except: pass
                    
                    if datas_val:
                        # Retorna a mais recente presente no documento
                        from classes.utils import comparar_datas_recentes
                        data_final = datas_val[0]
                        for d in datas_val[1:]:
                            data_final = comparar_datas_recentes(data_final, d)
                        return data_final

        except Exception as e:
            self.logger.warning(f"Erro ao extrair data base do cálculo: {e}")
        return None