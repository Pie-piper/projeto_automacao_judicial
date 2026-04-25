from playwright.sync_api import Page, Locator
from typing import Optional, List, Dict, Union, Tuple
from pathlib import Path
import os
import time
import re
import config
import logging
from classes.selectors import Selectors
from classes.types_download import ResultadoDownload, StatusDownload
from .utils import parece_nome_pessoa
import pdfplumber
import pytesseract
from pdf2image import convert_from_path
import shutil

class PastaDigitalPage:
    def __init__(self, page: Page):
        self.page = page
        self.logger = logging.getLogger(__name__)
        # Configurar Tesseract
        pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_PATH

    def aguardar_carregamento_pasta(self) -> bool:
        """
        Método DEFINITIVO para abrir e aguardar carregamento da pasta digital.
        Resolve problemas de AJAX e instabilidade do e-SAJ.
        """
        try:
            self.logger.info("⏳ Aguardando pasta digital carregar (URL e Network)...")
            
            # 1. Aguardar mudança para URL da pasta digital
            try:
                self.page.wait_for_url("**/abrirPastaDigital.do**", timeout=30000)
                self.logger.info("✅ URL da pasta digital detectada.")
            except Exception as e:
                self.logger.warning(f"⚠️ URL não mudou conforme esperado: {e}")

            # 2. Aguardar Load States
            self.page.wait_for_load_state("domcontentloaded", timeout=30000)
            self.logger.info("✅ DOM carregado.")
            
            # CRÍTICO: Networkidle garante que o AJAX de carregamento da árvore terminou
            try:
                self.page.wait_for_load_state("networkidle", timeout=30000)
                self.logger.info("✅ Network idle (AJAX concluído).")
            except Exception:
                self.logger.warning("⚠️ Timeout aguardando networkidle, prosseguindo com verificação de árvore.")

            # 3. Aguardar Container da Árvore
            self.page.wait_for_selector(Selectors.ARVORE_PRINCIPAL, state="visible", timeout=20000)
            self.logger.info("✅ Container da árvore visível.")

            # 4. Aguardar Documentos Popularem (Wait for treeitems)
            self._aguardar_documentos_popularem()
            
            # Verificação final de contagem
            count = self.page.locator(f"{Selectors.ARVORE_PRINCIPAL} .jstree-anchor").count()
            self.logger.info(f"✅ Árvore carregada com {count} nós clicáveis.")
            
            if count == 0:
                raise Exception("Árvore de documentos está vazia!")

            return True

        except Exception as e:
            self.logger.error(f"❌ Falha no carregamento robusto da pasta digital: {e}")
            self._debug_snapshot("falha_carga_pasta")
            return False

    def _aguardar_documentos_popularem(self, max_tentativas=10):
        """Aguarda os itens da árvore aparecerem no DOM."""
        self.logger.info("⏳ Aguardando itens da árvore aparecerem...")
        for tentativa in range(1, max_tentativas + 1):
            count = self.page.locator(f"{Selectors.ARVORE_PRINCIPAL} .jstree-anchor").count()
            if count > 0:
                self.logger.info(f"✅ Itens detectados na tentativa {tentativa}.")
                return True
            self.logger.info(f"⏳ Tentativa {tentativa}/{max_tentativas} - Árvore vazia, aguardando...")
            time.sleep(2)
        raise Exception(f"Itens da árvore não carregaram após {max_tentativas} tentativas.")

    def validar_jstree_disponivel(self) -> bool:
        """
        Verifica se a biblioteca jsTree e a instância da árvore estão carregadas.
        """
        try:
            return self.page.evaluate("""
                () => {
                    try {
                        // Verifica jQuery
                        if (typeof jQuery === 'undefined') return false;
                        
                        // Verifica plugin jsTree
                        if (typeof jQuery.jstree === 'undefined') return false;
                        
                        // Verifica elemento da árvore
                        const arvore = $('#arvore_principal');
                        if (arvore.length === 0) return false;
                        
                        // Verifica instância ativa
                        const instance = arvore.jstree(true);
                        return instance !== false && instance !== null;
                    } catch (e) {
                        return false;
                    }
                }
            """)
        except Exception as e:
            self.logger.error(f"❌ Erro ao validar jsTree: {e}")
            return False

    # ========================================
    # MÉTODOS DE BUSCA
    # ========================================

    def buscar_documento_por_nome(self, nome: str) -> Optional[Locator]:
        """
        Busca o elemento do documento na árvore pelo nome (conteúdo de texto).
        Retorna o Locator do primeiro elemento encontrado ou None.
        """
        try:
            # Seletor que busca âncoras dentro da árvore que contenham o texto
            # O jsTree usa <a> com class jstree-anchor.
            # Usamos partial text match porque o nome pode ter sufixos (ex: " (Página 1-5)")
            
            # Estratégia 1: Selector de texto direto do Playwright (mais robusto para texto visível)
            locator = self.page.locator(f"{Selectors.ARVORE_PRINCIPAL} .jstree-anchor").filter(has_text=nome).first
            
            if locator.count() > 0:
                # Validar se o texto é realmente o esperado (evitar falsos positivos parciais muito curtos)
                texto_encontrado = locator.inner_text()
                # Validação simples: se o nome buscado está contido no início ou é parte significativa
                if nome in texto_encontrado:
                   return locator

            return None
            
        except Exception as e:
            self.logger.warning(f"⚠️ Erro ao buscar documento '{nome}': {e}")
            return None

    # ========================================
    # MÉTODO PRINCIPAL - ORQUESTRADOR
    # ========================================
    
    def baixar_documentos(self, tipo_processo: str = "todos", documentos_adicionais: list = None) -> Dict[str, 'ResultadoDownload']:
        """
        Orquestra o download dos documentos chave da pasta digital.
        
        Args:
            tipo_processo: "autos_principais", "cumprimento", ou "todos"
            documentos_adicionais: Lista de chaves de documentos a baixar (ex: ['decisao'])
            
        Returns:
            Dict com resultados de cada documento (chave: ResultadoDownload)
        """
        self.logger.info("="*80)
        self.logger.info(f"🚀 INICIANDO DOWNLOAD DE DOCUMENTOS ({tipo_processo.upper()}) - Estratégia Robusta")
        self.logger.info("="*80)
        
        resultados = {}
        
        # Configuração de documentos com metadata
        todas_configs = {
            "instrumentoprocuracao": {
                "variantes": ["Instrumento de Procuração", "Procuração"],
                "paginas_esperadas": (9, 13)
            },
            "decisao": {
                "variantes": ["Decisão"],
                "paginas_esperadas": (17, 19)
            },
            "planilhacalculo": {
                "variantes": [
                    "Planilha de Cálculo", "Planilha de Calculo",
                    "Planilha Decisão", "Planilha Decisao",
                    "Planilha de Cálculos", "Planilha de Calculos",
                    "Planilha Atualizada", "Planilha Complementar",
                    "Cálculo", "Calculo", "Planilha"
                ],
                "paginas_esperadas": (15, 16)
            }
        }
        
        if tipo_processo == "autos_principais":
            documentos_alvo = {k: v for k, v in todas_configs.items() if k in ["instrumentoprocuracao"]}
        elif tipo_processo == "cumprimento":
            documentos_alvo = {k: v for k, v in todas_configs.items() if k in ["decisao", "planilhacalculo"]}
        else:
            documentos_alvo = todas_configs
            
        if documentos_adicionais:
            for d in documentos_adicionais:
                if d in todas_configs:
                    documentos_alvo[d] = todas_configs[d]
        
        # VALIDAR jsTree ANTES de começar
        if not self.validar_jstree_disponivel():
            self.logger.error("❌ jsTree não está disponível! Abortando.")
            return {}

        # 1. Verificar se existe "Impugnação ao Cumprimento de Sentença"
        # Se houver, ele substitui a Planilha de Cálculo e dispara download de 3 Documentos Diversos
        self.logger.info("🔍 Verificando se há Impugnação ao Cumprimento de Sentença...")
        impugnacao_loc = self.buscar_documento_por_nome("Impugnação ao Cumprimento de Sentença")
        if impugnacao_loc:
            self.logger.info("⚠️ Impugnação detectada! Iniciando fluxo especial de download.")
            res_impugnacao = self._baixar_documento_seguro(
                chave="planilhacalculo", # Será salvo como 02_PLANILHA
                variantes=["Impugnação ao Cumprimento de Sentença"],
                paginas_esperadas=(1, 50)
            )
            resultados["planilhacalculo"] = res_impugnacao
            
            # Download dos 3 documentos seguintes ("Documentos Diversos")
            self._baixar_documentos_seguintes(impugnacao_loc, 3, "Documentos Diversos")
        
        # Garantir estado limpo inicial
        self.logger.info("🧹 Limpeza inicial da árvore...")
        self._garantir_arvore_limpa()
        
        # Separar documentos que precisam de seleção inteligente (HOMOLOGO)
        # Se a planilha já foi baixada via Impugnação, removemos daqui
        if "planilhacalculo" in resultados:
            docs_smart = {k: v for k, v in documentos_alvo.items() if k in ["decisao"]}
        else:
            docs_smart = {k: v for k, v in documentos_alvo.items() if k in ["decisao", "planilhacalculo"]}
            
        docs_regular = {k: v for k, v in documentos_alvo.items() if k not in ["decisao", "planilhacalculo"]}
        
        # 1. Download regular (instrumentoprocuracao, etc.)
        for chave, config_doc in docs_regular.items():
            self.logger.info("")
            self.logger.info(f"📄 Processando: {chave.upper()}")
            self.logger.info("-" * 60)
            
            resultado = self._baixar_documento_seguro(
                chave=chave,
                variantes=config_doc["variantes"],
                paginas_esperadas=config_doc["paginas_esperadas"]
            )
            
            resultados[chave] = resultado
            
            if resultado.status == StatusDownload.SUCESSO:
                self.logger.info(f"   ✅ {chave.upper()}: {resultado.mensagem}")
                
                # EXTRA: Se for a planilha, tentar extrair a data de protocolo (Data Base do requisito 3.3)
                if chave == "planilhacalculo":
                    self._abrir_documento_viewer(self.buscar_documento_por_nome(resultado.documento))
                    data_proto = self.extrair_data_protocolo_peticao()
                    if data_proto:
                        resultado.metadata['data_protocolo'] = data_proto
                        self.logger.info(f"   📅 Data de protocolo (Data Base) extraída: {data_proto}")
            else:
                self.logger.warning(f"   ❌ {chave.upper()}: {resultado.mensagem}")
            
            time.sleep(2.0)
        
        # 2. Seleção inteligente para Decisão + Planilha (via HOMOLOGO)
        if docs_smart:
            self.logger.info("")
            self.logger.info("🧠 SELEÇÃO INTELIGENTE: Buscando Decisão com HOMOLOGO...")
            self.logger.info("-" * 60)
            
            resultados_smart = self.processar_selecao_complexa()
            
            if resultados_smart:
                resultados.update(resultados_smart)
                self.logger.info("   ✅ Seleção inteligente concluída")
            else:
                self.logger.warning("   ⚠️ Seleção inteligente não encontrou HOMOLOGO")
            
            # Fallback omitido ou substituído por falha explícita se for decisao
            for chave in docs_smart:
                if chave not in resultados or resultados[chave].status != StatusDownload.SUCESSO:
                    if chave == "decisao":
                        self.logger.info(f"   🔄 Fallback recusado para {chave.upper()}: Exige-se HOMOLOGO rigorosamente.")
                        if chave not in resultados:
                            resultados[chave] = ResultadoDownload(documento=chave, status=StatusDownload.NAO_ENCONTRADO, mensagem="Decisão de Homologação não encontrada (critério rígido)")
                    elif chave == "planilhacalculo" and "planilhacalculo" not in resultados:
                        self.logger.info(f"   🔄 Fallback para download direto: {chave.upper()}")
                        config_doc = todas_configs[chave]
                        resultado = self._baixar_documento_seguro(
                            chave=chave,
                            variantes=config_doc["variantes"],
                            paginas_esperadas=config_doc["paginas_esperadas"]
                        )
                        resultados[chave] = resultado
                        
                        if resultado.status == StatusDownload.SUCESSO:
                            self.logger.info(f"   ✅ {chave.upper()} (fallback): {resultado.mensagem}")
                        else:
                            self.logger.warning(f"   ❌ {chave.upper()} (fallback): {resultado.mensagem}")
        
        # Extração de metadata de Petição, Documento Pessoal e Sentença (apenas leitura)
        self.logger.info("")
        self.logger.info("📋 Extraindo metadata adicional (Petição, Doc Pessoal, Sentença)...")
        
        adicionais = {
            "peticao": ["Petição (Outras)", "Peticão", "Petição"],
            "documentopessoal": ["Documentos Pessoais", "Documento Pessoal", "Docs Pessoais"],
            "sentenca": ["Sentença", "Sentenca", "Decisão de Homologação"],
            "certidao": ["Certidão", "Certidão de Trânsito em Julgado", "Certidao"]
        }
        
        for chave, variantes in adicionais.items():
            for variante in variantes:
                doc_loc = self.buscar_documento_por_nome(variante)
                if doc_loc:
                    # Tentar extrair páginas do texto do nó pai primeiro
                    texto_pai = doc_loc.inner_text()
                    info_paginas = self.extrair_paginas_do_texto(texto_pai)
                    
                    # Se o nó pai não contém páginas, buscar nos nós filhos
                    if not info_paginas or not info_paginas.get('formato_fls'):
                        try:
                            # Buscar o nó <li> pai que contém os filhos
                            li_pai = doc_loc.locator('xpath=ancestor::li[1]')
                            filhos = li_pai.locator('.jstree-children .jstree-anchor')
                            count_filhos = filhos.count()
                            
                            if count_filhos > 0:
                                # Concatenar texto de todos os filhos
                                textos_filhos = []
                                for idx in range(count_filhos):
                                    textos_filhos.append(filhos.nth(idx).inner_text())
                                
                                texto_completo = ' | '.join(textos_filhos)
                                self.logger.info(f"   📄 Texto dos filhos de '{variante}': {texto_completo}")
                                
                                info_paginas = self.extrair_paginas_do_texto(texto_completo)
                        except Exception as e:
                            self.logger.warning(f"   ⚠️ Erro ao ler filhos de '{variante}': {e}")
                    
                    if chave == "peticao":
                        # Se for petição, extraímos também os autores e data de protocolo
                        self.logger.info(f"   🕵️ Abrindo '{variante}' para extrair autores e data...")
                        self._abrir_documento_viewer(doc_loc)
                        if info_paginas is None:
                            info_paginas = {}
                        info_paginas['lista_autores'] = self.extrair_autores_peticao()
                        info_paginas['data_protocolo'] = self.extrair_data_protocolo_peticao()
                        info_paginas['vara'] = self.extrair_vara_peticao()
                        info_paginas['cidade'] = self.extrair_cidade_peticao()

                    if chave == "certidao":
                        # Tentar extrair data de trânsito em julgado do texto (se houver)
                        if info_paginas is None:
                            info_paginas = {}
                        
                        texto_busca = info_paginas.get('texto_paginas', '')
                        # Regex para data brasileira (dd/mm/aaaa)
                        match_data = re.search(r'(\d{2}/\d{2}/\d{4})', str(texto_busca))
                        if match_data:
                            info_paginas['data_transito_julgado'] = match_data.group(1)
                            self.logger.info(f"   📅 Data extraída da Certidão: {match_data.group(1)}")
                    
                    resultados[chave] = ResultadoDownload(
                        documento=variante,
                        status=StatusDownload.SUCESSO,
                        mensagem="Metadata extraída",
                        metadata=info_paginas
                    )
                    self.logger.info(f"   ✅ {chave}: {info_paginas.get('formato_fls', 'N/A') if info_paginas else 'N/A'}")
                    break
            else:
                # Apenas adiciona como não encontrado se a chave ainda não existir (para não sobrescrever sucessos de outras abas)
                if chave not in resultados:
                    resultados[chave] = ResultadoDownload(
                        documento=chave,
                        status=StatusDownload.NAO_ENCONTRADO,
                        mensagem="Não encontrada"
                    )
        
        # Resumo final
        self.logger.info("")
        self.logger.info("="*80)
        sucessos = sum(1 for r in resultados.values() if r.status == StatusDownload.SUCESSO)
        self.logger.info(f"📊 Processamento concluído: {sucessos}/{len(resultados)} documentos")
        self.logger.info("="*80)
        
        return resultados
    
    def _baixar_documentos_seguintes(self, locator_base: Locator, quantidade: int, nome_esperado: str):
        """Baixa os N documentos que aparecem logo após o locator_base na árvore."""
        try:
            li_pai = locator_base.locator('xpath=ancestor::li[1]')
            # No jsTree, os irmãos estão no mesmo nível de <li> dentro do <ul> pai
            # No entanto, a forma mais fácil é navegar pelo DOM ou usar a API
            self.logger.info(f"📥 Tentando baixar {quantidade} documentos seguintes a partir do ID do jsTree...")
            
            ids_seguintes = self.page.evaluate(f"""
                (base_id_texto, qtd) => {{
                    const tree = $('#arvore_principal').jstree(true);
                    const nodes = tree.get_json('#', {{flat: true}});
                    const idx = nodes.findIndex(n => n.text.includes(base_id_texto));
                    if (idx === -1) return [];
                    
                    return nodes.slice(idx + 1, idx + 1 + qtd).map(n => n.id);
                }}
            """, locator_base.inner_text(), quantidade)
            
            for node_id in ids_seguintes:
                try:
                    nome_doc = self.page.evaluate(f"$('#arvore_principal').jstree(true).get_node('{node_id}').text")
                    self.logger.info(f"   📄 Baixando documento seguinte: {nome_doc}")
                    self._baixar_documento_por_id_jstree(node_id, "diversos")
                except Exception as e:
                    self.logger.warning(f"   ⚠️ Falha ao baixar documento seguinte {node_id}: {e}")
        except Exception as e:
            self.logger.error(f"❌ Erro ao baixar documentos seguintes: {e}")

    def _baixar_documento_por_id_jstree(self, node_id: str, chave: str) -> bool:
        """Versão do download que usa o ID interno do jsTree em vez do nome."""
        try:
            self._garantir_arvore_limpa()
            self.page.evaluate(f"$('#arvore_principal').jstree(true).check_node('{node_id}')")
            time.sleep(0.5)
            
            nome_doc = self.page.evaluate(f"$('#arvore_principal').jstree(true).get_node('{node_id}').text")
            info_paginas = self.extrair_paginas_do_texto(nome_doc)
            
            caminho = self._executar_download_com_retry(nome_doc, chave, info_paginas)
            return caminho is not None
        except Exception as e:
            self.logger.error(f"Erro ao baixar por ID {node_id}: {e}")
            return False

    def _abrir_documento_viewer(self, locator: Locator):
        """Clica no documento para abrir no viewer lateral."""
        try:
            locator.click()
            # Aguardar o viewer carregar (tolerância aumentada para 30s)
            self.page.wait_for_selector("#viewer", state="visible", timeout=45000)
            time.sleep(3) # Tempo extra para o PDF.js renderizar a textLayer
        except Exception as e:
            self.logger.warning(f"Falha ao abrir viewer: {e}")

    def extrair_autores_peticao(self) -> List[str]:
        """Extrai a lista de autores da petição aberta no viewer."""
        try:
            # Pegar todo o texto do viewer e focar na área de requerentes
            texto_completo = self.page.locator(".textLayer").inner_text(timeout=5000)
            
            if "REQUERENTE(S)" in texto_completo.upper() or "REQUERENTES" in texto_completo.upper():
                linhas = texto_completo.split('\n')
                idx_req = -1
                for i, linha in enumerate(linhas):
                    if "REQUERENTE(S)" in linha.upper() or "REQUERENTES" in linha.upper():
                        idx_req = i
                        break
                
                if idx_req != -1:
                    autores = []
                    buffer_nome = []
                    
                    # Range estendido para até 250 linhas, suportando tabelas de múltiplos autores
                    for i in range(idx_req + 1, min(idx_req + 250, len(linhas))):
                        linha = linhas[i].strip()
                        if not linha:
                            continue
                            
                        linha_upper = linha.upper()
                        
                        # Gatilho de parada: Início da petição em si (textos normais, parágrafos)
                        # Esses termos costumam aparecer logo após o esqueleto das partes
                        if "POR SEUS ADVOGADOS" in linha_upper or "VÊM, RESPEITOSAMENTE" in linha_upper or "VÊM À PRESENÇA" in linha_upper or "ARTIGOS 319" in linha_upper or "PROPOR A PRESENTE" in linha_upper:
                             break
                             
                        # Se não é UPPERCASE e tem muita letra minúscula, achamos os parágrafos normais da petição
                        if len(linha) > 20 and not linha.isupper() and not linha.istitle():
                             break
                        
                        # ÂNCORA PRINCIPAL DA TABELA: CPF! 
                        # NOME da pessoa invariavelmente antecede seu número de documento (lido linha a linha pelo PDF)
                        if re.search(r'\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b', linha):
                            if buffer_nome:
                                nome_completo = " ".join(buffer_nome).strip()
                                
                                # Validação: um nome precisa ter pelo menos 2 palavras e não ser lixo
                                if parece_nome_pessoa(nome_completo):
                                     
                                     # Tratamento especial para tabelas extraidas como colunas (fallback)
                                     if len(buffer_nome) > 1 and len(nome_completo.split()) >= 8:
                                          for parte in buffer_nome:
                                               if len(parte.split()) >= 2:
                                                    autores.append(parte.strip())
                                     else:
                                          autores.append(nome_completo)
                                
                            # Após achar o CPF e salvar o nome atrelado a ele, limpa o buffer para o próximo
                            buffer_nome = []
                            continue
                            
                        # Limpeza 1: Se for RG, CEP, ou linha contendo muitos números (Endereço, data) -> ZERA o buffer
                        if re.search(r'\d', linha):
                            buffer_nome = []
                            continue
                            
                        # Limpeza 2: Palavras de exclusão exatas da tabela (Cabeçalhos, profissões, est. civis comuns)
                        exclusoes = [
                            "NOME", "CPF", "RG", "NACIONALIDADE", "ESTADO CIVIL", "PROFISSAO", "PROFISSÃO",
                            "CIDADE", "ENDEREÇO", "ENDERECO", "BAIRRO", "CEP", "TELEFONE", "E-MAIL", "EMAIL",
                            "BRASILEIRA", "BRASILEIRO", "CASADA", "CASADO", "SOLTEIRA", "SOLTEIRO", 
                            "DIVORCIADA", "DIVORCIADO", "VIÚVA", "VIÚVO", "SEPARADA", "SEPARADO",
                            "AXILIAR DE ENFERMAGEM", "AUXILIAR DE ENFERMAGEM", "ENFERMEIRA", "ENFERMEIRO",
                            "TÉCNICO EM ENFERMAGEM", "TECNICO EM ENFERMAGEM", "MOTORISTA", "PROFESSOR"
                        ]
                        
                        if linha_upper in exclusoes or len(linha_upper) <= 2:
                            buffer_nome = []
                            continue
                            
                        # Limpeza 3: Padrões de endereço (se pegar bairro que pulou bloqueio do CEP sem numero)
                        if any(linha_upper.startswith(prefixo) for prefixo in ["RUA ", "AV ", "AV. ", "AVENIDA ", "JD ", "JARDIM ", "VILA ", "VL ", "SÍTIO ", "SITIO ", "FAZENDA ", "ALAMEDA "]):
                             buffer_nome = []
                             continue
                             
                        # Se passou por todos os filtros, é UPPERCASE, e tá logo antes do CPF, assumimos que é o Nome.
                        if linha_upper.isupper() or linha.istitle():
                             buffer_nome.append(linha_upper)
                             
                    if autores:
                        # Remove nomes duplicados mantendo a ordem correta
                        return list(dict.fromkeys(autores))
                        
            return []
        except Exception as e:
            self.logger.warning(f"Erro ao extrair autores de tabela com precisão atômica: {e}")
            return []

    def extrair_data_protocolo_peticao(self) -> Optional[str]:
        """Extrai a data de protocolo da petição (pode estar no viewer ou no DOM)."""
        try:
            # Estratégia 0: Seletor específico do e-SAJ (conforme imagem do cliente)
            # O painel de assinatura tem ID regiaoAssinatura (usando .first para evitar conflitos de ID duplicado)
            assinatura = self.page.locator("#divAssinaturas #regiaoAssinatura").first
            if assinatura.is_visible():
                td_proto = assinatura.locator("td").filter(has_text="Protocolado em")
                if td_proto.count() > 0:
                    texto = td_proto.first.inner_text()
                    match = re.search(r'(\d{2}/\d{2}/\d{4})', texto)
                    if match:
                        self.logger.info(f"✅ Data protocolo extraída via #regiaoAssinatura: {match.group(1)}")
                        return match.group(1)

            # Estratégia 1: Procurar em qualquer <td> (mais genérico)
            td_proto = self.page.locator("td").filter(has_text="Protocolado em")
            if td_proto.count() > 0:
                texto = td_proto.first.inner_text()
                match = re.search(r'(\d{2}/\d{2}/\d{4})', texto)
                if match:
                    return match.group(1)
            
            # Estratégia 2: Procurar no viewer (texto extraído do PDF)
            texto_viewer = self.page.locator(".textLayer").inner_text(timeout=5000)
            match = re.search(r'Protocolado em\s*(\d{2}/\d{2}/\d{4})', texto_viewer, re.IGNORECASE)
            if match:
                return match.group(1)
                
            return None
        except Exception as e:
            self.logger.warning(f"Erro ao extrair data protocolo: {e}")
            return None

    def extrair_vara_peticao(self) -> Optional[str]:
        """Extrai a Vara do cabeçalho da petição no viewer."""
        try:
            # Pequeno retry para garantir que o textLayer carregou
            for _ in range(3):
                texto = self.page.locator(".textLayer").inner_text(timeout=5000)
                if texto.strip():
                    break
                time.sleep(1)
            else:
                return None
            
            # Padrão 1: "AO JUÍZO DE UMA DAS VARAS DO JUIZADO ESPECIAL DA FAZENDA PÚBLICA..."
            match_aj = re.search(
                r'AO JU[IÍ]ZO.*?(JUIZADO\s+ESPECIAL(?:\s+(?:DA|DA\s+FAZENDA\s+P[UÚ]BLICA|C[IÍ]VEL|FAZENDA\s+P[UÚ]BLICA))?)',
                texto, flags=re.IGNORECASE
            )
            if match_aj:
                return match_aj.group(1).strip().title()

            # Padrão 2: "Vara X" clássico
            match = re.search(r'(Vara\s+.*?)(?:\n|Rua|Av\.|Telefone|Fone|Email|E-mail|$)', texto, flags=re.IGNORECASE)
            if match:
                vara = match.group(1).strip()
                return re.split(r'\s{2,}', vara)[0]

            return None
        except Exception as e:
            self.logger.warning(f"Erro ao extrair vara da petição: {e}")
            return None

    def extrair_cidade_peticao(self) -> Optional[str]:
        """Extrai a Comarca do cabeçalho da petição no viewer."""
        try:
            texto = self.page.locator(".textLayer").inner_text(timeout=5000)
            # Padrão: Comarca de [CIDADE]
            match = re.search(r'Comarca(?:\s+da|\s+de)?\s+([A-Za-zÀ-Úà-ú\s]+)', texto, flags=re.IGNORECASE)
            if match:
                cidade = match.group(1).strip()
                cidade = re.split(r'\s*(?:Foro)|\s+(?:Estado|Vara|Juiz|Tribunal|SP|RJ|MG|-)', cidade, flags=re.IGNORECASE)[0]
                return cidade.strip().upper()
            return None
        except Exception as e:
            self.logger.warning(f"Erro ao extrair cidade da petição: {e}")
            return None
    
    # ========================================
    # DOWNLOAD SEGURO COM VALIDAÇÃO
    # ========================================
    
    def _baixar_documento_seguro(
        self, 
        chave: str, 
        variantes: List[str],
        paginas_esperadas: Tuple[int, int]
    ) -> ResultadoDownload:
        """
        Baixa 1 documento com validação RIGOROSA de estado atômico.
        """
        ultimo_erro = None
        
        for idx, variante in enumerate(variantes, 1):
            try:
                self.logger.info(f"   🔍 Tentando variante {idx}/{len(variantes)}: '{variante}'")
                
                # 1. LIMPAR TUDO antes de começar
                if not self._garantir_arvore_limpa():
                    self.logger.error("   ❌ Falha ao limpar árvore!")
                    continue
                
                # 2. Buscar documento
                doc_loc = self.buscar_documento_por_nome(variante)
                if not doc_loc:
                    self.logger.warning(f"   ⚠️ Documento '{variante}' não encontrado")
                    continue
                
                # 3. Extrair metadata ANTES do download
                texto_completo = doc_loc.inner_text()
                info_paginas = self.extrair_paginas_do_texto(texto_completo)
                self.logger.info(f"   📄 Metadata: {info_paginas.get('formato_fls', 'N/A')}")
                
                # 4. MARCAR via JavaScript atômico
                self.logger.info(f"   ☑️ Marcando checkbox...")
                if not self._marcar_checkbox_atomico(variante):
                    self.logger.error(f"   ❌ Falha ao marcar checkbox")
                    continue
                
                # 5. Validar que APENAS 1 documento PAI está marcado
                time.sleep(0.5)  # Aguardar animação jsTree
                count_pais = self._contar_documentos_marcados_pais()
                count_total = self.page.evaluate("document.querySelectorAll('.jstree-checked').length")
                
                self.logger.info(f"   📊 Validação: {count_pais} documento(s) pai | {count_total} total (com filhos)")
                
                if count_pais != 1:
                    self.logger.error(f"   ❌ Esperava 1 documento pai marcado, mas há {count_pais}!")
                    self._garantir_arvore_limpa()
                    continue
                
                # 6. Executar download com retry
                caminho = self._executar_download_com_retry(variante, chave, info_paginas)
                
                if caminho and caminho.exists():
                    # 7. LIMPAR IMEDIATAMENTE após download
                    self.logger.info(f"   ✅ Download concluído: {caminho.name}")
                    self._garantir_arvore_limpa()
                    
                    return ResultadoDownload(
                        documento=variante,
                        status=StatusDownload.SUCESSO,
                        mensagem=f"Download concluído ({caminho.name})",
                        caminho_arquivo=str(caminho),
                        metadata=info_paginas
                    )
                else:
                    self.logger.warning(f"   ⚠️ Download retornou caminho inválido")
                    continue
                    
            except Exception as e:
                ultimo_erro = e
                self.logger.error(f"   ❌ Erro com variante '{variante}': {e}")
                self._garantir_arvore_limpa()
                continue
        
        # Se chegou aqui, nenhuma variante funcionou
        if ultimo_erro:
            return ResultadoDownload(
                documento=chave,
                status=StatusDownload.ERRO,
                mensagem=f"Erro: {str(ultimo_erro)}"
            )
        else:
            return ResultadoDownload(
                documento=chave,
                status=StatusDownload.NAO_ENCONTRADO,
                mensagem="Nenhuma variante encontrada/baixada"
            )
    
    # ========================================
    # LIMPEZA ATÔMICA DA ÁRVORE (API jsTree)
    # ========================================
    
    def _garantir_arvore_limpa(self, max_tentativas: int = 3) -> bool:
        """
        FORÇA limpeza usando API do jsTree (não cliques DOM).
        """
        for tentativa in range(1, max_tentativas + 1):
            try:
                # Desmarcar usando API do jsTree
                resultado = self.page.evaluate("""
                    () => {
                        try {
                            const arvore = $('#arvore_principal');
                            if (!arvore.length) return {erro: 'Árvore não encontrada'};
                            
                            const tree = arvore.jstree(true);
                            if (!tree) return {erro: 'Instância jsTree não encontrada'};
                            
                            tree.uncheck_all();
                            const checked = tree.get_checked(true);
                            
                            return {
                                sucesso: true,
                                desmarcados: checked.length === 0,
                                ainda_marcados: checked.length
                            };
                        } catch (e) {
                            return {erro: e.toString()};
                        }
                    }
                """)
                
                if "erro" in resultado:
                    self.logger.error(f"   ❌ Erro na API jsTree: {resultado['erro']}")
                    # Fallback para clique DOM
                    count = self._desmarcar_via_dom()
                    self.logger.info(f"   🧹 Tentativa {tentativa} (DOM): {count} checkboxes clicados")
                else:
                    self.logger.info(f"   🧹 Tentativa {tentativa} (API): Desmarcar via jsTree.uncheck_all()")
                
                # Aguardar processamento
                time.sleep(1.5)
                
                # Validar resultado
                count_marcados = self._contar_todos_marcados()
                
                if count_marcados == 0:
                    self.logger.info(f"   ✅ Árvore 100% limpa")
                    return True
                else:
                    self.logger.warning(f"   ⚠️ Ainda há {count_marcados} marcado(s), tentando novamente...")
                    
            except Exception as e:
                self.logger.error(f"   ❌ Erro na tentativa {tentativa}: {e}")
        
        self.logger.error(f"   ❌ FALHA ao limpar após {max_tentativas} tentativas!")
        return False

    def _desmarcar_via_dom(self) -> int:
        """Fallback: desmarcar clicando diretamente nos elementos DOM."""
        return self.page.evaluate("""
            () => {
                let count = 0;
                const checked = document.querySelectorAll('.jstree-checked');
                
                checked.forEach(el => {
                    const cb = el.querySelector('.jstree-checkbox');
                    if (cb) {
                        cb.click();
                        count++;
                    }
                });
                return count;
            }
        """)

    def _contar_todos_marcados(self) -> int:
        """Conta TODOS os checkboxes marcados (pais + filhos)."""
        return self.page.evaluate("""
            () => {
                try {
                    const tree = $('#arvore_principal').jstree(true);
                    if (tree) {
                        return tree.get_checked(true).length;
                    }
                } catch (e) {}
                
                return document.querySelectorAll('.jstree-checked').length;
            }
        """)
    
    # ========================================
    # MARCAÇÃO ATÔMICA DE CHECKBOX (API jsTree)
    # ========================================
    
    def _marcar_checkbox_atomico(self, texto_documento: str) -> bool:
        """
        Marcar checkbox usando API do jsTree.
        """
        try:
            resultado = self.page.evaluate(f"""
                async (texto) => {{
                    try {{
                        const tree = $('#arvore_principal').jstree(true);
                        if (!tree) return "jsTree não encontrado";
                        
                        const nodes = tree.get_json('#', {{flat: true}});
                        const target = nodes.find(node => {{
                            const cleanText = (node.text || '').replace(/\\(Páginas?.*?\\)/i, '').trim();
                            return cleanText === texto || cleanText.startsWith(texto + ' ');
                        }});
                        
                        if (!target) return "Documento não encontrado";
                        
                        if (tree.is_checked(target.id)) return "Já estava marcado";
                        
                        tree.check_node(target.id);
                        await new Promise(resolve => setTimeout(resolve, 200));
                        
                        const isChecked = tree.is_checked(target.id);
                        return isChecked ? "Sucesso: Marcado via API" : "Falha ao marcar";
                    }} catch (e) {{
                        return "Erro: " + e.toString();
                    }}
                }}
            """, texto_documento)
            
            self.logger.info(f"   JS Marcar: {resultado}")
            return "Sucesso" in resultado or "Já estava" in resultado
            
        except Exception as e:
            self.logger.error(f"   ❌ Erro ao marcar: {e}")
            return False

    def _contar_documentos_marcados_pais(self) -> int:
        """Conta APENAS documentos PAIS marcados usando API do jsTree."""
        return self.page.evaluate("""
            () => {
                try {
                    const tree = $('#arvore_principal').jstree(true);
                    if (!tree) return 0;
                    
                    const checked = tree.get_checked(true);
                    const pais = checked.filter(node => {
                        const parent = tree.get_parent(node.id);
                        return parent === '#' || parent === 'arvore_principal';
                    });
                    return pais.length;
                } catch (e) {
                    const arvore = document.querySelector('#arvore_principal');
                    if (!arvore) return 0;
                    const pais = arvore.querySelectorAll(':scope > ul > li.jstree-checked');
                    return pais.length;
                }
            }
        """)

    def _executar_download_com_retry(self, nome_doc: str, chave: str, info_paginas: dict, max_tentativas: int = 2) -> Optional[Path]:
        """
        Executa download com retry em caso de timeout ou problemas de modal.
        """
        for tentativa in range(1, max_tentativas + 1):
            try:
                self.logger.info(f"   📥 Download tentativa {tentativa}/{max_tentativas}")
                
                # Clicar em Baixar PDF
                self.page.click(Selectors.BOTAO_BAIXAR_PDF, timeout=10000)
                time.sleep(1.5)
                
                # Verificar se apareceu o modal perguntando "Arquivo Único" x "Vários"
                try:
                    btn_continuar = self.page.locator("#botaoContinuar")
                    if btn_continuar.count() > 0 and btn_continuar.is_visible():
                        self.logger.info("   🖱️ Modal de opções detectado. Clicando em 'Continuar'...")
                        btn_continuar.click()
                        time.sleep(1.5)
                except Exception as e:
                    pass
                
                # Verificar modal de ERRO
                if self._verificar_modal_aviso_visivel():
                    self.logger.error("   ❌ Modal de ERRO apareceu (checkbox não está marcado corretamente)")
                    self._fechar_modal_aviso()
                    return None
                
                # Aguardar modal de SUCESSO
                if not self._aguardar_modal_sucesso(timeout=90000):
                    self.logger.warning(f"   ⚠️ Timeout no modal de sucesso (tentativa {tentativa})")
                    if tentativa < max_tentativas:
                        time.sleep(2.0)
                        continue
                    else:
                        return None
                
                # Executar download
                with self.page.expect_download(timeout=90000) as download_info:
                    # Garantir que overlays não bloqueiam
                    self.page.evaluate("document.querySelectorAll('.ui-widget-overlay').forEach(el => el.style.display = 'none');")
                    botao = self.page.locator(Selectors.BOTAO_SALVAR_DOCUMENTO)
                    botao.wait_for(state="visible", timeout=10000)
                    botao.click()
                
                download = download_info.value
                
                # Salvar com nome único baseado em metadata
                timestamp = int(time.time())
                prefixo = config.PREFIXOS.get(chave, "DOC")
                nome_arquivo = f"{prefixo}_{chave}_{timestamp}.pdf"
                caminho = Path(config.DOWNLOADS_DIR) / nome_arquivo
                
                download.save_as(caminho)
                
                # Fechar modal
                try:
                    btn_cancelar = self.page.locator(Selectors.BOTAO_CANCELAR_MODAL_DOWNLOAD)
                    if btn_cancelar.is_visible(timeout=2000):
                        btn_cancelar.click()
                except Exception:
                    pass
                
                time.sleep(2.0)
                return caminho
                
            except Exception as e:
                self.logger.error(f"   ❌ Erro na tentativa {tentativa}: {e}")
                if tentativa < max_tentativas:
                    time.sleep(3.0)
                continue
        return None

    def _verificar_modal_aviso_visivel(self) -> bool:
        """
        Verifica se o modal de ERRO está visível.
        
        IMPORTANTE: Tanto modal de ERRO quanto modal de SUCESSO usam #popupModalDiv como container!
        Precisamos diferenciar verificando os BOTÕES:
        - Modal de ERRO: tem botão "Ok" e NÃO tem botão "Salvar o documento"
        - Modal de SUCESSO: tem botão "Salvar o documento"
        
        NÃO fecha o modal - apenas retorna True/False.
        """
        try:
            # Primeiro verificar se o container está visível
            if not self.page.locator(Selectors.MODAL_AVISO).is_visible():
                return False
            
            # Verificar presença de botões específicos
            tem_botao_ok = False
            tem_botao_salvar = False
            
            try:
                tem_botao_ok = self.page.locator(Selectors.BOTAO_OK_MODAL).is_visible()
            except Exception:
                pass
            
            try:
                tem_botao_salvar = self.page.locator(Selectors.BOTAO_SALVAR_DOCUMENTO).is_visible()
            except Exception:
                pass
            
            # É modal de ERRO apenas se:
            # 1. Tem botão "Ok" E
            # 2. NÃO tem botão "Salvar o documento"
            e_modal_erro = tem_botao_ok and not tem_botao_salvar
            
            if e_modal_erro:
                self.logger.debug("   🔍 Modal detectado: ERRO (tem Ok, não tem Salvar)")
            elif tem_botao_salvar:
                self.logger.debug("   🔍 Modal detectado: SUCESSO (tem Salvar)")
            else:
                self.logger.debug("   🔍 Modal detectado: tipo DESCONHECIDO")
            
            return e_modal_erro
            
        except Exception as e:
            self.logger.debug(f"   Erro ao verificar modal de aviso: {e}")
            return False
    
    def _fechar_modal_aviso(self) -> bool:
        """
        Fecha o modal de ERRO clicando no botão 'Ok'.
        Retorna True se conseguiu fechar, False caso contrário.
        """
        try:
            if self.page.locator(Selectors.MODAL_AVISO).is_visible():
                self.logger.info("   🖱️ Fechando modal de ERRO (clicando em 'Ok')...")
                self.page.locator(Selectors.BOTAO_OK_MODAL).click()
                time.sleep(1)  # Aguardar modal desaparecer
                
                # Validar se realmente sumiu
                if not self.page.locator(Selectors.MODAL_AVISO).is_visible():
                    self.logger.info("   ✅ Modal de ERRO fechado com sucesso")
                    return True
                else:
                    self.logger.warning("   ⚠️ Modal de ERRO ainda visível após clique")
                    return False
            return True  # Já estava fechado
        except Exception as e:
            self.logger.error(f"   ❌ Erro ao fechar modal de aviso: {e}")
            return False
    
    def _aguardar_modal_sucesso(self, timeout: int = 60000) -> bool:
        """
        Aguarda o modal de SUCESSO aparecer.
        Modal de SUCESSO contém:
        - Texto "GERANDO O DOCUMENTO PARA IMPRESSÃO..."
        - Botão "Salvar o documento" (#btnDownloadDocumento)
        
        Retorna True se modal de SUCESSO apareceu, False caso contrário.
        """
        try:
            # Esperar pelo texto do modal de geração (opcional, pois pode não aparecer sempre)
            try:
                self.page.wait_for_selector("text=GERANDO O DOCUMENTO", timeout=5000)
                self.logger.info("   📄 Texto 'GERANDO O DOCUMENTO' detectado")
            except Exception:
                self.logger.debug("   ⚠️ Texto 'GERANDO O DOCUMENTO' não detectado (pode ser normal)")
            
            # Aguardar botão "Salvar o documento" (CRÍTICO)
            self.logger.info(f"   ⏳ Aguardando botão 'Salvar o documento' (timeout: {timeout/1000}s)...")
            self.page.wait_for_selector(Selectors.BOTAO_SALVAR_DOCUMENTO, state="visible", timeout=timeout)
            
            self.logger.info("   ✅ Modal de SUCESSO confirmado (botão 'Salvar o documento' visível)")
            return True
            
        except TimeoutError as e:
            # Timeout específico - botão não ficou visível no tempo esperado
            self.logger.error(f"   ❌ TIMEOUT: Botão 'Salvar o documento' não apareceu após {timeout/1000}s")
            self.logger.error(f"   Detalhes: {e}")
            self._debug_snapshot("timeout_modal_sucesso")
            return False
        except Exception as e:
            # Outras exceções (seletor inválido, erro de rede, etc.)
            self.logger.error(f"   ❌ ERRO ao aguardar modal de SUCESSO")
            self.logger.error(f"   Tipo: {type(e).__name__}")
            self.logger.error(f"   Mensagem: {str(e)}")
            self._debug_snapshot("erro_modal_sucesso")
            return False

    def _debug_snapshot(self, prefix: str):
        """Salva screenshot e HTML para depuração em caso de erro."""
        try:
            timestamp = int(time.time())
            path_img = f"debug_{prefix}_{timestamp}.png"
            path_html = f"debug_{prefix}_{timestamp}.html"
            
            self.page.screenshot(path=path_img, full_page=True)
            with open(path_html, "w", encoding="utf-8") as f:
                f.write(self.page.content())
            
            self.logger.info(f"📸 Snapshot de erro salvo: {path_img}")
        except Exception as e:
            self.logger.error(f"Erro ao salvar snapshot: {e}")

    def extrair_paginas_do_texto(self, texto: str) -> Optional[Dict[str, Union[int, str]]]:
        if not texto: return None
        # Regex aceita números com ponto separador de milhar (ex: "Página 1.852")
        match_intervalo = re.search(r'P[aá]ginas?\s+([\d.]+)\s*-\s*([\d.]+)', texto, re.IGNORECASE)
        match_unica = re.search(r'P[aá]ginas?\s+([\d.]+)', texto, re.IGNORECASE)
        
        resultado = {
            'pagina_inicial': 0, 'pagina_final': 0,
            'texto_paginas': texto, 'formato_fls': ''
        }
        
        def parse_num(s: str) -> int:
            """Remove ponto de milhar e converte para inteiro (ex: '1.852' -> 1852)"""
            return int(s.replace('.', ''))
        
        if match_intervalo:
            i, f = parse_num(match_intervalo.group(1)), parse_num(match_intervalo.group(2))
            resultado.update({'pagina_inicial': i, 'pagina_final': f, 'formato_fls': f"fls. {i}/{f}"})
        elif match_unica:
            p = parse_num(match_unica.group(1))
            resultado.update({'pagina_inicial': p, 'pagina_final': p, 'formato_fls': f"fls. {p}"})
            
        return resultado

    # ========================================
    # HEURÍSTICAS AVANÇADAS (HOMOLOGO / FLS)
    # ========================================

    def extrair_valor_rejeicao_impugnacao(self) -> Optional[float]:
        """
        Busca o valor após o trecho 'REJEITADA A IMPUGNACAO' na petição/decisão aberta.
        """
        try:
            texto_completo = self.page.locator(".textLayer").inner_text(timeout=5000)
            if "REJEITADA A IMPUGNACAO" in texto_completo.upper():
                # Procurar valor monetário após o termo
                match = re.search(r'REJEITADA A IMPUGNAC[AÃ]O.*?R\$\s*([\d.,]+)', texto_completo, re.IGNORECASE | re.DOTALL)
                if match:
                    valor_str = match.group(1).replace(".", "").replace(",", ".")
                    return float(valor_str)
            return None
        except Exception as e:
            self.logger.warning(f"Erro ao extrair valor de rejeição: {e}")
            return None

    def coletar_todos_candidatos(self, nome: str):
        """Retorna todos os locators que casam com o nome (regex ignorecase) na árvore."""
        try:
            # Transforma "Decisão" em "Decis[ãa]o" para suportar sem acento e case insensitive
            padrao = nome.replace('ã', '[ãa]').replace('ç', '[çc]')
            import re
            regex_nome = re.compile(padrao, re.IGNORECASE)
            
            # Pega todos os nós que contenham o nome via regex
            elementos = self.page.locator(f"{Selectors.ARVORE_PRINCIPAL} .jstree-anchor").filter(has_text=regex_nome)
            count = elementos.count()
            locators = [elementos.nth(i) for i in range(count)]
            self.logger.info(f"   🔍 Encontrados {len(locators)} candidatos para regex '{padrao}'")
            return locators
        except Exception as e:
            self.logger.error(f"Erro ao coletar candidatos para {nome}: {e}")
            return []

    def analisar_homologo_em_pdf(self, caminho_pdf: Path) -> Tuple[bool, Optional[str], str]:
        """
        Analisa o PDF em busca da palavra 'HOMOLOGO' e status de impugnação.
        Retorna (encontrado, texto_fls, status_impugnacao).
        """
        try:
            texto_extraido = ""
            
            # 1. Tentar extração direta de texto com pdfplumber
            with pdfplumber.open(caminho_pdf) as pdf:
                for page in pdf.pages:
                    texto_extraido += (page.extract_text() or "") + "\n"
            
            # 2. Se o texto está muito curto, tentar OCR
            if len(texto_extraido.strip()) < 100:
                self.logger.info("   🔍 Texto insuficiente no PDF, tentando OCR...")
                texto_extraido = self._executar_ocr_pdf(caminho_pdf)
            
            from classes.pdf_extractor import PDFExtractor
            extractor = PDFExtractor(caminho_pdf)
            status_impugnacao = extractor.analisar_homologacao(texto_ocr=texto_extraido)
            
            # 3. Buscar 'HOMOLOGO' e extrair contexto
            if re.search(r'homologo', texto_extraido, re.IGNORECASE):
                self.logger.info(f"   ✅ Palavra 'HOMOLOGO' encontrada! Status: {status_impugnacao}")
                pos = texto_extraido.upper().find("HOMOLOGO")
                inicio = max(0, pos - 250)
                fim = min(len(texto_extraido), pos + 250)
                contexto = str(texto_extraido)[inicio:fim]
                
                match_fls = re.search(
                    r'(?:à[s]?|a)?\s*fl[s]?\.?\s*:?\s*(\d+(?:\.\d+)?(?:\s*[-/]\s*\d+(?:\.\d+)?)?)',
                    contexto, re.IGNORECASE
                )
                fls_contexto = match_fls.group(1).strip() if match_fls else None
                
                return True, fls_contexto, status_impugnacao
            
            return False, None, status_impugnacao
        except Exception as e:
            self.logger.error(f"Erro na análise de PDF: {e}")
            return False, None, "erro"
        except Exception as e:
            self.logger.error(f"Erro na análise de PDF: {e}")
            return False, None

    def _executar_ocr_pdf(self, caminho_pdf: Path) -> str:
        """Converte PDF para imagem e aplica Tesseract."""
        try:
            # Configurar poppler_path se necessário no convert_from_path
            imagens = convert_from_path(str(caminho_pdf), poppler_path=config.POPPLER_PATH)
            texto_ocr = ""
            for img in imagens:
                texto_ocr += pytesseract.image_to_string(img, lang='por') + "\n"
            return texto_ocr
        except Exception as e:
            self.logger.error(f"Falha no OCR: {e}")
            return ""

    def _baixar_temporario(self, locator: Locator, chave: str) -> Optional[Path]:
        """Baixa o documento para a pasta temp para análise."""
        try:
            # Garantir limpeza antes de marcar
            self._garantir_arvore_limpa()
            
            texto_node = locator.inner_text()
            self.logger.info(f"   📥 Baixando temporário para análise: {texto_node}")
            
            # Marcar o nó
            if not self._marcar_checkbox_atomico(texto_node):
                return None
            
            # Clicar baixar
            self.page.click(Selectors.BOTAO_BAIXAR_PDF)
            
            if not self._aguardar_modal_sucesso(timeout=45000):
                self._fechar_modal_aviso()
                return None
            
            with self.page.expect_download(timeout=60000) as download_info:
                self.page.locator(Selectors.BOTAO_SALVAR_DOCUMENTO).click()
            
            download = download_info.value
            nome_temp = f"temp_{int(time.time())}.pdf"
            caminho = config.TEMP_DIR / nome_temp
            download.save_as(caminho)
            
            # Fechar modal
            try: self.page.locator(Selectors.BOTAO_CANCELAR_MODAL_DOWNLOAD).click(timeout=2000)
            except: pass
            
            return caminho
        except Exception as e:
            self.logger.error(f"Erro no download temporário: {e}")
            return None

    def processar_selecao_complexa(self) -> Dict[str, ResultadoDownload]:
        """
        Orquestra a seleção da Decisão (via HOMOLOGO) e Planilha.
        LÓGICA DE NEGÓCIO:
        1. Se impugnação acolhida -> Planilha da Fazenda (Diversos).
        2. Se impugnação rejeitada ou s/ impugnação -> Planilha do Escritório (pós-sentença).
        """
        self.logger.info("🧠 Iniciando seleção inteligente (Decisão + Planilha)...")
        resultados = {}
        
        # 1. Coletar todos os candidatos a Decisão
        candidatos_decisao = self.coletar_todos_candidatos("Decisão")
        if not candidatos_decisao:
            self.logger.warning("❌ Nenhuma 'Decisão' encontrada na árvore.")
            return {}

        # 2. Analisar do mais recente (baixo) para o mais antigo (cima)
        decisao_eleita = None
        fls_referencia = None
        status_impugnacao = "nao_detectada"
        
        for i in range(len(candidatos_decisao) - 1, -1, -1):
            locator = candidatos_decisao[i]
            caminho_temp = self._baixar_temporario(locator, "decisao")
            
            if caminho_temp and caminho_temp.exists():
                encontrado, fls, status = self.analisar_homologo_em_pdf(caminho_temp)
                
                try: os.remove(caminho_temp)
                except: pass
                
                if encontrado:
                    decisao_eleita = locator
                    fls_referencia = fls
                    status_impugnacao = status
                    self.logger.info(f"   🏆 Decisão correta encontrada (Índice {i}). Status Impugnação: {status_impugnacao}")
                    break
        
        # 2.1 FALLBACK: Se não achou decisão homologatória, buscar petição de "não se opõe" (Requisito 2.2)
        if not decisao_eleita:
            self.logger.info("   🔍 Nenhuma decisão com 'HOMOLOGO' encontrada. Tentando fallback 'não se opõe'...")
            concordancia = self.buscar_concordancia_fazenda()
            if concordancia:
                decisao_eleita = concordancia['locator']
                fls_referencia = concordancia['fls']
                status_impugnacao = "concordancia_direta"
                self.logger.info(f"   🤝 Concordância direta encontrada: {concordancia['texto']}")
        
        # 3. Execução da Lógica de Planilha
        if decisao_eleita:
            # Download definitivo da decisão
            texto_decisao = decisao_eleita.inner_text()
            res_dec = self._baixar_documento_seguro("decisao", [texto_decisao], (0,0))
            resultados["decisao"] = res_dec
            
            # LÓGICA DE ESCOLHA DA PLANILHA
            if status_impugnacao == "acolhida":
                # REQUISITO: Se acolheu, buscar a planilha que está na impugnação (ou anexa)
                self.logger.info("   🔍 Impugnação ACOLHIDA. Buscando planilha da Fazenda Pública...")
                impugnacao_loc = self.buscar_documento_por_nome("Impugnação ao Cumprimento de Sentença")
                if impugnacao_loc:
                     # Baixar os anexos da impugnação (Diversos)
                     self.logger.info("   📥 Baixando planilhas anexas à Impugnação (Diversos)...")
                     ids_diversos = self.page.evaluate(f"""
                        () => {{
                            const tree = $('#arvore_principal').jstree(true);
                            const nodes = tree.get_json('#', {{flat: true}});
                            const baseText = "{impugnacao_loc.inner_text()}";
                            const idx = nodes.findIndex(n => n.text.includes(baseText));
                            if (idx === -1) return [];
                            // Pega os 2 seguintes que geralmente são as planilhas da fazenda
                            return nodes.slice(idx + 1, idx + 3).map(n => n.id);
                        }}
                     """)
                     for node_id in ids_diversos:
                         self._baixar_documento_por_id_jstree(node_id, "planilhacalculo")
                     
                     # Marcar como sucesso para o fluxo principal
                     resultados["planilhacalculo"] = ResultadoDownload(
                         documento="Planilha da Fazenda", status=StatusDownload.SUCESSO, 
                         mensagem="Planilha da Fazenda baixada via anexos da Impugnação"
                     )
            
            else:
                # REQUISITO: Se rejeitou ou não houve, usar a nossa (casar por FLS)
                self.logger.info(f"   🔍 Impugnação {status_impugnacao.upper()}. Buscando planilha do escritório pós-sentença...")
                if fls_referencia:
                    candidatos_planilha = self.coletar_todos_candidatos("Planilha")
                    planilha_eleita = self.casar_planilha_por_fls(candidatos_planilha, fls_referencia)
                    
                    if planilha_eleita:
                        texto_planilha = planilha_eleita.inner_text()
                        res_plan = self._baixar_documento_seguro("planilhacalculo", [texto_planilha], (0,0))
                        
                        # Extrair data de protocolo (Data Base - 3.3)
                        self._abrir_documento_viewer(planilha_eleita)
                        data_proto = self.extrair_data_protocolo_peticao()
                        if data_proto:
                            res_plan.metadata['data_protocolo'] = data_proto
                            self.logger.info(f"   📅 Data de protocolo (Data Base) extraída: {data_proto}")
                            
                        resultados["planilhacalculo"] = res_plan
                    else:
                        self.logger.warning("   ⚠️ Nenhuma planilha casou com as FLS da decisão.")
        else:
            self.logger.error("❌ Não foi possível identificar a Decisão de Homologação via HOMOLOGO ou Concordância.")
            return {}

        return resultados

    def buscar_concordancia_fazenda(self) -> Optional[Dict[str, Any]]:
        """
        Busca por petições/manifestações que contenham o termo 'não se opõe' ou 'concorda'
        na descrição ou no conteúdo inicial, conforme Requisito 2.2.
        """
        self.logger.info("   🧐 Buscando petição de concordância (não se opõe)...")
        
        # 1. Buscar candidatos por nome de documento comum para concordância
        palavras_chave = ["Petição", "Manifestação", "Concordância"]
        candidatos = []
        for pc in palavras_chave:
            candidatos.extend(self.coletar_todos_candidatos(pc))
        
        # 2. Analisar os 5 mais recentes (para não demorar demais)
        for loc in candidatos[:5]:
            texto_no = loc.inner_text()
            caminho = self._baixar_temporario(loc, "concordancia")
            if not caminho: continue
            
            try:
                with pdfplumber.open(caminho) as pdf:
                    texto = ""
                    for p in pdf.pages[:2]: # Analisa só as 2 primeiras páginas
                        texto += (p.extract_text() or "").upper()
                
                termos_sucesso = ["NÃO SE OPÕE", "NAO SE OPOE", "CONCORDA COM OS CÁLCULOS", "MANIFESTA CONCORDÂNCIA"]
                if any(t in texto for t in termos_sucesso):
                    # Extrair FLS se houver
                    match_fls = re.search(r'FLS\.?\s*(\d+)', texto, re.IGNORECASE)
                    fls = match_fls.group(1) if match_fls else None
                    
                    try: os.remove(caminho)
                    except: pass
                    
                    return {
                        'locator': loc,
                        'texto': texto_no,
                        'fls': fls
                    }
                
                try: os.remove(caminho)
                except: pass
            except Exception as e:
                self.logger.warning(f"Erro ao analisar possível concordância: {e}")
                
        return None

    def casar_planilha_por_fls(self, candidatos: List[Locator], fls_alvo: str) -> Optional[Locator]:
        """
        Compara o número fls_alvo com as páginas descritas no texto dos nós da árvore.
        Ex: fls_alvo="335" vs "Planilha de Cálculo (Páginas 335-338)"
        """
        if not fls_alvo: return None
        
        # Extrair apenas o primeiro número se for um intervalo
        num_alvo = re.search(r'(\d+)', fls_alvo)
        if not num_alvo: return None
        n_alvo = int(num_alvo.group(1))
        
        for loc in candidatos:
            texto = loc.inner_text()
            info = self.extrair_paginas_do_texto(texto)
            if info and int(info['pagina_inicial']) <= n_alvo <= int(info['pagina_final']):
                self.logger.info(f"   ✅ Planilha casou com FLS {n_alvo}: {texto}")
                return loc
                
        return None
