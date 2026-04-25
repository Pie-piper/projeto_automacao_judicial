import pikepdf
from pathlib import Path
import config
import logging

class PDFMerger:
    def __init__(self, pasta_processo):
        self.pasta_processo = Path(pasta_processo)
        self.logger = logging.getLogger(f"PDFMerger_{self.pasta_processo.name}")
        
        # Mapeamento de onde procurar arquivos
        self.pastas_busca = [
            self.pasta_processo,
            self.pasta_processo / "originais",
            self.pasta_processo / "gerados",
            self.pasta_processo / "processados"
        ]

    def _encontrar_arquivo(self, nome_arquivo):
        """Procura arquivo nas pastas padrão"""
        for pasta in self.pastas_busca:
            caminho = pasta / nome_arquivo
            if caminho.exists():
                return caminho
        return None

    def mesclar_pdfs(self, lista_pdfs, nome_saida):
        """Mescla múltiplos PDFs em um único arquivo usando pikepdf"""
        pdf_final = pikepdf.Pdf.new()
        
        try:
            arquivos_encontrados = 0
            for nome_pdf in lista_pdfs:
                caminho = self._encontrar_arquivo(nome_pdf)
                
                if caminho:
                    try:
                        # Abre o PDF (pikepdf lida bem com criptografia se senha for vazia)
                        pdf = pikepdf.Pdf.open(caminho)
                        pdf_final.pages.extend(pdf.pages)
                        arquivos_encontrados += 1
                        self.logger.info(f"  + Adicionado: {nome_pdf}")
                    except pikepdf.PasswordError:
                        self.logger.error(f"  ✗ Erro: {nome_pdf} está protegido por senha.")
                    except Exception as e:
                        self.logger.error(f"  ✗ Erro ao abrir {nome_pdf}: {e}")
                else:
                    self.logger.warning(f"  ✗ Não encontrado: {nome_pdf}")
            
            if arquivos_encontrados > 0:
                output_path = self.pasta_processo / "gerados" / nome_saida
                # Se pasta gerados não existir (caso não tenha sido criada pelo FileManager), usa raiz
                if not output_path.parent.exists():
                    output_path = self.pasta_processo / nome_saida
                
                pdf_final.save(output_path)
                self.logger.info(f"✓ PDF mesclado criado: {output_path.name}")
                return output_path
            else:
                self.logger.error("Nenhum arquivo válido encontrado para mesclar.")
                return None
                
        except Exception as e:
            self.logger.error(f"✗ Erro ao mesclar PDFs: {e}")
            return None
        finally:
            pdf_final.close()

    def criar_contrato_completo(self):
        """Cria Contrato.pdf mesclando Subestabelecimento + CNPJ + Contrato Social"""
        arquivos = [
            "Subestabelecimento.pdf",
            "CNPJ.pdf",
            "Contrato_Social.pdf"
        ]
        
        self.logger.info("Mesclando arquivos do Contrato (Ordem: Subst -> CNPJ -> Contrato)...")
        return self.mesclar_pdfs(arquivos, "Contrato.pdf")
    
    def criar_juntada_final(self, dados_autos):
        """Cria PDF final da juntada com todos os documentos necessários"""
        arquivos = [
            "Peticao_Inicial.pdf",
            "RG_CPF.pdf",
            config.ARQUIVO_PROCURACAO,
            "Sentenca.pdf",
            "Certidao_Transito_Julgado.pdf",
            config.ARQUIVO_DECISAO,
            config.ARQUIVO_PLANILHA,
            "Contrato.pdf"
        ]
        
        self.logger.info("Criando juntada final...")
        return self.mesclar_pdfs(arquivos, "Contrato.pdf")
    
    def criar_pdf_contrato(self, documento_gerado_path):
        """
        Cria juntada para peticionamento eletrônico na ordem:
        1. Documento gerado (ex: Substabelecimento.pdf)
        2. CNPJ.pdf
        3. CONTRATO SOCIAL.pdf
        
        Args:
            documento_gerado_path: Path do documento gerado (já preenchido)
        
        Returns:
            Path do PDF mesclado ou None se falhar
        """
        import config
        
        pdf_final = pikepdf.Pdf.new()
        arquivos_adicionados = 0
        
        try:
            # 1. Documento gerado (já está em processados/)
            if documento_gerado_path and documento_gerado_path.exists():
                pdf = pikepdf.Pdf.open(documento_gerado_path)
                pdf_final.pages.extend(pdf.pages)
                arquivos_adicionados += 1
                self.logger.info(f"  + Adicionado: {documento_gerado_path.name}")
            else:
                self.logger.error(f"  ✗ Documento gerado não encontrado: {documento_gerado_path}")
            
            # 2. CNPJ.pdf (template estático)
            cnpj_path = config.TEMPLATES_DIR / "CNPJ.pdf"
            if cnpj_path.exists():
                pdf = pikepdf.Pdf.open(cnpj_path)
                pdf_final.pages.extend(pdf.pages)
                arquivos_adicionados += 1
                self.logger.info(f"  + Adicionado: CNPJ.pdf")
            else:
                self.logger.warning(f"  ✗ Não encontrado: CNPJ.pdf em {cnpj_path}")
            
            # 3. CONTRATO SOCIAL.pdf (template estático)
            contrato_path = config.TEMPLATES_DIR / "CONTRATO SOCIAL.pdf"
            if contrato_path.exists():
                pdf = pikepdf.Pdf.open(contrato_path)
                pdf_final.pages.extend(pdf.pages)
                arquivos_adicionados += 1
                self.logger.info(f"  + Adicionado: CONTRATO SOCIAL.pdf")
            else:
                self.logger.warning(f"  ✗ Não encontrado: CONTRATO SOCIAL.pdf em {contrato_path}")
            
            if arquivos_adicionados > 0:
                output_path = self.pasta_processo / "processados" / "Contrato.pdf"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                pdf_final.save(output_path)
                self.logger.info(f"✅ Contrato para peticionamento criado: {output_path.name}")
                return output_path
            else:
                self.logger.error("❌ Nenhum arquivo foi adicionado à juntada")
                return None
                
        except Exception as e:
            self.logger.error(f"✗ Erro ao criar juntada de peticionamento: {e}")
            return None
        finally:
            pdf_final.close()
    
    def extrair_paginas_especificas(self, pdf_origem, paginas, nome_saida):
        """Extrai páginas específicas de um PDF"""
        try:
            caminho_origem = self._encontrar_arquivo(pdf_origem)
            
            if not caminho_origem:
                self.logger.error(f"✗ Arquivo não encontrado: {pdf_origem}")
                return None
            
            pdf = pikepdf.Pdf.open(caminho_origem)
            pdf_novo = pikepdf.Pdf.new()
            
            for num_pagina in paginas:
                if 0 <= num_pagina < len(pdf.pages):
                    pdf_novo.pages.append(pdf.pages[num_pagina])
                else:
                    self.logger.warning(f"⚠ Página {num_pagina + 1} não existe em {pdf_origem}")
            
            output_path = self.pasta_processo / "gerados" / nome_saida
            if not output_path.parent.exists():
                output_path = self.pasta_processo / nome_saida
                
            pdf_novo.save(output_path)
            self.logger.info(f"✓ Páginas extraídas: {nome_saida}")
            return output_path
            
        except Exception as e:
            self.logger.error(f"✗ Erro ao extrair páginas: {e}")
            return None
    
    def organizar_documentos_peticao(self):
        """Organiza todos os documentos para peticionamento"""
        documentos = {
            'contrato': "Contrato.pdf",
            'juntada': "Juntada_Completa.pdf",
            'renuncia': "Renuncia.pdf"
        }
        
        documentos_prontos = {}
        for nome_chave, nome_arquivo in documentos.items():
            caminho = self._encontrar_arquivo(nome_arquivo)
            if caminho:
                documentos_prontos[nome_chave] = caminho
                self.logger.info(f"✓ {nome_chave.capitalize()}: pronto")
            else:
                self.logger.warning(f"✗ {nome_chave.capitalize()}: faltando")
        
        return documentos_prontos