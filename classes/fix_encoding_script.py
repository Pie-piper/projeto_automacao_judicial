import sys
import os

filepath = r"c:\Users\User\Desktop\arquivo executavel\projeto_automacao_judicial\classes\peticionamento_eletronico.py"
temp_path = filepath + ".tmp"

# Detect encoding
encodings = ['utf-8', 'latin-1', 'utf-16', 'utf-16le', 'cp1252']
content = None
chosen_enc = None

for enc in encodings:
    try:
        with open(filepath, 'r', encoding=enc) as f:
            content = f.read()
            chosen_enc = enc
            print(f"Detected: {enc}")
            break
    except Exception:
        continue

if not content:
    print("Failed to detect encoding")
    sys.exit(1)

# Categorization Delay Adjustment
old_text = '            self.logger.info("Iniciando categorização dinâmica de documentos no grid...")'
new_text = '''            # Opção 2: Aguardar o portal estabilizar após o upload em massa
            self.logger.info("⏳ Aguardando 5 segundos para estabilização do portal (Opção 2)...")
            import time
            time.sleep(5)
            
            self.logger.info("Iniciando categorização dinâmica de documentos no grid...")'''

if old_text in content:
    content = content.replace(old_text, new_text)
    print("Replacement success!")
else:
    print("Target text not found in content!")
    print(f"Content length: {len(content)}")
    # Print a slice around where we expect it
    idx = content.find("categorizar_documentos_upload")
    if idx != -1:
        print(f"Snippet: {content[idx:idx+200]}")

with open(temp_path, 'w', encoding=chosen_enc) as f:
    f.write(content)

os.replace(temp_path, filepath)
print("File updated.")
