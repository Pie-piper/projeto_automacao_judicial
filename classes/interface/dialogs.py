import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from typing import Dict, Any, List, Optional
import os
import re
import webbrowser
from .theme import COLORS, FONTS
from ..types_download import ResultadoDownload, StatusDownload

class BaseDialog(ctk.CTkToplevel):
    def __init__(self, parent, title="Diálogo", width=400, height=300):
        super().__init__(parent)
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.resizable(True, True)
        self._mousewheel_bindings = []  # Rastreia todos os bindings para cleanup
        
        # Vincular ao pai e forçar topo inicial
        self.transient(parent)
        self.attributes("-topmost", True)
        
        # Tratar fechamento pelo X e Minimizar (BUG FIX: encerrar programa conforme pedido)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Unmap>", self._on_minimize)
        
        # Centralizar na tela
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"+{x}+{y}")
        
        # Forçar visibilidade - múltiplas tentativas
        self.deiconify()
        self.lift()
        self.focus_force()
        
        # BUG 10 FIX: Remover topmost após breve delay (não bloquear outras janelas do sistema)
        self.after(600, self._remover_topmost)
        self.after(100, self.lift)
        self.after(200, self.lift)

    def _remover_topmost(self):
        """Remove o atributo topmost após a janela estar visível."""
        try:
            if self.winfo_exists():
                self.attributes("-topmost", False)
        except Exception:
            pass

    def _on_close(self):
        """Fecha o diálogo e encerra o programa completamente (X)."""
        self._cleanup_bindings()
        print("\n[!] Programa encerrado pelo usuário (X).")
        os._exit(0)

    def _on_minimize(self, event):
        """Encerra o programa se a janela for minimizada."""
        try:
            if self.winfo_exists() and self.state() == 'iconic':
                self._cleanup_bindings()
                print("\n[!] Programa encerrado pelo usuário (Minimizar).")
                os._exit(0)
        except Exception:
            pass

    def _cleanup_bindings(self):
        """BUG 2 + 12 FIX: Remove todos os bindings de MouseWheel registrados por este diálogo."""
        for widget, seq, func_id in self._mousewheel_bindings:
            try:
                if widget.winfo_exists():
                    widget.unbind(seq, func_id)
            except Exception:
                pass
        self._mousewheel_bindings.clear()

    def _bind_mousewheel(self, canvas):
        """BUG 2 FIX: Registra binding de scroll de forma rastreada e local ao canvas.
        Usa bind no canvas e no diálogo (não bind_all global)."""
        def _on_scroll(event):
            try:
                if canvas.winfo_exists():
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass
        
        # Bind local no canvas e na janela (cobre mouse sobre qualquer área do dialogo)
        fid1 = canvas.bind("<MouseWheel>", _on_scroll, add="+")
        fid2 = self.bind("<MouseWheel>", _on_scroll, add="+")
        self._mousewheel_bindings.append((canvas, "<MouseWheel>", fid1))
        self._mousewheel_bindings.append((self, "<MouseWheel>", fid2))

    def destroy(self):
        """Override: garante cleanup de bindings antes de destruir."""
        self._cleanup_bindings()
        super().destroy()

