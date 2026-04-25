import threading
import queue
import time
import logging
from classes.tribunal_scraper import TribunalScraper


from classes.types_download import StatusDownload

class ThreadedScraper(threading.Thread):
    """
    Wrapper thread-safe para TribunalScraper.
    Executa operações Playwright em thread separada para não bloquear UI do Tkinter.
    """
    
    def __init__(self, numero_processo, callback_queue):
        """
        Args:
            numero_processo: Número do processo a ser consultado
            callback_queue: Queue para enviar mensagens para a UI
        """
        super().__init__(daemon=True)
        self.numero_processo = numero_processo
        self.callback_queue = callback_queue
        self.scraper = None
        self._stop_event = threading.Event()
        self.error = None
        self.success = False
        self.resultados_scraping = None
        self.url_pasta_digital = ""
        
    def run(self):
        """Loop principal da thread - executa todas as operações do scraper"""
        try:
            self._emit_progress("Iniciando navegador...", 10)
            self.scraper = TribunalScraper(self.numero_processo)
            
            if self._should_stop():
                return
            
            self.scraper.iniciar_navegador(headless=False)
            
            self._emit_progress("Acessando tribunal...", 20)
            if self._should_stop():
                return
            self.scraper.acessar_tribunal()
            
            self._emit_progress("Pesquisando processo...", 40)
            if self._should_stop():
                return
            self.scraper.pesquisar_processo()
            
            self._emit_progress("Processando documentos (Orquestrador Automático)...", 50)
            if self._should_stop():
                return
            
            # Utilizar o orquestrador para baixar todos os documentos sequencialmente
            # Retorna Dict[str, ResultadoDownload]
            retorno_scraping = self.scraper.processar_todos_documentos()
            
            # Guardar resultados para acesso via main.py
            self.resultados_scraping = retorno_scraping
            self.url_pasta_digital = self.scraper.url_pasta_digital
            
            # Verificar se houve falha crítica (retorno vazio ou None)
            if not retorno_scraping:
                raise Exception("Falha crítica no processamento de documentos")
            
            # Contar sucessos usando o novo objeto ResultadoDownload
            sucessos = sum(1 for r in retorno_scraping.values() if r.status == StatusDownload.SUCESSO)
            total_esperado = len(retorno_scraping)
            
            logging_msg = f"Documentos baixados: {sucessos}/{total_esperado}"
            print(f"THREAD: {logging_msg}")
            
            # if sucessos == 0:
            #      raise Exception("Nenhum documento foi baixado com sucesso.")
            
            if sucessos < total_esperado:
                self._emit_progress(f"Atenção: {logging_msg}", 95)
                # Não lança erro fatal, permite continuar com o que tem e o dialog vai mostrar
            
            self._emit_progress("Concluído!", 100)
            self.success = True
                
        except Exception as e:
            self.error = e
            self._emit_error(e)

        finally:
            self._cleanup()
    
    def _emit_progress(self, message, progress):
        """Envia atualização de progresso para a UI"""
        self.callback_queue.put({
            'type': 'progress',
            'message': message,
            'progress': progress
        })
    
    def _emit_error(self, error_obj):
        """Envia erro para a UI preservando o objeto Exception"""
        self.callback_queue.put({
            'type': 'error',
            'error_obj': error_obj,
            'message': str(error_obj)
        })
    
    def _should_stop(self):
        """Verifica se a thread deve parar"""
        return self._stop_event.is_set()
    
    def stop(self):
        """Sinaliza para a thread parar"""
        self._stop_event.set()
    
    def _cleanup(self):
        """Limpa recursos do scraper (não fecha o navegador para permitir acesso posterior)"""
        # O navegador agora deve ser fechado manualmente pelo fluxo principal (main.py)
        # se o usuário não optar por abrir a pasta digital.
        pass
    
    def get_scraper(self):
        """Retorna instância do scraper (após thread terminar)"""
        return self.scraper
