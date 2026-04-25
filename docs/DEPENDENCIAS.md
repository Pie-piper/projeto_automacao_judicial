# Dependências Externas - RPV Automação

Este documento lista as dependências externas necessárias para o funcionamento do sistema.

---

## 1. Tesseract OCR (v5.3.3+)

**Obrigatório** para extração de texto de PDFs via OCR.

### Versão Recomendada
- **Tesseract OCR 5.3.3** (64-bit Windows)
- **Idioma**: Português (`por.traineddata`) incluso por padrão

### Download
```
https://github.com/tesseract-ocr/tesseract/releases/download/5.3.3/tesseract-ocr-w64-setup-5.3.3.20230621.exe
```

### Instalação Manual
1. Baixe o instalador `.exe` acima
2. Execute como Administrador
3. Mantenha o caminho padrão: `C:\Program Files\Tesseract-OCR\`
4. O idioma português já vem incluso

### Verificação da Instalação
```cmd
"C:\Program Files\Tesseract-OCR\tesseract.exe" --version
```

Saída esperada:
```
tesseract v5.3.3
leptonica-1.84.0
...
```

### Idiomas Adicionais (Opcional)
O idioma português já vem incluso. Para adicionar outros:
1. Baixe de: https://github.com/tesseract-ocr/tessdata
2. Copie o arquivo `.traineddata` para `C:\Program Files\Tesseract-OCR\tessdata\`

---

## 2. Poppler (para pdf2image)

**Obrigatório** para conversão de PDF em imagens (usado no OCR).

### Versão Recomendada
- **poppler-23.11.0** ou superior

### Download
```
https://github.com/oschwartz10612/poppler-windows/releases/download/v23.11.0-0/Release-23.11.0-0.zip
```

### Instalação
1. Extraia o ZIP
2. Mova a pasta `Library\bin` para:
   - `C:\Program Files\poppler-23.11.0\Library\bin`
3. Adicione ao PATH do sistema (opcional):
   ```
   C:\Program Files\poppler-23.11.0\Library\bin
   ```

### Verificação
```cmd
"C:\Program Files\poppler-23.11.0\Library\bin\pdftoppm.exe" -v
```

---

## 3. Microsoft Word

**Obrigatório** para geração de documentos DOCX/PDF via automação COM.

### Versão Mínima
- Microsoft Word 2016 ou superior

### Verificação
```cmd
winword.exe /?
```

---

## 4. Microsoft Visual C++ Redistributable

**Obrigatório** para bibliotecas nativas do Python.

### Download
```
https://aka.ms/vs/17/release/vc_redist.x64.exe
```

---

## Instalador Automático

O instalador Inno Setup (`setup_script.iss`) pode baixar e instalar automaticamente:

1. **Tesseract OCR 5.3.3** - Idioma português incluso
2. **Poppler** - Versão embarcada opcional

Execute o instalador e marque a opção "Instalar Tesseract OCR".

---

## Validação Automática

Ao iniciar, o sistema verifica automaticamente:

1. Existência do Tesseract
2. Versão instalada (recomenda 5.x)
3. Idioma português disponível

Verifique os logs se houver problemas de OCR.
