import sys
import os

filepath = r"c:\Users\User\Desktop\arquivo executavel\projeto_automacao_judicial\classes\pasta_digital_page.py"
temp_path = filepath + ".tmp"

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Agregando "Fôlego" ao Viewer
old_viewer = 'self.page.wait_for_selector("#viewer", state="visible", timeout=30000)'
new_viewer = 'self.page.wait_for_selector("#viewer", state="visible", timeout=45000)'
content = content.replace(old_viewer, new_viewer)

# 2. Reduzindo Timeout de Extração de Texto para 5s (Evitar prints de 30s)
# Aplicamos apenas em locators que costumam demorar: .textLayer e seletores de assinatura
locators_to_fix = [
    '.locator(".textLayer").inner_text()',
    '.locator("#divAssinaturas #regiaoAssinatura").first.inner_text()',
    '.locator("td").filter(has_text="Protocolado em").first.inner_text()'
]

for loc in locators_to_fix:
    content = content.replace(loc, loc.replace('()', '(timeout=5000)'))

with open(temp_path, 'w', encoding='utf-8') as f:
    f.write(content)

os.replace(temp_path, filepath)
print("File updated with targeted timeouts.")