class SolicitarNumeroDialog(BaseDialog):
    def __init__(self, parent):
        super().__init__(parent, title="Nova Automação", width=500, height=350)
        self.resultado = None
        self.abrir_configs = False
        self._criar_interface()
        
    def _criar_interface(self):
        self.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(self, text="Início das Atividades", font=FONTS['title'], text_color=COLORS['primary']).grid(row=0, column=0, pady=(20, 10))
        ctk.CTkLabel(self, text="Digite o número do processo (CNJ):", font=FONTS['normal']).grid(row=1, column=0)
        ctk.CTkLabel(self, text="Formato: 0000000-00.0000.0.00.0000", font=FONTS['small'], text_color="gray").grid(row=2, column=0, pady=(0, 20))
        
        self.entry = ctk.CTkEntry(self, width=400, height=40, font=FONTS['normal'], placeholder_text="0000000-00.0000.0.00.0000")
        self.entry.grid(row=3, column=0, pady=10)
        self.entry.focus_set()
        
        frame_btns = ctk.CTkFrame(self, fg_color="transparent")
        frame_btns.grid(row=4, column=0, pady=20)
        
        ctk.CTkButton(frame_btns, text="Confirmar", command=self._confirmar, fg_color=COLORS['success'], hover_color="#246d3d", width=120).pack(side='left', padx=10)
        ctk.CTkButton(frame_btns, text="Configurações ⚙️", command=self._config, fg_color=COLORS['primary'], width=140).pack(side='left', padx=10)
        ctk.CTkButton(frame_btns, text="Cancelar", command=self.destroy, fg_color=COLORS['error'], hover_color="#b5433f", width=120).pack(side='right', padx=10)
        
        self.bind('<Return>', lambda e: self._confirmar())
        self.bind('<Escape>', lambda e: self.destroy())

    def _config(self):
        self.abrir_configs = True
        self.destroy()

    def _confirmar(self):
        numero = self.entry.get().strip()
        padrao = r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}"
        if re.fullmatch(padrao, numero):
            self.resultado = numero
            self.destroy()
        else:
            messagebox.showerror("Número Inválido", "Por favor, digite um número no formato CNJ:\n0000000-00.0000.0.00.0000")

class DialogoResultadoDownload(BaseDialog):
    def __init__(self, parent, resultados: Dict[str, ResultadoDownload], url_pasta_digital: str = "", on_abrir_pasta_automacao=None):
        super().__init__(parent, title="Resultado dos Downloads", width=750, height=550)
        self.resultados = resultados
        self.url_pasta_digital = url_pasta_digital
        self.on_abrir_pasta_automacao = on_abrir_pasta_automacao
        self.requer_intervencao = self._verificar_necessidade_humana()
        self._criar_interface()

    def _verificar_necessidade_humana(self) -> bool:
        ignorados = ['peticao', 'documentopessoal', 'sentenca']
        return any(
            resultado.status != StatusDownload.SUCESSO 
            for chave, resultado in self.resultados.items()
            if chave not in ignorados
        )

    def _criar_interface(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Título
        titulo = "⚠️ Intervenção Necessária" if self.requer_intervencao else "✅ Downloads Concluídos"
        cor = COLORS['error'] if self.requer_intervencao else COLORS['success']
        ctk.CTkLabel(self, text=titulo, font=FONTS['subtitle'], text_color=cor).grid(row=0, column=0, pady=15)

        msg = "Os seguintes documentos foram processados:"
        ctk.CTkLabel(self, text=msg, font=FONTS['normal']).grid(row=1, column=0, pady=(0, 10))

        # Canvas nativo em vez de CTkScrollableFrame (evita bug de renderização no Windows)
        container = ctk.CTkFrame(self, fg_color="#2b2b2b", corner_radius=0)
        container.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)

        canvas = tk.Canvas(container, bg="#2b2b2b", highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.grid(row=0, column=0, sticky="nsew")

        inner = ctk.CTkFrame(canvas, fg_color="#2b2b2b", corner_radius=0)
        cw = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cw, width=e.width))
        self._bind_mousewheel(canvas)  # BUG 2 FIX: bind local rastreado

        for tipo, res in self.resultados.items():
            frame_item = tk.Frame(inner, bg="#2b2b2b")
            frame_item.pack(fill='x', pady=2, padx=5)

            nome = self._nome_legivel(tipo)
            status_text = "✅ Sucesso" if res.status == StatusDownload.SUCESSO else f"❌ {res.status.value}"
            cor_status = COLORS['success'] if res.status == StatusDownload.SUCESSO else COLORS['error']

            ctk.CTkLabel(frame_item, text=nome, width=200, anchor="w", font=FONTS['normal']).pack(side='left', padx=8)
            ctk.CTkLabel(frame_item, text=status_text, width=130, text_color=cor_status, font=FONTS['normal']).pack(side='left', padx=5)
            ctk.CTkLabel(frame_item, text=res.mensagem[:55], anchor="w", font=FONTS['small'], text_color="gray").pack(side='left', fill='x', expand=True)

        # Botões de ação
        frame_acoes = ctk.CTkFrame(self, fg_color="transparent")
        frame_acoes.grid(row=3, column=0, pady=20)

        if self.requer_intervencao:
            ctk.CTkButton(frame_acoes, text="Abrir Pasta Digital", command=self._abrir_navegador, fg_color=COLORS['primary']).pack(side='left', padx=10)
            ctk.CTkButton(frame_acoes, text="Confirmar Manual e Continuar", command=self._confirmar_manual, fg_color=COLORS['success']).pack(side='left', padx=10)
        else:
            ctk.CTkButton(frame_acoes, text="Continuar", command=self.destroy, fg_color=COLORS['success'], width=200).pack(pady=10)

    def _nome_legivel(self, tipo: str) -> str:
        nomes = {
            'instrumentoprocuracao': 'Procuração',
            'decisao': 'Decisão',
            'planilhacalculo': 'Planilha de Cálculo',
            'peticao': 'Petição Intermediária',
            'documentopessoal': 'Documento Pessoal',
            'sentenca': 'Sentença'
        }
        return nomes.get(tipo, tipo.capitalize())

    def _abrir_navegador(self):
        if self.on_abrir_pasta_automacao:
            # Invoca o callback de automação assistida
            self.on_abrir_pasta_automacao()
        elif self.url_pasta_digital:
            webbrowser.open(self.url_pasta_digital)
        else:
            messagebox.showinfo("Informação", "Navegador aberto em segundo plano.\nUse-o para baixar os documentos faltantes.")

    def _confirmar_manual(self):
        if messagebox.askyesno("Confirmar", "Confirmar download manual de todos os pendentes?"):
            self.destroy()

