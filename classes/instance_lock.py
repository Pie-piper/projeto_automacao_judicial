import os
import sys
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class InstanceLock:
    """
    Garante que apenas uma instância do programa esteja em execução.
    Cria um arquivo de lock que é removido ao fechar o programa.
    """
    
    LOCK_FILE = ".app.lock"
    
    def __init__(self):
        self.lock_path = Path(config.BASE_DIR) / self.LOCK_FILE if 'config' in dir() else Path.cwd() / self.LOCK_FILE
        self.pid = os.getpid()
        self.obtido = False
    
    def __enter__(self):
        return self._obter_lock()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.obtido:
            self._liberar_lock()
    
    def _obter_lock(self) -> bool:
        """Tenta obter o lock. Retorna True se bem-sucedido."""
        if self.lock_path.exists():
            try:
                with open(self.lock_path, 'r') as f:
                    pid_antigo = int(f.read().strip())
                
                # Verificar se o processo antigo ainda está rodando
                if self._is_process_running(pid_antigo):
                    logger.error(f"Outra instância já está em execução (PID: {pid_antigo})")
                    return False
                else:
                    logger.info(f"Lock antigo (PID: {pid_antigo}) encontrado de processo já finalizado. Removendo...")
                    self.lock_path.unlink()
            except (ValueError, FileNotFoundError):
                self.lock_path.unlink()
        
        try:
            with open(self.lock_path, 'w') as f:
                f.write(str(self.pid))
            self.obtido = True
            logger.info(f"Lock obtido com sucesso (PID: {self.pid})")
            return True
        except Exception as e:
            logger.error(f"Falha ao criar lock: {e}")
            return False
    
    def _liberar_lock(self):
        """Libera o lock removendo o arquivo."""
        try:
            if self.lock_path.exists():
                self.lock_path.unlink()
                logger.info("Lock liberado")
        except Exception as e:
            logger.warning(f"Erro ao liberar lock: {e}")
    
    def _is_process_running(self, pid: int) -> bool:
        """Verifica se um processo está em execução."""
        try:
            if sys.platform == 'win32':
                import ctypes
                PROCESS_QUERY_LIMITED_INFORMATION = 0x0100
                handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                if handle:
                    ctypes.windll.kernel32.CloseHandle(handle)
                    return True
                return False
            else:
                os.kill(pid, 0)
                return True
        except (ProcessLookupError, PermissionError):
            return False
        except Exception:
            return False


def verificar_instancia_unica():
    """Função de conveniência para verificar instância única."""
    lock = InstanceLock()
    if not lock._obter_lock():
        return None
    return lock
