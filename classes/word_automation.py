import win32com.client
import pythoncom
import os
from pathlib import Path
import logging

class WordAutomation:
    def __init__(self):
        self.logger = logging.getLogger("WordAutomation")
        self.word_app = None

    def _limpar_cache_win32(self):
        """Limpa o cache do win32com (gen_py)"""
        try:
            import shutil
            import sys
            import win32com
            
            # Caminho padrão do gen_py
            gen_py_path = Path(win32com.__gen_path__)
            if gen_py_path.exists():
                self.logger.warning(f"Limpando cache win32com em: {gen_py_path}")
                shutil.rmtree(gen_py_path)
                
                # Recarregar módulo win32com.client
                if 'win32com.client.gencache' in sys.modules:
                    del sys.modules['win32com.client.gencache']
                if 'win32com.client' in sys.modules:
                    del sys.modules['win32com.client']
                import win32com.client
                
                return True
        except Exception as e:
            self.logger.error(f"Erro ao limpar cache win32com: {e}")
        return False

    def _iniciar_word(self):
        """Inicia instancia do Word visivel"""
        try:
            # Garante inicializacao COM para thread atual
            pythoncom.CoInitialize()
            
            try:
                # Tenta inicialização com Cache (Early Binding)
                self.word_app = win32com.client.gencache.EnsureDispatch("Word.Application")
            except AttributeError:
                # Se falhar por erro de atributo (típico de cache corrompido), limpa e tenta de novo
                self.logger.warning("Cache win32com corrompido detectado. Tentando limpar e reiniciar...")
                if self._limpar_cache_win32():
                    try:
                        self.word_app = win32com.client.gencache.EnsureDispatch("Word.Application")
                    except Exception as e2:
                        self.logger.error(f"Falha na segunda tentativa de EnsureDispatch: {e2}")
                        self.word_app = win32com.client.Dispatch("Word.Application")
                else:
                    self.word_app = win32com.client.Dispatch("Word.Application")
            except Exception as e:
                self.logger.warning(f"Falha no EnsureDispatch ({e}), tentando Dispatch padrão...")
                self.word_app = win32com.client.Dispatch("Word.Application")
            
            self.word_app.Visible = True
            self.word_app.DisplayAlerts = False
            return True
        except Exception as e:
            self.logger.error(f"Erro ao iniciar Word: {e}")
            return False

    def preencher_substabelecimento(self, template_path, dados, output_pdf_path):
        """
        Abre o template, substitui BOOKMARKS e salva como PDF.
        
        Args:
            template_path (Path): Caminho do modelo .docx
            dados (dict): Dicionario com chaves/valores para substituir Bookmarks
                          Ex: {'numero_processo': '123...', 'cidade': 'São Paulo', ...}
            output_pdf_path (Path): Caminho final do PDF
            
        Returns:
            bool: True se sucesso, False c.c.
        """
        doc = None
        try:
            self.logger.info("Iniciando automacao do Word (Modo Bookmarks)...")
            if not self._iniciar_word():
                return False

            abs_template = str(Path(template_path).resolve())
            abs_output = str(Path(output_pdf_path).resolve())

            self.logger.info(f"Abrindo template: {abs_template}")
            doc = self.word_app.Documents.Open(abs_template)
            
            # Delay de segurança (mantido por prudência)
            import time
            time.sleep(1)
            
            # Substituicao via Bookmarks
            self.logger.info("Iniciando substituição de Bookmarks...")
            
            bookmarks_encontrados_total = 0
            for chave, valor in dados.items():
                if valor is None:
                    valor = ""
                
                # Forçar VARA em maiúsculas conforme solicitado
                if "vara" in chave.lower():
                    valor = str(valor).upper()
                
                str_valor = str(valor)
                substituiu_algum = False

                # 1. Tenta bookmark base (sem número)
                if doc.Bookmarks.Exists(chave):
                    try:
                        doc.Bookmarks(chave).Range.Text = str_valor
                        self.logger.info(f"✅ Bookmark '{chave}' preenchido: {str_valor}")
                        bookmarks_encontrados_total += 1
                        substituiu_algum = True
                    except Exception as e:
                        self.logger.error(f"✗ Erro ao preencher bookmark '{chave}': {e}")

                # 2. Tenta bookmarks numerados (chave_1, chave_2, ...)
                contador = 1
                while True:
                    bookmark_numerado = f"{chave}_{contador}"
                    if doc.Bookmarks.Exists(bookmark_numerado):
                        try:
                            doc.Bookmarks(bookmark_numerado).Range.Text = str_valor
                            self.logger.info(f"✅ Bookmark '{bookmark_numerado}' preenchido: {str_valor}")
                            bookmarks_encontrados_total += 1
                            substituiu_algum = True
                        except Exception as e:
                            self.logger.error(f"✗ Erro ao preencher bookmark '{bookmark_numerado}': {e}")
                        
                        contador += 1
                    else:
                        # Se não encontrar o numero atual, assume que acabaram as variações
                        break
                
                if not substituiu_algum:
                    self.logger.warning(f"⚠ Bookmark '{chave}' e variações não encontrados no template.")
                    print(f"⚠ Bookmark '{chave}' (e variações) não existe no documento.")

            self.logger.info(f"Total de bookmarks preenchidos: {bookmarks_encontrados_total}")
            
            # Salvar como PDF
            # wdFormatPDF = 17
            self.logger.info(f"Salvando PDF em: {abs_output}")
            doc.SaveAs(abs_output, FileFormat=17)
            
            return True

        except Exception as e:
            self.logger.error(f"Erro na automacao Word: {e}")
            return False
            
        finally:
            if doc:
                try:
                    # Fecha sem salvar para preservar o template original (os bookmarks)
                    doc.Close(SaveChanges=0)
                except Exception as e:
                    self.logger.warning(f"Erro: {e}")
            
            if self.word_app:
                try:
                    self.word_app.Quit()
                except Exception as e:
                    self.logger.warning(f"Erro: {e}")
            
            pythoncom.CoUninitialize()

    def preencher_documento_docx(self, template_path, dados, output_docx_path):
        """
        Abre o template, substitui BOOKMARKS e salva como DOCX (sem converter para PDF).
        
        Args:
            template_path (Path): Caminho do modelo .docx
            dados (dict): Dicionário com chaves/valores para substituir Bookmarks
            output_docx_path (Path): Caminho final do DOCX
            
        Returns:
            bool: True se sucesso, False c.c.
        """
        doc = None
        try:
            self.logger.info("Iniciando automação do Word (Modo Bookmarks - DOCX)...")
            if not self._iniciar_word():
                return False

            abs_template = str(Path(template_path).resolve())
            abs_output = str(Path(output_docx_path).resolve())

            self.logger.info(f"Abrindo template: {abs_template}")
            
            # Tenta abrir o documento com retry
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self.word_app.Documents.Open(abs_template)
                    break
                except Exception as e:
                    if "2147418111" in str(e) or "chamada foi rejeitada" in str(e):
                        if attempt < max_retries - 1:
                            self.logger.warning(f"Word ocupado (tentativa {attempt+1}), aguardando...")
                            import time
                            time.sleep(2)
                            continue
                    self.logger.error(f"Erro ao chamar Documents.Open: {e}")
                    return False

            # Tenta obter o objeto doc de forma robusta com retry
            doc = None
            for attempt in range(max_retries):
                try:
                    # Método 1: ActiveDocument
                    doc = self.word_app.ActiveDocument
                    
                    # Teste de acesso (pode falhar se Word estiver ocupado)
                    _ = doc.Name
                    
                    # Verificação extra
                    if doc.FullName.lower() != abs_template.lower():
                        self.logger.warning("ActiveDocument não corresponde ao template aberto. Procurando na coleção...")
                        doc = None
                        for d in self.word_app.Documents:
                            if d.FullName.lower() == abs_template.lower():
                                doc = d
                                break
                    
                    if doc:
                         break
                except Exception as e:
                     if attempt < max_retries - 1:
                        import time
                        time.sleep(1)
                        continue
            
            if not doc:
                self.logger.error("❌ CRÍTICO: Não foi possível obter a referência ao objeto Documento do Word.")
                return False

            # Delay para estabilização
            import time
            time.sleep(1)

            # DEBUG: Listar todos os bookmarks encontrados no documento
            try:
                print(f"\n--- DEBUG BOOKMARKS EM {Path(template_path).name} ---")
                count = 0
                # Retry para contar bookmarks
                for _ in range(3):
                    try:
                        count = doc.Bookmarks.Count
                        break
                    except Exception:
                        time.sleep(0.5)
                
                print(f"Total de bookmarks detectados: {count}")
                
                bookmarks_existentes = []
                for i in range(1, count + 1):
                    try:
                        bookmarks_existentes.append(doc.Bookmarks(i).Name)
                    except Exception:
                        pass
                
                print(f"Lista: {', '.join(bookmarks_existentes)}")
                print("-------------------------------------------\n")
            except Exception as e:
                print(f"⚠️ Erro ao listar bookmarks (debug): {e}")

            # Substituir bookmarks
            bookmarks_encontrados = 0
            bookmarks_nao_encontrados = []
            
            for chave, valor in dados.items():
                if valor is None or valor == "":
                    continue
                
                # Forçar VARA em maiúsculas conforme solicitado
                if "vara" in chave.lower():
                    valor = str(valor).upper()
                
                # Funcao auxiliar para retry no Check
                def safe_bookmark_exists(doc_obj, bm_name):
                    for _ in range(10):  # Aumentado para 10 tentativas
                        try:
                            return doc_obj.Bookmarks.Exists(bm_name)
                        except Exception:
                            time.sleep(0.5)  # Aumentado para 0.5s
                    return False

                # Funcao auxiliar para retry no Set
                def safe_set_text(doc_obj, bm_name, val):
                    for _ in range(10):  # Aumentado para 10 tentativas
                        try:
                            doc_obj.Bookmarks(bm_name).Range.Text = str(val)
                            return True
                        except Exception:
                            time.sleep(0.5)  # Aumentado para 0.5s
                    return False
                
                # Tenta bookmark base
                if safe_bookmark_exists(doc, chave):
                    if safe_set_text(doc, chave, valor):
                        bookmarks_encontrados += 1
                        self.logger.info(f"  ✓ Bookmark '{chave}' preenchido")
                else:
                    # Tentar variações numeradas
                    encontrou_variacao = False
                    for i in range(1, 10):
                        bookmark_numerado = f"{chave}_{i}"
                        if safe_bookmark_exists(doc, bookmark_numerado):
                            if safe_set_text(doc, bookmark_numerado, valor):
                                bookmarks_encontrados += 1
                                encontrou_variacao = True
                                self.logger.info(f"  ✓ Bookmark '{bookmark_numerado}' preenchido")
                    
                    if not encontrou_variacao:
                        bookmarks_nao_encontrados.append(chave)
            
            if bookmarks_nao_encontrados:
                self.logger.warning(f"Bookmarks não encontrados: {', '.join(bookmarks_nao_encontrados)}")
            
            self.logger.info(f"Total de bookmarks preenchidos: {bookmarks_encontrados}")
            
            # --- FALLBACK: SUBSTITUIÇÃO DE TEXTO {{chave}} ---
            # Caso o usuário tenha usado placeholders de texto ao invés de bookmarks
            self.logger.info("Iniciando varredura de Texto (Find/Replace)...")
            replacements_text = 0
            
            # Otimização: Só roda find/replace para o que não foi preenchido via bookmark
            # ou roda para tudo para garantir
            
            for chave, valor in dados.items():
                if valor is None: valor = ""
                
                # Forçar VARA em maiúsculas conforme solicitado
                if "vara" in chave.lower():
                    valor = str(valor).upper()
                    
                str_valor = str(valor)
                
                # Padrões para substituir: {{chave}}, {{ chave }}, {chave}
                patterns = [
                    f"{{{{{chave}}}}}",     # {{chave}}
                    f"{{{{ {chave} }}}}",   # {{ chave }}
                    f"{{{chave}}}"          # {chave}
                ]
                
                for pattern in patterns:
                    try:
                        # Configura o objeto Find
                        # Range total do documento
                        rng = doc.Content
                        find = rng.Find
                        
                        find.ClearFormatting()
                        find.Replacement.ClearFormatting()
                        
                        # Execute(FindText, MatchCase, MatchWholeWord, MatchWildcards, MatchSoundsLike, MatchAllWordForms, Forward, Wrap, Format, ReplaceWith, Replace)
                        # Replace=2 (wdReplaceAll)
                        if find.Execute(pattern, False, False, False, False, False, True, 1, False, str_valor, 2):
                            replacements_text += 1
                            self.logger.info(f"  ✓ Texto '{pattern}' substituído.")
                    except Exception as e:
                        self.logger.warning(f"Erro no Find/Replace para '{chave}': {e}")

            self.logger.info(f"Total de substituições de texto: {replacements_text}")

            # Salvar como DOCX com Retry
            self.logger.info(f"Salvando documento DOCX: {abs_output}")
            for _ in range(3):
                try:
                    doc.SaveAs2(abs_output, FileFormat=16)
                    self.logger.info("✅ Documento DOCX salvo com sucesso!")
                    return True
                except Exception:
                    time.sleep(1)
            
            return False
            
        except Exception as e:
            self.logger.error(f"Erro ao preencher documento: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            if doc:
                try:
                    doc.Close(SaveChanges=0)
                except Exception as e:
                    self.logger.warning(f"Erro ao fechar documento: {e}")
            
            if self.word_app:
                try:
                    self.word_app.Quit()
                except Exception as e:
                    self.logger.warning(f"Erro ao fechar Word: {e}")
            
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    def converter_docx_para_pdf(self, input_docx, output_pdf):
        """
        Converte um arquivo DOCX para PDF.
        
        Args:
            input_docx (Path): Caminho do arquivo DOCX de entrada
            output_pdf (Path): Caminho para salvar o PDF
            
        Returns:
            bool: True se sucesso, False c.c.
        """
        doc = None
        try:
            self.logger.info(f"Convertendo para PDF: {input_docx}")
            if not self._iniciar_word():
                return False

            abs_input = str(Path(input_docx).resolve())
            abs_output = str(Path(output_pdf).resolve())

            doc = self.word_app.Documents.Open(abs_input)
            
            # wdFormatPDF = 17
            doc.SaveAs(abs_output, FileFormat=17)
            self.logger.info(f"✅ PDF gerado: {output_pdf}")
            return True
            
        except Exception as e:
            self.logger.error(f"Erro ao converter para PDF: {e}")
            return False
        finally:
            if doc:
                try:
                    doc.Close(SaveChanges=0)
                except Exception as e:
                    self.logger.warning(f"Erro ao fechar documento: {e}")
            
            if self.word_app:
                try:
                    self.word_app.Quit()
                except Exception as e:
                    self.logger.warning(f"Erro ao fechar Word: {e}")
            
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
