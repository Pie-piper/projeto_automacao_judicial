import sys
import os

filepath = r"c:\Users\User\Desktop\arquivo executavel\projeto_automacao_judicial\config.py"
temp_path = filepath + ".tmp"

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Cleanup Logic Adjustment
old_text = '    agora = time.time()\n\n    # Considera tanto o LOGS_DIR atual quanto a pasta SCREENSHOTS_DIR'
new_text = '    agora = time.time()\n    limite_tempo = agora - (dias_limite * 86400)\n\n    # Considera tanto o LOGS_DIR atual quanto a pasta SCREENSHOTS_DIR'

if old_text in content:
    content = content.replace(old_text, new_text)
    print("Replacement success!")
else:
    # Try with \r\n
    old_text_rn = old_text.replace('\n', '\r\n')
    if old_text_rn in content:
        content = content.replace(old_text_rn, new_text.replace('\n', '\r\n'))
        print("Replacement success (CRLF)!")
    else:
        print("Target text not found in content!")
        # Fallback simpler replacement
        if 'if arquivo.stat().st_mtime < limite_tempo:' in content:
             content = content.replace('agora = time.time()', 'agora = time.time()\n    limite_tempo = agora - (dias_limite * 86400)')
             print("Fallback replacement success!")

with open(temp_path, 'w', encoding='utf-8') as f:
    f.write(content)

os.replace(temp_path, filepath)
print("File updated.")
