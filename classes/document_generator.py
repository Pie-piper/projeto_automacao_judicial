from docxtpl import DocxTemplate
from docx2pdf import convert
from pathlib import Path
import config
from classes import utils
import logging

class DocumentGenerator:
    def __init__(self, pasta_processo):
        self.pasta_processo = Path(pasta_processo)
        utils.configurar_locale()
        self.logger = logging.getLogger(f"DocGenerator_{self.pasta_processo.name}")
    
    def preparar_contexto_subestabelecimento(self, dados):
        """Prepara dados para template de subestabelecimento"""
        valor = dados.get('valor', 0)
        
        # Obtém limite RPV (prioridade: dados validados > config)
        limite_rpv = dados.get('limite_rpv', config.LIMITE_RPV)
        limite_fmt = utils.formatar_moeda(limite_rpv)
        limite_extenso = utils.numero_por_extenso(limite_rpv)
        
        # Lógica do Texto Condicional
        if valor > limite_rpv:
            # Caso ultrapasse
            texto_status_rpv = (
                f", ultrapassando, portanto, o limite de RPV estabelecido para o Estado de São Paulo, "
                f"que é de {limite_fmt} ({limite_extenso})"
            )
        else:
            # Caso esteja dentro
            texto_status_rpv = (
                f", encontrando-se dentro do limite de RPV estabelecido para o Estado de São Paulo, "
                f"que é de {limite_fmt} ({limite_extenso})"
            )

        contexto = {
            'cidade': utils.limpar_texto(dados.get('cidade', '')).upper(),
            'vara': utils.limpar_texto(dados.get('vara', '')).upper(),
            'autor': utils.limpar_texto(dados.get('partes', {}).get('autor', '')),
            'reu': utils.limpar_texto(dados.get('partes', {}).get('reu', '')),
            'numero_processo': dados.get('numero_processo', ''),
            'valor': utils.formatar_moeda(valor),
            'valor_extenso': utils.numero_por_extenso(valor),
            'data_atual': dados.get('data_atual', ''),
            'texto_status_rpv': texto_status_rpv,
            
            # Tags Universais de Limite RPV
            'valor_limite_rpv': limite_fmt,
            'valor_limite_rpv_extenso': limite_extenso,
            
            # Tags de Renúncia (Valor excedente)
            'valor_renuncia': "R$ 0,00",
            'valor_renuncia_extenso': "zero reais"
        }
        
        # Calcular renúncia se houver excesso
        if valor > limite_rpv:
            diferenca = valor - limite_rpv
            contexto['valor_renuncia'] = utils.formatar_moeda(diferenca)
            contexto['valor_renuncia_extenso'] = utils.numero_por_extenso(diferenca)
            
        return contexto
    
    def preparar_contexto_renuncia(self, dados):
        """Prepara dados para template de renúncia"""
        contexto = {
            'cidade': utils.limpar_texto(dados.get('cidade', '')).upper(),
            'vara': utils.limpar_texto(dados.get('vara', '')).upper(),
            'autor': utils.limpar_texto(dados.get('partes', {}).get('autor', '')),
            'reu': utils.limpar_texto(dados.get('partes', {}).get('reu', '')),
            'numero_processo': dados.get('numero_processo', ''),
            'data_atual': dados.get('data_atual', '')
        }
        return contexto
    
    def gerar_documento_word(self, template_path, contexto, output_name):
        """Gera documento Word a partir de template"""
        try:
            doc = DocxTemplate(template_path)
            doc.render(contexto)
            
            # Salvar na pasta 'gerados' se possível, senão na raiz do processo
            # Assumindo que FileManager criou a estrutura, mas aqui recebemos pasta_processo
            # Se pasta_processo for a raiz, tentamos salvar em 'gerados'
            output_dir = self.pasta_processo / "gerados"
            if not output_dir.exists():
                output_dir = self.pasta_processo
            
            output_path = output_dir / f"{output_name}.docx"
            doc.save(output_path)
            
            self.logger.info(f"✓ Documento Word gerado: {output_name}.docx")
            return output_path
        except Exception as e:
            self.logger.error(f"✗ Erro ao gerar {output_name}.docx: {e}")
            return None
    
    def converter_word_para_pdf(self, word_path, pdf_name=None):
        """Converte documento Word para PDF"""
        try:
            if pdf_name is None:
                pdf_name = word_path.stem + ".pdf"
            
            pdf_path = word_path.parent / pdf_name
            
            # Tenta converter usando docx2pdf (requer Word instalado no Windows)
            convert(str(word_path), str(pdf_path))
            
            self.logger.info(f"✓ PDF gerado: {pdf_name}")
            return pdf_path
        except Exception as e:
            self.logger.error(f"✗ Erro ao converter para PDF: {e}")
            self.logger.warning("Verifique se o Microsoft Word está instalado ou tente usar outra biblioteca.")
            return None
    
    def gerar_subestabelecimento(self, dados):
        """Gera Subestabelecimento (Word + PDF)"""
        template = config.TEMPLATES_DIR / "Modelo_Subestabelecimento.docx"
        
        # Validação de existência do template
        if not template.exists():
            erro_msg = (
                f"Template de Subestabelecimento não encontrado!\n"
                f"Caminho esperado: {template.absolute()}\n"
                f"Verifique se o arquivo existe na pasta 'templates' e tente novamente."
            )
            self.logger.error(erro_msg)
            raise FileNotFoundError(erro_msg)
        
        contexto = self.preparar_contexto_subestabelecimento(dados)
        
        word_path = self.gerar_documento_word(template, contexto, "Subestabelecimento")
        if word_path:
            return self.converter_word_para_pdf(word_path, "Subestabelecimento.pdf")
        return None
    
    def gerar_renuncia(self, dados):
        """Gera Renúncia (Word + PDF)"""
        template = config.TEMPLATES_DIR / "Modelo_Renuncia.docx"
        
        # Validação de existência do template
        if not template.exists():
            erro_msg = (
                f"Template de Renúncia não encontrado!\n"
                f"Caminho esperado: {template.absolute()}\n"
                f"Verifique se o arquivo existe na pasta 'templates' e tente novamente."
            )
            self.logger.error(erro_msg)
            raise FileNotFoundError(erro_msg)
        
        contexto = self.preparar_contexto_renuncia(dados)
        
        word_path = self.gerar_documento_word(template, contexto, "Renuncia")
        if word_path:
            return self.converter_word_para_pdf(word_path, "Renuncia.pdf")
        return None
    
        return None
    
    def preparar_contexto_geral(self, dados):
        """
        Prepara um contexto unificado com todos os campos disponíveis.
        Útil para quando o usuário seleciona um template arbitrário.
        """
        # Reutiliza lógica do subestabelecimento que já é bem completa e adiciona extras se necessário
        contexto = self.preparar_contexto_subestabelecimento(dados)
        
        # Adicionar campos extras se houver (ex: placeholder específico de renúncia se não estiver lá)
        # No momento, subestabelecimento já cobre: cidade, vara, autor, reu, processo, valor, extenso, data, texto_rpv
        
        # Adicionar dados de páginas manualmente extraídos também
        # Como o contexto de subestabelecimento só pegava dados.get('valor'), vamos garantir que tudo de 'dados' vá para o contexto
        # Mas cuidado com objetos complexos
        for k, v in dados.items():
            if k not in contexto and isinstance(v, (str, int, float)):
                contexto[k] = v
                
        return contexto

    def gerar_documento_customizado(self, template_path, dados):
        """
        Gera um documento a partir de um template escolhido pelo usuário.
        """
        try:
            path_obj = Path(template_path)
            if not path_obj.exists():
                raise FileNotFoundError(f"Template não encontrado: {template_path}")
                
            nome_saida = path_obj.stem
            contexto = self.preparar_contexto_geral(dados)
            
            self.logger.info(f"Gerando documento customizado: {nome_saida}")
            
            word_path = self.gerar_documento_word(path_obj, contexto, nome_saida)
            
            if word_path:
                return self.converter_word_para_pdf(word_path, f"{nome_saida}.pdf")
            return None
            
        except Exception as e:
            self.logger.error(f"Erro ao gerar documento customizado: {e}")
            return None

    def gerar_todos_documentos(self, dados, templates_selecionados=None):
        """
        Gera documentos. 
        Args:
            templates_selecionados (list): Lista de caminhos de templates escolhidos.
        """
        documentos_gerados = []
        substabelecimento_gerado = False
        
        if templates_selecionados:
            for template_path in templates_selecionados:
                doc = self.gerar_documento_customizado(template_path, dados)
                if doc:
                    documentos_gerados.append(doc)
                    if "Substabelecimento" in Path(template_path).name:
                        substabelecimento_gerado = True
            
            # Garante que o Substabelecimento seja gerado se não foi selecionado
            # O usuário pediu "modelo de substabelecimento já deve vir preenchido... e convertido"
            if not substabelecimento_gerado:
                 self.logger.info("Gerando Substabelecimento padrão (obrigatório)...")
                 sub = self.gerar_subestabelecimento(dados)
                 if sub:
                     documentos_gerados.append(sub)
        
        else:
            # Comportamento antigo (fallback)
            sub = self.gerar_subestabelecimento(dados)
            if sub:
                documentos_gerados.append(sub)
            
            ren = self.gerar_renuncia(dados)
            if ren:
                documentos_gerados.append(ren)
        
        return documentos_gerados