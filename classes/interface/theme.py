import customtkinter as ctk

# Configurações Globais
ctk.set_appearance_mode("dark")  # "light" ou "dark"
ctk.set_default_color_theme("blue")  # Tema base

# Paleta Profissional TJSP
COLORS = {
    'primary': '#1f6aa5',      # Azul TJSP
    'primary_hover': '#164e7a',
    'success': '#2d8a4e',
    'warning': '#f0ad4e',
    'error': '#d9534f',
    'bg_dark': '#1a1a2e',
    'bg_light': '#f5f5f5',
    'text_light': '#ffffff',
    'text_dark': '#121212'
}

FONTS = {
    'title': ("Segoe UI", 20, "bold"),
    'subtitle': ("Segoe UI", 16, "bold"),
    'normal': ("Segoe UI", 12),
    'small': ("Segoe UI", 10)
}