class DialogoAnalisePlaceholders(BaseDialog):
    def __init__(self, parent, dados_extraidos: Dict):
        super().__init__(parent, title="Análise de Dados", width=750, height=650)
        self.dados = dados_extraidos.copy()
        self.novos_dados = {}
        self.entries = {}
        self._criar_interface()

    def _criar_interface(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(self, text="Análise de Dados Identificados", font=FONTS['title'],
                     text_color=COLORS['primary']).grid(row=0, column=0, pady=15)

        msg = "Verifique os dados encontrados (✅) e preencha os faltantes (❌)."
        ctk.CTkLabel(self, text=msg, font=FONTS['normal']).grid(row=1, column=0, pady=(0, 10))

        # Canvas nativo - sem CTkScrollableFrame para garantir renderização no Windows
        container = ctk.CTkFrame(self, fg_color="#2b2b2b", corner_radius=0)
        container.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)

        canvas = tk.Canvas(container, bg="#2b2b2b", highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.grid(row=0, column=0, sticky="nsew")

        scroll_frame = ctk.CTkFrame(canvas, fg_color="#2b2b2b", corner_radius=0)
        cw = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cw, width=e.width))
        self._bind_mousewheel(canvas)  # BUG 2 FIX: bind local rastreado

        campos = {
            'numero_processo': 'Autos Principais',
            'cumprimento_sentenca': 'Cumprimento de Sentença',
            'cidade': 'Cidade/Comarca',
            'vara': 'Vara',
            'entidade_devedora': 'Entidade Devedora (Fazenda, etc)',
            'autor': 'Autor Principal',
            'valor': 'Valor Bruto',
            'paginas_decisao': 'Fls. Decisão',
            'paginas_procuracao': 'Fls. Procuração',
            'paginas_planilha': 'Fls. Planilha de Cálculo',
            'data_transito_julgado': 'Trânsito em Julgado',
            'data_protocolo': 'Data Ajuizamento',
            'data_base': 'Data Base (Cálculo)',
            'data_embargos': 'Data Embargos/Impugnação',
            'data_nascimento': 'Data de Nascimento (DD/MM/AAAA)',
            'termo_final_juros': 'Termo Final dos Juros',
            'banco': 'Banco',
            'agencia': 'Agência Bancária',
            'conta_corrente': 'Conta Corrente + Dígito',
            'tipo_requisitorio': 'Tipo (RPV ou PRECATÓRIO)'
        }

        for chave, label in campos.items():
            valor = self.dados.get(chave, "")
            
            # Aplica o padrão caso não tenha sido extraído
            if chave == 'entidade_devedora' and not str(valor).strip():
                valor = "FAZENDA DO ESTADO DE SÃO PAULO"
                
            frame = tk.Frame(scroll_frame, bg="#2b2b2b")
            frame.pack(fill='x', pady=5, padx=5)

            ctk.CTkLabel(frame, text=f"{label}:", width=200, anchor="w",
                         font=FONTS['normal']).pack(side='left', padx=8)

            check = "✅" if str(valor).strip() else "❌"
            cor_check = COLORS['success'] if str(valor).strip() else COLORS['error']
            ctk.CTkLabel(frame, text=check, text_color=cor_check,
                         font=("Arial", 14)).pack(side='left', padx=4)

            if chave == 'tipo_requisitorio':
                entry = ctk.CTkComboBox(frame, values=["RPV", "PRECATÓRIO"], width=330, height=34)
                entry.set(valor if valor in ["RPV", "PRECATÓRIO"] else "RPV")
            else:
                entry = ctk.CTkEntry(frame, width=330, height=34)
                entry.insert(0, str(valor) if valor else "")
            entry.pack(side='left', padx=8)
            self.entries[chave] = entry

        ctk.CTkButton(self, text="✔ Confirmar e Gerar Documentos",
                      command=self._confirmar, fg_color=COLORS['success'],
                      height=45, font=FONTS['normal']).grid(row=3, column=0, pady=20)

    def _confirmar(self):
        for chave, entry in self.entries.items():
            self.novos_dados[chave] = entry.get().strip()
        for k, v in self.dados.items():
            if k not in self.novos_dados:
                self.novos_dados[k] = v
        self.destroy()

