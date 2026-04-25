import pdfplumber
import re

path = r'c:\Users\User\Downloads\doc_315352196.pdf'
with pdfplumber.open(path) as pdf:
    text = ''
    for page in pdf.pages:
        text += page.extract_text() + '\n'
        
    for line in text.split('\n'):
        # match line with name and multiple numbers
        match = re.search(r'^([A-ZÀ-Úa-zà-ú\s]+?)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)$', line.strip())
        if match:
            print(f"Name: {match.group(1).strip()} | Total: {match.group(5)}")
