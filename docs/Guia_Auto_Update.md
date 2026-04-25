# 🚀 Guia de Configuração do Updater Automático (GitHub)

Para que o seu programa atualize automaticamente no computador dos clientes, você precisa integrar o `updater.py` já existente ao fluxo de build e subir os arquivos certos como "Releases" no GitHub.

Como o seu projeto lida com o executável secundário, o fluxo exato deve seguir a receita abaixo rigorosamente:

---

## 1. O Problema Atual: Como o seu projeto está embalado
Hoje você usa o **Inno Setup** para fabricar o `Instalador_RPV_Automacao.exe` que empacota dezenas de bibliotecas em uma pasta (`--onedir`). O código do seu atualizador (`classes/update_manager.py`) foi desenhado para **baixar diretamente o executável bruto** da aplicação e jogá-lo por cima do antigo.

> [!WARNING]
> **Regra de ouro:** Nunca envie o arquivo gerado pelo Inno Setup (`Instalador...exe`) para a seção de anexo de "Releases" no Github. O updater vai baixar o instalador automático e colocá-lo no lugar do seu app principal, abrindo a tela de instalação toda vez que o advogado clicar!

**O que o updater espera baixar no Github:** O executável direto da aplicação compilado.

## 2. Preparando os "Engrenagens" da Atualização
Antes de publicar para os usuários finais, garanta que seu ambiente compila e envia o `updater.exe` junto com a aplicação.

### A. Adicione o Updater no arquivo de Build (Compilação)
Atualmente o instalador apenas gera o seu app. Precisamos gerar separadamente um `.exe` pequeno e focado do script `updater.py` para que ele feche e substitua os arquivos corretos.

Altere seu arquivo `build_installer.bat`. Adicione a linha de compilação do spec do updater:
```diff
echo [2/4] Gerando executavel (PyInstaller)...
+ pyinstaller --noconfirm updater.spec
pyinstaller --noconfirm rpv_automation.spec
```

*Se você não tiver o arquivo `updater.spec` bem configurado, me avise que modifico o projeto para incluir a compilação do autoupdater no pipeline principal de uma vez!*

## 3. O Fluxo: Como Lançar Uma Nova Atualização

A magia acontece via Tags de Versão (Releases). Quando for o momento de liberar melhorias:

**Passo 1: Alterar a versão nos códigos**
Vá no arquivo `config.py` e aumente a versão na sua máquina. Ex:
`VERSION = "1.0.2"`

**Passo 2: Gere o build novo**
Execute seu arquivo `build_installer.bat`. O Pyinstaller reconstruirá a pasta `dist\main` e lá dentro estará o arquivo principal `main.exe` mais recente.

**Passo 3: Publique a "Release" no Github**
Abra o repositório (`https://github.com/Pie-piper/projeto_automacao_judicial`). Certifique-se de que o repositório é **PÚBLICO** (pois o código baixa sem um access token especial).

1. Acesse a aba de **Releases > Draft a new release**.
2. Clique em **Choose a tag** e insira: `v1.0.2` (*Use sempre o prefixo 'v' antes do número contido em `config.py`*).
3. Crie o Título desta revisão/versão (ex: "Correção e melhorias na Planilha de RPV").
4. **Vá até a pasta `dist\main\` no seu PC** e encontre o executável gerado (`main.exe`).
5. Arraste **este executável e apenas ele** (renomeie-o para algo como `Atualizacao_RPV_102.exe` antes de anexar para ficar organizado) para a caixa: "Attach binaries by dropping them here".
6. Salve e publique (Publish Release).

## 🎉 Como o sistema Cliente Reagirá

1. O cliente abre o *RPV Automacao*. Ele roda o Check_Updates silencioso para a URL `https://api.github.com/repos/Pie-piper/projeto_automacao_judicial/releases/latest`.
2. A API mapeia que a tag `v1.0.2` é maior que a versão local atual.
3. Ele encontra naquele seu release o executável disponível (`Atualizacao_RPV_102.exe`) ignorando nomes como "updater".
4. Baixa o download silenciosamente para a pasta Temp do disco.
5. Invoca o pequeno `updater.exe` e encerra sua própria operação (`sys.exit`).
6. A pequena janela do updater substitui o arquivo original pelo novo que desceu da net e reabre o app atualizado automaticamente!

> [!NOTE]
> Essa rota funciona impecavelmente para atualizações em que você só altera o código em si (o que engloba 80% das interações futuras). Se futuramente você for usar métodos com pacotes monstruosos instalados via Pip, a atualização puramente do `.exe` não importará o módulo novo que você precisa caso você esteja usando arquitetura de bibliotecas desacopladas (ONEDIR). Para proteger definitivamente contra isso, recomenda-se compilar como `--onefile` (Arquivo Único) no futuro!