class DialogoAtivacao(BaseDialog):
    def __init__(self, parent, machine_id):
        super().__init__(parent, title="Ativação de Licença", width=500, height=350)
        self.machine_id = machine_id
        self.chave = None
        self._criar_interface()

    def _criar_interface(self):
        self.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(self, text="Software Licenciado", font=FONTS['title'], text_color=COLORS['primary']).grid(row=0, column=0, pady=20)
        ctk.CTkLabel(self, text="ID desta Máquina:", font=FONTS['small']).grid(row=1, column=0)
        
        # Entry apenas leitura para o ID
        id_entry = ctk.CTkEntry(self, width=400, height=30, font=("Consolas", 10))
        id_entry.insert(0, self.machine_id)
        id_entry.configure(state="readonly")
        id_entry.grid(row=2, column=0, pady=10)

        ctk.CTkLabel(self, text="Por favor, insira sua chave de ativação:", font=FONTS['normal']).grid(row=3, column=0, pady=(10, 0))
        
        self.key_entry = ctk.CTkEntry(self, width=400, height=40, placeholder_text="Cole sua chave aqui...")
        self.key_entry.grid(row=4, column=0, pady=15)

        ctk.CTkButton(self, text="Ativar Sistema", command=self._ativar, fg_color=COLORS['success'], width=200, height=40).grid(row=5, column=0, pady=10)

    def _ativar(self):
        self.chave = self.key_entry.get().strip()
        if self.chave:
            self.destroy()
        else:
            messagebox.showwarning("Aviso", "A chave não pode estar vazia.")

