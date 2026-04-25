import shutil
from pathlib import Path
import config
import time
import logging
import re

class FileManager:
    def __init__(self, numero_processo):
        self.numero_processo = numero_processo
        self.pasta_raiz = config.PROCESSOS_DIR / numero_processo
        
        # Estrutura de pastas
        self.pasta_originais = self.pasta_raiz / "originais"
        self.pasta_gerados = self.pasta_raiz / "gerados"
        self.pasta_processados = self.pasta_raiz / "processados" # Para arquivos intermediários ou OCR
        
        # Configurar logger específico para este processo
        self.logger = logging.getLogger(f"FileManager_{numero_processo}")

    def criar_pasta_processo(self):
        """Cria estrutura de pastas para o processo"""
        for pasta in [self.pasta_originais, self.pasta_gerados, self.pasta_processados]:
            pasta.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"Estrutura de pastas criada em: {self.pasta_raiz}")
        return self.pasta_raiz
    
    def mover_documentos_baixados(self):
        """
        Move documentos de downloads para pasta de originais do processo.
        Lida com nomes dinâmicos (PREFIXO_chave_timestamp.pdf).
        """
        # Mapeamento: Chave do scraping -> Nome final esperado
        mapeamento = {
            'decisao': config.ARQUIVO_DECISAO,
            'planilhacalculo': config.ARQUIVO_PLANILHA,
            'instrumentoprocuracao': config.ARQUIVO_PROCURACAO
        }
        
        movidos = []
        
        for chave, nome_final in mapeamento.items():
            # Padrão de busca: PREFIXO_chave_*.pdf
            padrao = f"*_{chave}_*.pdf" 
            arquivos_encontrados = list(config.DOWNLOADS_DIR.glob(padrao))
            
            # Ordenar por data de modificação (mais recente primeiro)
            arquivos_encontrados.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            
            if arquivos_encontrados:
                arquivo_recente = arquivos_encontrados[0]
                destino = self.pasta_originais / nome_final
                
                if destino.exists():
                    # Backup do existente
                    timestamp = int(time.time())
                    backup = self.pasta_originais / f"{destino.stem}_old_{timestamp}{destino.suffix}"
                    destino.rename(backup)
                
                try:
                    shutil.move(str(arquivo_recente), str(destino))
                    self.logger.info(f"✓ {arquivo_recente.name} -> {nome_final}")
                    movidos.append(nome_final)
                    
                    # Limpar outros arquivos antigos do mesmo tipo no downloads
                    for arq_velho in arquivos_encontrados[1:]:
                        try: arq_velho.unlink()
                        except: pass
                except Exception as e:
                    self.logger.error(f"Erro ao mover {arquivo_recente.name}: {e}")
            else:
                self.logger.warning(f"✗ Nenhum arquivo encontrado para chave '{chave}'")
        
        return movidos
    
    def verificar_arquivos_necessarios(self):
        """Verifica se todos os arquivos necessários estão na pasta de originais"""
        arquivos_necessarios = config.ARQUIVOS_NECESSARIOS
        faltando = []
        for arquivo in arquivos_necessarios:
            if not (self.pasta_originais / arquivo).exists():
                faltando.append(arquivo)
        return faltando
    
    def obter_caminho_arquivo(self, nome_arquivo, tipo="original"):
        """Retorna caminho completo de um arquivo."""
        if tipo == "original":
            return self.pasta_originais / nome_arquivo
        elif tipo == "gerado":
            return self.pasta_gerados / nome_arquivo
        elif tipo == "processado":
            return self.pasta_processados / nome_arquivo
        return self.pasta_raiz / nome_arquivo

    def copiar_templates_fixos(self):
        """Copia templates fixos para a pasta do processo."""
        arquivos_fixos = ["CNPJ.pdf", "CONTRATO SOCIAL.pdf"]
        try:
            for nome_fixo in arquivos_fixos:
                origem = config.TEMPLATES_DIR / nome_fixo
                if not origem.exists() and "CONTRATO SOCIAL" in nome_fixo:
                     possiveis = list(config.TEMPLATES_DIR.glob("CONTRATO SOCIAL*.pdf"))
                     if possiveis: origem = possiveis[0]
                
                if origem.exists():
                    nome_destino = "Contrato_Social.pdf" if "CONTRATO SOCIAL" in nome_fixo.upper() else nome_fixo
                    shutil.copy2(str(origem), self.pasta_originais / nome_destino)
                    self.logger.info(f"✓ Copiado template fixo: {nome_destino}")
        except Exception as e:
            self.logger.error(f"Erro ao copiar templates fixos: {e}")

    def preparar_pasta_upload(self, peticao_pdf_path, autores_selecionados=None):
        """
        Consolida e organiza os documentos para o upload.
        Implementa a associação por autor levando os documentos nomeados para o e-SAJ.
        """
        try:
            pasta_upload = self.pasta_raiz / "upload"
            if pasta_upload.exists():
                shutil.rmtree(pasta_upload)
            pasta_upload.mkdir(parents=True, exist_ok=True)
            
            # 1. Documentos Base
            planilha = self.obter_caminho_arquivo(config.ARQUIVO_PLANILHA, "original")
            decisao = self.obter_caminho_arquivo(config.ARQUIVO_DECISAO, "original")
            procuracao = self.obter_caminho_arquivo(config.ARQUIVO_PROCURACAO, "original")
            contrato = self.pasta_processados / "Contrato.pdf"
            
            # Typos intencionais removidos para clareza
            peticao_pdf = Path(peticao_pdf_path) if peticao_pdf_path else None
            
            documentos_src = [
                (peticao_pdf, "01 - PETICAO"),
                (planilha, "02 - PLANILHA DE CALCULO"),
                (procuracao, "03 - PROCURACAO"),
                (decisao, "04 - DECISAO DE HOMOLOGACAO"),
                (contrato, "05 - CONTRATO")
            ]
            
            arquivos_prontos = []
            for src_path, prefixo in documentos_src:
                if src_path and src_path.exists():
                    nome_final = f"{prefixo}.pdf"
                    destino = pasta_upload / nome_final
                    shutil.copy2(str(src_path), str(destino))
                    arquivos_prontos.append(str(destino))
            
            # 2. Documentos Dinâmicos por Autor
            # REQUISITO: Ordem dos anexos por autor (Incidência separada)
            from classes import utils 
            outros_pdfs = list(self.pasta_originais.glob("*.pdf"))
            for pdf in outros_pdfs:
                if pdf.name in [config.ARQUIVO_DECISAO, config.ARQUIVO_PLANILHA, config.ARQUIVO_PROCURACAO]:
                    continue
                
                incluir = False
                if autores_selecionados:
                    for autor in autores_selecionados:
                        if utils.limpar_texto(autor).lower() in utils.limpar_texto(pdf.name).lower():
                            incluir = True
                            break
                else: incluir = True
                
                if incluir:
                    idx = len(arquivos_prontos) + 1
                    nome_limpo = re.sub(r'^\d+\s*-\s*', '', pdf.name)
                    nome_final = f"{idx:02d} - {nome_limpo}"
                    destino = pasta_upload / nome_final
                    if not destino.exists():
                         shutil.copy2(str(pdf), str(destino))
                         arquivos_prontos.append(str(destino))

            return arquivos_prontos if arquivos_prontos else None
        except Exception as e:
            self.logger.error(f"Erro ao preparar pasta de upload: {e}")
            return None

    def arquivar_peticionados(self, autores_selecionados: list):
        """
        Move documentos gerados e originais utilizados para uma subpasta datada de finalização.
        REQUISITO 6.3: "Ao final de cada protocolo... mover os documentos gerados para essa pasta e os arquivos originais utilizados."
        """
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            nome_autores = "_".join([re.sub(r'[^\w]', '', a)[:10] for a in autores_selecionados])
            nome_pasta = f"Peticionado_{timestamp}_{nome_autores}"
            pasta_destino = self.pasta_raiz / nome_pasta
            pasta_destino.mkdir(exist_ok=True)
            
            self.logger.info(f"📂 Arquivando documentos em: {nome_pasta}")
            
            # 1. Mover arquivos da pasta 'upload' (que contém os arquivos finais enviados)
            pasta_upload = self.pasta_raiz / "upload"
            if pasta_upload.exists():
                for arq in pasta_upload.glob("*"):
                    shutil.copy2(str(arq), str(pasta_destino))
            
            # 2. Mover originais utilizados (opcional: copiar para manter histórico)
            for arq_orig in self.pasta_originais.glob("*"):
                # Copia originais para a pasta de arquivamento
                shutil.copy2(str(arq_orig), str(pasta_destino))
                
            # 3. GERAR RELATÓRIO FINAL (.txt) - REQUISITO FASE 6
            try:
                caminho_relatorio = pasta_destino / "RELATORIO_FINAL.txt"
                with open(caminho_relatorio, "w", encoding="utf-8") as f:
                    f.write("="*60 + "\n")
                    f.write("       RELATÓRIO DE PETICIONAMENTO AUTOMÁTICO\n")
                    f.write("="*60 + "\n\n")
                    f.write(f"Processo: {self.numero_processo}\n")
                    f.write(f"Data/Hora: {time.strftime('%d/%m/%Y %H:%M:%S')}\n\n")
                    f.write("AUTORES PETICIONADOS NESTE LOTE:\n")
                    for autor in autores_selecionados:
                        f.write(f" - {autor}\n")
                    
                    f.write("\nSTATUS: Sucesso no protocolo (e-SAJ).\n")
                    f.write("="*60 + "\n")
                self.logger.info("   📄 Relatório final (.txt) gerado.")
            except Exception as e_rel:
                self.logger.warning(f"Falha ao gerar arquivo de relatório: {e_rel}")
                
            self.logger.info(f"✅ Arquivamento concluído com sucesso.")
            return pasta_destino
        except Exception as e:
            self.logger.error(f"Erro ao arquivar documentos: {e}")
            return None