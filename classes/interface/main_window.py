import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import queue
import logging
import os
import time
import sys
import threading
from typing import Dict, List, Optional, Any, Callable

from .theme import COLORS, FONTS
from .dialogs import (
     SolicitarNumeroDialog, 
     DialogoResultadoDownload, 
     DialogoAnalisePlaceholders, 
     DialogoAtivacao,
     DialogoHallAutores,
     DialogoTipoDocumento,
     ConfirmDialog,
     DialogoTermosUso
)

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Configurações básicas - Janela Fantasma Profissional (STABLE)
        # Evitamos withdraw() pois CustomTkinter no Windows tem bugs com pais 'withdrawn'.
        # Mantemos a janela 'ativa' para o SO, mas invisível ao usuário.
        self.title("Automação Judicial")
        self.geometry("1x1+-2000+-2000")  # Fora da tela
        try:
            self.overrideredirect(True)       # Remove da barra de tarefas e tira bordas
            self.attributes("-alpha", 0.0)      # Torna totalmente transparente
            self.lift()                       # Garante que está no fluxo de janelas
        except Exception:
            pass
            
        self.protocol("WM_DELETE_WINDOW", self.fechar)
        
        # Estado Interno
        self.janela_progresso = None
        self.label_status = None
        self.progressbar = None
        self.btn_cancelar = None
        self.reiniciar_sistema = False
        self.callback_cancelar = None


    def fechar(self):
        """Fecha a aplicação e encerra o processo completamente."""
        print("\n[!] Finalizando aplicação...")
        os._exit(0)

    # --- PROGRESSO DO SCRAPING ---

    def mostrar_janela_progresso(self, callback_cancelar=None):
        """Cria e exibe uma janela de progresso modal."""
        self.callback_cancelar = callback_cancelar
        
        # Se a janela já existe, foca nela
        if self.janela_progresso and self.janela_progresso.winfo_exists():
            self.janela_progresso.focus_set()
            return

        self.janela_progresso = ctk.CTkToplevel(self)
        self.janela_progresso.title("Progresso da Automação")
        self.janela_progresso.geometry("500x250")
        self.janela_progresso.resizable(True, True)
        try:
            self.janela_progresso.grab_set()
        except Exception:
            pass
        
        # Centralizar
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 250
        y = (self.winfo_screenheight() // 2) - 125
        self.janela_progresso.geometry(f"+{x}+{y}")

        # Interface da Janela de Progresso
        ctk.CTkLabel(self.janela_progresso, text="Automação em Execução", font=FONTS['subtitle'], text_color=COLORS['primary']).pack(pady=(20, 10))
        
        self.label_status = ctk.CTkLabel(self.janela_progresso, text="Iniciando...", font=FONTS['normal'])
        self.label_status.pack(pady=10)

        self.progressbar = ctk.CTkProgressBar(self.janela_progresso, width=400)
        self.progressbar.pack(pady=20)
        self.progressbar.set(0)

        self.btn_cancelar = ctk.CTkButton(
            self.janela_progresso, 
            text="Cancelar/Parar", 
            command=self._cancelar_clique,
            fg_color=COLORS['error'],
            hover_color="#b5433f"
        )
        self.btn_cancelar.pack(pady=10)

        # Tratar fechamento manual da janela de progresso (X) e minimizar
        self.janela_progresso.protocol("WM_DELETE_WINDOW", self.fechar)
        self.janela_progresso.bind("<Unmap>", self._on_minimize_app)

    def _on_minimize_app(self, event):
        """Encerra o programa se a janela for minimizada."""
        try:
            # event.widget pode ser a janela_progresso ou self (App)
            if event.widget.state() == 'iconic':
                self.fechar()
        except Exception:
            pass

    def atualizar_progresso(self, porcentagem: int, status: str):
        """Atualiza a barra de progresso e o texto de status."""
        if self.label_status and self.label_status.winfo_exists():
            self.label_status.configure(text=status)
        
        if self.progressbar and self.progressbar.winfo_exists():
            self.progressbar.set(porcentagem / 100.0)
        
        self.update()

    def fechar_janela_progresso(self):
        """Fecha a janela de progresso e libera o foco (grab)."""
        if self.janela_progresso and self.janela_progresso.winfo_exists():
            try:
                self.janela_progresso.grab_release()
            except Exception:
                pass
            try:
                self.janela_progresso.destroy()
            except Exception:
                pass
        self.janela_progresso = None

    def _cancelar_clique(self):
        """Chamada quando o usuário clica em cancelar."""
        if messagebox.askyesno("Confirmar", "Deseja realmente cancelar a automação em curso?"):
            if self.callback_cancelar:
                self.callback_cancelar()
            self.fechar_janela_progresso()

    # --- COMUNICAÇÃO COM THREADS ---

    def processar_queue(self, q: queue.Queue, thread: threading.Thread, on_success: Callable, on_error: Callable):
        """Monitora a fila de mensagens da thread do scraper para atualizar a UI em tempo real."""
        try:
            # Tenta processar todas as mensagens pendentes na fila
            while True:
                try:
                    msg = q.get_nowait()
                    if msg['type'] == 'progress':
                        self.atualizar_progresso(msg['progress'], msg['message'])
                    elif msg['type'] == 'error':
                        self.fechar_janela_progresso()
                        on_error(msg['error_obj'])
                        return
                    elif msg['type'] == 'success':
                        self.fechar_janela_progresso()
                        self.after(0, on_success)
                        return
                except queue.Empty:
                    break

            # Se a thread parou e não enviou mensagem definitiva, verifica estado
            if not thread.is_alive():
                self.fechar_janela_progresso()
                if getattr(thread, 'success', False):
                    on_success()
                elif getattr(thread, 'error', None):
                    on_error(thread.error)
                return

            # Agenda próxima verificação em 100ms
            self.after(100, lambda: self.processar_queue(q, thread, on_success, on_error))
        except Exception as e:
            logging.error(f"Erro ao processar fila: {e}", exc_info=True)
            self.mostrar_erro("Erro Interno", f"Falha ao processar atualizações da automação: {e}")

    # --- MÉTODOS DE COMPATIBILIDADE E UTILIDADE ---

    def mostrar_mensagem(self, titulo: str, mensagem: str):
        messagebox.showinfo(titulo, mensagem)

    def mostrar_erro(self, titulo: str, mensagem: str):
        messagebox.showerror(titulo, mensagem)

    def mostrar_confirmacao(self, titulo: str, mensagem: str) -> bool:
        import logging
        logging.info(f"❓ Solicitando confirmação: {titulo}")
        dialog = ConfirmDialog(self, titulo, mensagem)
        self.wait_window(dialog)
        return dialog.resultado

    def pedir_numero_processo(self) -> Optional[str]:
        import logging
        while True:
            logging.info("📝 Solicitando número do processo...")
            dialog = SolicitarNumeroDialog(self)
            self.wait_window(dialog)
            
            if dialog.abrir_configs:
                self.mostrar_configuracoes()
                # Após fechar configs, volta a pedir o número
                continue
            
            return dialog.resultado

    def mostrar_configuracoes(self):
        from .dialogs import DialogoConfiguracoes
        dialog = DialogoConfiguracoes(self)
        self.wait_window(dialog)
        if dialog.salvou:
            self.reiniciar_sistema = True
            # Força o reinício do loop no main.py
            return

    def solicitar_ativacao(self, machine_id: str) -> Optional[str]:
        dialog = DialogoAtivacao(self, machine_id)
        self.wait_window(dialog)
        return dialog.chave

    def mostrar_termos_uso(self) -> bool:
        """Exibe os termos de uso e retorna True se o usuário aceitou."""
        dialog = DialogoTermosUso(self)
        self.wait_window(dialog)
        return getattr(dialog, 'aceitou', False)

    def mostrar_resultados_download(self, resultados: Dict, url: str = "", on_abrir_pasta=None):
        dialog = DialogoResultadoDownload(self, resultados, url, on_abrir_pasta_automacao=on_abrir_pasta)
        self.wait_window(dialog)

    def mostrar_relatorio_downloads(self, resultados: Dict, url: str = "", on_abrir_pasta=None):
        """Alias para manter compatibilidade com main.py"""
        self.mostrar_resultados_download(resultados, url, on_abrir_pasta=on_abrir_pasta)

    def mostrar_analise_placeholders(self, dados: Dict) -> Dict:
        """Exibe o diálogo de conferência e edição de dados extraídos."""
        import logging
        logging.info("🖥️ Abrindo Espelho de Dados Identificados...")
        dialog = DialogoAnalisePlaceholders(self, dados)
        self.wait_window(dialog)
        return getattr(dialog, 'novos_dados', dados)

    def perguntar_embargos(self) -> bool:
        return self.mostrar_confirmacao(
            "Embargos / Impugnação", 
            "Houve oposição de Embargos à Execução ou Impugnação ao Cumprimento de Sentença neste processo?"
        )

    def mostrar_hall_autores(self, lista_autores_pendentes: List[str]) -> List[str]:
        """Exibe o Hall de Autores usando CustomTkinter (Canvas nativo, sem CTkScrollableFrame)."""
        if not lista_autores_pendentes:
            return []
        logging.info(f"👥 Abrindo Hall de Autores para {len(lista_autores_pendentes)} pendentes...")

        dialog = DialogoHallAutores(self, lista_autores_pendentes)
        self.wait_window(dialog)

        logging.info(f"✅ Hall de Autores fechado. Selecionados: {getattr(dialog, 'selecionados', [])}")
        return getattr(dialog, 'selecionados', [])

    def selecionar_tipo_documento(self) -> Optional[str]:
        # Carregar templates dinamicamente
        import sys
        import os
        from pathlib import Path
        
        try:
            # Obtém a pasta de templates importando o config globalmente
            sys.path.insert(0, str(Path(__file__).parent.parent.parent))
            import config
            templates = []
            if config.TEMPLATES_DIR.exists():
                for f in config.TEMPLATES_DIR.glob("*.docx"):
                    if not f.name.startswith("~$"):
                        templates.append(f.stem)
        except Exception:
            templates = []
                
        if not templates:
            templates = ["Peticao Intermediaria", "Substabelecimento"] # Fallback
            
        dialog = DialogoTipoDocumento(self, templates)
        self.wait_window(dialog)
        return getattr(dialog, 'resultado', None)

    def confirmar_documento_gerado(self, output_docx_path) -> bool:
        return self.mostrar_confirmacao(
            "Aprovação de Documento", 
            f"O documento '{output_docx_path.name}' está correto?\n\nDeseja prosseguir?"
        )

    def perguntar_novos_peticionamentos(self, lista_autores_pendentes: List[str]) -> bool:
        return self.mostrar_confirmacao(
            "Novos Peticionamentos", 
            f"Ainda faltam {len(lista_autores_pendentes)} requerentes.\n\nDeseja iniciar um novo ciclo de peticionamento para eles?"
        )

    def solicitar_valor_planilha(self) -> Optional[float]:
        """Solicita ao usuário o valor da planilha quando não foi possível extrair automaticamente."""
        from .dialogs import SolicitarValorPlanilhaDialog
        dialog = SolicitarValorPlanilhaDialog(self)
        self.wait_window(dialog)
        return getattr(dialog, 'valor', None)

# Alias para compatibilidade retrô
TkinterInterface = App