class DialogoHallAutores(BaseDialog):
    def __init__(self, parent, lista_autores: List[str]):
        super().__init__(parent, title="Hall de Autores - Seleção de Requerentes", width=520, height=500)

        self.resizable(True, True)
        self.lista_autores = lista_autores
        self.selecionados = []
        self.checkboxes = {}
        self._criar_interface()

    def _criar_interface(self):
        import logging
        logging.info("🏗️ Iniciando construção da interface do Hall de Autores (estabilizada)...")
        try:
            self.grid_columnconfigure(0, weight=1)
            self.grid_rowconfigure(2, weight=1)

            # Título
            ctk.CTkLabel(
                self, text="Seleção de Requerentes",
                font=FONTS['title'], text_color=COLORS['primary']
            ).grid(row=0, column=0, pady=(15, 5), padx=20, sticky="ew")

            ctk.CTkLabel(
                self, text="Selecione os autores para gerar petição:",
                font=FONTS['normal']
            ).grid(row=1, column=0, pady=(0, 8), padx=20, sticky="ew")

            # --- CONTAINER NATIVO (STABLE) ---
            # Usar tk.Frame nativo como container para o Canvas é muito mais estável 
            # no Windows do que usar ctk.CTkFrame aninhado com Canvas.
            container = tk.Frame(self, bg="#2b2b2b")
            container.grid(row=2, column=0, padx=20, pady=5, sticky="nsew")
            container.grid_columnconfigure(0, weight=1)
            container.grid_rowconfigure(0, weight=1)

            canvas = tk.Canvas(container, bg="#2b2b2b", highlightthickness=0)
            scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=scrollbar.set)

            scrollbar.grid(row=0, column=1, sticky="ns")
            canvas.grid(row=0, column=0, sticky="nsew")

            # Frame interno onde os widgets serão colocados (tk.Frame é mais confiável dentro do Canvas)
            inner_frame = tk.Frame(canvas, bg="#2b2b2b")
            canvas_window = canvas.create_window((0, 0), window=inner_frame, anchor="nw")

            def on_frame_configure(event):
                canvas.configure(scrollregion=canvas.bbox("all"))
            def on_canvas_configure(event):
                canvas.itemconfig(canvas_window, width=event.width)

            inner_frame.bind("<Configure>", on_frame_configure)
            canvas.bind("<Configure>", on_canvas_configure)
            self._bind_mousewheel(canvas)

            # Selecionar Todos
            self.chk_todos_var = tk.BooleanVar(value=True)
            chk_todos = ctk.CTkCheckBox(
                inner_frame, text="Selecionar Todos",
                variable=self.chk_todos_var,
                font=FONTS['subtitle'], text_color=COLORS['success'],
                command=self._toggle_todos, fg_color=COLORS['success']
            )
            chk_todos.pack(anchor="w", pady=(8, 12), padx=12)

            # Separador visual nativo
            tk.Frame(inner_frame, bg="#555555", height=1).pack(fill="x", padx=10, pady=2)

            if not self.lista_autores:
                tk.Label(inner_frame, text="Nenhum autor identificado.",
                         fg=COLORS['error'], bg="#2b2b2b", font=("Segoe UI", 11)).pack(pady=20)
            else:
                # Sanitização para evitar erros de renderização
                for autor in self.lista_autores:
                    var = tk.BooleanVar(value=True)
                    texto = str(autor)[:100] # Limite de caracteres
                    chk = ctk.CTkCheckBox(
                        inner_frame, text=texto, variable=var,
                        font=FONTS['normal'], fg_color=COLORS['primary']
                    )
                    chk.pack(anchor="w", pady=4, padx=24)
                    self.checkboxes[autor] = var

            # Botões de ação fora do scroll
            frame_btns = ctk.CTkFrame(self, fg_color="transparent")
            frame_btns.grid(row=3, column=0, pady=15, padx=20)

            ctk.CTkButton(
                frame_btns, text="✔ Confirmar Lote", command=self._confirmar,
                fg_color=COLORS['success'], hover_color=COLORS['primary'],
                height=42, width=170, font=FONTS['normal']
            ).pack(side='left', padx=10)

            ctk.CTkButton(
                frame_btns, text="✖ Cancelar", command=self.destroy,
                fg_color=COLORS['error'], height=42, width=140, font=FONTS['normal']
            ).pack(side='right', padx=10)

            logging.info("✅ Interface do Hall de Autores montada com sucesso.")
            print(">>> DEBUG: Hall de Autores MONTADO. Forçando exibição...")
            
            # Forçar mapeamento na tela
            self.update_idletasks()
            self.deiconify()
            self.lift()
            self.focus_force()
            
            # Garantia extra após 100ms
            self.after(100, lambda: self.state("normal"))
            self.after(200, self.lift)
            self.after(300, self.focus_force)

        except Exception as e:
            import traceback
            err_msg = f"❌ Erro FATAL ao criar interface do Hall de Autores: {e}\n{traceback.format_exc()}"
            logging.error(err_msg)
            print(err_msg) # Cópia redundante para o terminal
            self.destroy()

    def _toggle_todos(self):
        estado = self.chk_todos_var.get()
        for var in self.checkboxes.values():
            var.set(estado)

    def _confirmar(self):
        self.selecionados = [autor for autor, var in self.checkboxes.items() if var.get()]
        if not self.selecionados:
            messagebox.showwarning("Aviso", "Selecione pelo menos um autor para o lote, ou clique em Cancelar.")
            return
        self.destroy()

class DialogoTipoDocumento(BaseDialog):
    def __init__(self, parent, templates_disponiveis: List[str]):
        super().__init__(parent, title="Geração de Petição", width=500, height=350)
        self.templates = templates_disponiveis
        self.resultado = None
        self._criar_interface()

    def _criar_interface(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Selecione o Documento", font=FONTS['title'], text_color=COLORS['primary']).grid(row=0, column=0, pady=20)
        ctk.CTkLabel(self, text="Qual modelo de petição deseja confeccionar agora?", font=FONTS['normal']).grid(row=1, column=0, pady=(0, 10))

        if not self.templates:
            self.templates = ["Modelo Genérico"]

        self.combo_tipo = ctk.CTkComboBox(self, values=self.templates, width=350, height=40, font=FONTS['normal'])
        self.combo_tipo.grid(row=2, column=0, pady=20)
        self.combo_tipo.set(self.templates[0])

        frame_btns = ctk.CTkFrame(self, fg_color="transparent")
        frame_btns.grid(row=3, column=0, pady=20)

        ctk.CTkButton(frame_btns, text="Gerar", command=self._confirmar, 
                      fg_color=COLORS['success'], height=40, width=120).pack(side='left', padx=10)
        ctk.CTkButton(frame_btns, text="Pular (Apenas Peticionar)", command=self.destroy, 
                      fg_color=COLORS['warning'], text_color="#111", height=40, width=180).pack(side='right', padx=10)

    def _confirmar(self):
        self.resultado = self.combo_tipo.get().strip()
        self.destroy()


class SolicitarValorPlanilhaDialog(BaseDialog):
    def __init__(self, parent):
        super().__init__(parent, title="Valor da Planilha", width=450, height=220)
        self.valor = None
        self._criar_interface()

    def _criar_interface(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Valor Não Identificado", font=FONTS['subtitle'], text_color=COLORS['warning']).pack(pady=(20, 10))
        ctk.CTkLabel(self, text="Não foi possível extrair o valor da planilha automaticamente.\nDigite o valor total:", font=FONTS['normal']).pack(pady=(0, 15))

        self.entry = ctk.CTkEntry(self, width=300, height=40, font=FONTS['normal'], placeholder_text="Ex: 15000,50")
        self.entry.pack(pady=10)
        self.entry.focus_set()

        frame_btns = ctk.CTkFrame(self, fg_color="transparent")
        frame_btns.pack(pady=15)

        ctk.CTkButton(frame_btns, text="Confirmar", command=self._confirmar, fg_color=COLORS['success'], width=120).pack(side='left', padx=10)
        ctk.CTkButton(frame_btns, text="Cancelar (R$ 0)", command=self._cancelar, fg_color=COLORS['error'], width=150).pack(side='right', padx=10)

        self.bind('<Return>', lambda e: self._confirmar())
        self.bind('<Escape>', lambda e: self._cancelar())

    def _confirmar(self):
        valor_texto = self.entry.get().strip().replace('R$', '').replace('.', '').replace(',', '.')
        try:
            self.valor = float(valor_texto) if valor_texto else 0.0
        except ValueError:
            self.valor = 0.0
        self.destroy()

    def _cancelar(self):
        self.valor = 0.0
        self.destroy()
class ConfirmDialog(BaseDialog):
    def __init__(self, parent, titulo, mensagem):
        super().__init__(parent, title=titulo, width=450, height=200)
        self.resultado = False
        self.mensagem = mensagem
        self._criar_interface()

    def _criar_interface(self):
        self.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(self, text=self.mensagem, font=FONTS['normal'], wraplength=400).grid(row=0, column=0, pady=30, padx=20)
        
        frame_btns = ctk.CTkFrame(self, fg_color="transparent")
        frame_btns.grid(row=1, column=0, pady=10)
        
        ctk.CTkButton(frame_btns, text="Sim", command=self._sim, fg_color=COLORS['success'], width=120, height=35).pack(side='left', padx=10)
        ctk.CTkButton(frame_btns, text="Não", command=self._nao, fg_color=COLORS['error'], width=120, height=35).pack(side='right', padx=10)
        
        self.bind('<Return>', lambda e: self._sim())
        self.bind('<Escape>', lambda e: self._nao())

    def _sim(self):
        self.resultado = True
        self.destroy()

    def _nao(self):
        self.resultado = False
        self.destroy()

class DialogoTermosUso(BaseDialog):
    def __init__(self, parent):
        super().__init__(parent, title="Termos de Uso e Licenciamento", width=650, height=600)
        self.aceitou = False
        self._criar_interface()

    def _criar_interface(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Termos de Uso e Licenciamento", font=FONTS['title'], text_color=COLORS['primary']).grid(row=0, column=0, pady=15)

        # Container para o texto dos termos
        container = ctk.CTkFrame(self, fg_color="#2b2b2b", corner_radius=0)
        container.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)

        text_widget = tk.Text(container, bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 10), wrap="word", padx=15, pady=15, borderwidth=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.grid(row=0, column=1, sticky="ns")
        text_widget.grid(row=0, column=0, sticky="nsew")

        termos_texto = """
CLÁUSULA DE LICENCIAMENTO E PROTEÇÃO DE PROPRIEDADE INTELECTUAL

1. DA LICENÇA: O SOFTWARE é licenciado por estação de trabalho (máquina). O compartilhamento da chave de ativação com terceiros ou o uso em máquinas não contratadas resultará no bloqueio imediato da licença sem direito a reembolso.

2. DA PROPRIEDADE: Todos os direitos de propriedade intelectual sobre o software, incluindo código-fonte, algoritmos e lógica de automação, pertencem exclusivamente ao DESENVOLVEDOR.

3. DAS PROIBIÇÕES: É expressamente proibido ao USUÁRIO: (a) realizar engenharia reversa, descompilação ou qualquer tentativa de obter o código-fonte; (b) remover travas de segurança ou sistemas de controle de licença; (c) sublicenciar ou comercializar o acesso ao software.

4. DA MANUTENÇÃO: A continuidade do funcionamento do software está vinculada à manutenção do pagamento mensal, visto que depende de atualizações constantes para compatibilidade com os portais judiciais (E-SAJ, PJe, etc).

5. DA RESPONSABILIDADE: O desenvolvedor não se responsabiliza por erros decorrentes de instabilidades nos portais dos tribunais ou preenchimento incorreto de dados pelo usuário.

6. DO PAGAMENTO: O uso do software está condicionado ao pagamento da mensalidade acordada. O atraso superior a 5 dias poderá resultar na suspensão automática da licença.

Ao clicar em 'Aceitar e Continuar', você declara estar de acordo com todos os termos acima descritos.
        """
        text_widget.insert("1.0", termos_texto.strip())
        text_widget.configure(state="disabled")

        # Checkbox de aceite
        self.check_var = tk.BooleanVar(value=False)
        self.check_aceite = ctk.CTkCheckBox(self, text="Li e concordo com os termos de uso e licenciamento.", 
                                           variable=self.check_var, font=FONTS['normal'],
                                           fg_color=COLORS['success'], command=self._toggle_button)
        self.check_aceite.grid(row=2, column=0, pady=15, padx=20, sticky="w")

        # Botão de ação
        self.btn_confirmar = ctk.CTkButton(self, text="Aceitar e Continuar", command=self._confirmar, 
                                          fg_color=COLORS['success'], state="disabled", height=45, font=FONTS['normal'])
        self.btn_confirmar.grid(row=3, column=0, pady=(0, 20))

    def _toggle_button(self):
        if self.check_var.get():
            self.btn_confirmar.configure(state="normal")
        else:
            self.btn_confirmar.configure(state="disabled")

    def _confirmar(self):
        self.aceitou = True
        self.destroy()

class DialogoConfiguracoes(BaseDialog):
    def __init__(self, parent):
        super().__init__(parent, title="Configurações do Usuário", width=550, height=580)
        self.salvou = False
        self._carregar_dados_atuais()
        self._criar_interface()

    def _carregar_dados_atuais(self):
        import config
        # Tenta carregar do config mas prioriza o que está no estado atual
        self.dados = {
            'LOGIN_TJSP': getattr(config, 'LOGIN_TJSP', "") or "",
            'SENHA_TJSP': getattr(config, 'SENHA_TJSP', "") or "",
            'EMAIL_USER': getattr(config, 'EMAIL_USER', "") or "",
            'EMAIL_PASS': getattr(config, 'EMAIL_PASS', "") or ""
        }

    def _criar_interface(self):
        self.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(self, text="⚙️ Configurações de Acesso", font=FONTS['subtitle'], text_color=COLORS['primary']).pack(pady=20)
        
        # --- Seção TJSP ---
        frame_tjsp = ctk.CTkFrame(self)
        frame_tjsp.pack(fill='x', padx=20, pady=10)
        ctk.CTkLabel(frame_tjsp, text="Portal e-SAJ (TJSP)", font=FONTS['normal'], text_color="gray").pack(pady=5)
        
        self.entry_login = ctk.CTkEntry(frame_tjsp, width=400, placeholder_text="CPF (apenas números)")
        self.entry_login.insert(0, self.dados['LOGIN_TJSP'])
        self.entry_login.pack(pady=5)
        
        self.entry_senha = ctk.CTkEntry(frame_tjsp, width=400, placeholder_text="Senha do TJSP", show="*")
        self.entry_senha.insert(0, self.dados['SENHA_TJSP'])
        self.entry_senha.pack(pady=5)

        # --- Seção E-mail ---
        frame_email = ctk.CTkFrame(self)
        frame_email.pack(fill='x', padx=20, pady=10)
        ctk.CTkLabel(frame_email, text="E-mail para Código 2FA", font=FONTS['normal'], text_color="gray").pack(pady=5)
        
        self.entry_email = ctk.CTkEntry(frame_email, width=400, placeholder_text="seu-email@provedor.com")
        self.entry_email.insert(0, self.dados['EMAIL_USER'])
        self.entry_email.pack(pady=5)
        
        self.entry_email_pass = ctk.CTkEntry(frame_email, width=400, placeholder_text="Senha do E-mail", show="*")
        self.entry_email_pass.insert(0, self.dados['EMAIL_PASS'])
        self.entry_email_pass.pack(pady=5)

        ctk.CTkLabel(self, text="Nota: Estes dados ficam salvos apenas localmente na sua máquina.", 
                     font=FONTS['small'], text_color="gray").pack(pady=10)

        # Botões
        frame_btns = ctk.CTkFrame(self, fg_color="transparent")
        frame_btns.pack(pady=20)
        
        ctk.CTkButton(frame_btns, text="Salvar Alterações", command=self._salvar, 
                      fg_color=COLORS['success'], width=200, height=40).pack(side='left', padx=10)
        ctk.CTkButton(frame_btns, text="Cancelar", command=self.destroy, 
                      fg_color=COLORS['error'], width=120, height=40).pack(side='right', padx=10)

    def _salvar(self):
        login = self.entry_login.get().strip()
        senha = self.entry_senha.get().strip()
        email = self.entry_email.get().strip()
        email_pass = self.entry_email_pass.get().strip()

        if not all([login, senha, email, email_pass]):
            messagebox.showwarning("Aviso", "Todos os campos são obrigatórios para o funcionamento do robô.")
            return

        try:
            # Salvar no arquivo .env localmente
            # Preservar o que é sensível ao desenvolvedor (Supabase) se disponível
            import config
            with open(".env", "w", encoding="utf-8") as f:
                f.write(f"LOGIN_TJSP={login}\n")
                f.write(f"SENHA_TJSP={senha}\n")
                f.write(f"EMAIL_USER={email}\n")
                f.write(f"EMAIL_PASS={email_pass}\n")
                
                # Chaves de licenciamento (SaaS) fixas
                if getattr(config, 'LICENSE_SECRET_KEY', None): f.write(f"LICENSE_SECRET_KEY={config.LICENSE_SECRET_KEY}\n")
                if getattr(config, 'SUPABASE_URL', None): f.write(f"SUPABASE_URL={config.SUPABASE_URL}\n")
                if getattr(config, 'SUPABASE_KEY', None): f.write(f"SUPABASE_KEY={config.SUPABASE_KEY}\n")

            messagebox.showinfo("Sucesso", "Configurações salvas! O programa será reiniciado para aplicar as mudanças.")
            self.salvou = True
            self.destroy()
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível salvar as configurações: {e}")

