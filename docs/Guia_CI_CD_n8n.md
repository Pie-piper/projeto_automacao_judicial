# 🛠️ Guia: Configuração de CI/CD com n8n

Este guia explica como integrar o seu projeto ao n8n para que, ao subir uma nova `Tag` no GitHub, o seu computador Windows gere automaticamente o instalador e faça o upload da Release.

---

## 1. Obtendo o Token de Acesso (GitHub PAT)

O n8n precisa de uma "chave mestra" para criar Releases em seu nome no GitHub.

1. Acesse **GitHub > Settings > Developer Settings**.
2. Vá em **Personal access tokens** > **Tokens (classic)**.
3. Clique em **Generate new token (classic)**.
4. Dê um nome (ex: `n8n_RPV_Automation`).
5. Marque o escopo: **[x] repo** (Full control of private repositories).
6. Clique em **Generate token** no final da página.
7. **COPIE O TOKEN AGORA!** Você não conseguirá vê-lo novamente.

---

## 2. Preparando o Windows Host (SSH)

Como o seu n8n está no Docker (Linux) e o build precisa rodar no Windows, usaremos o **OpenSSH** nativo do Windows para fazer a ponte.

1. Abra o **PowerShell como Administrador** e rode:
   ```powershell
   Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
   Start-Service sshd
   Set-Service -Name sshd -StartupType 'Automatic'
   ```
2. Abra a porta do Firewall:
   ```powershell
   New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -LocalPort 22 -Action Allow
   ```
3. Teste a conexão: Verifique se você consegue acessar seu PC via SSH de outra máquina ou do próprio terminal usando seu usuário de login do Windows.

---

## 3. Importando o Workflow no n8n

1. Baixe o arquivo [workflow_n8n.json](file:///C:/Users/User/.gemini/antigravity/brain/54672e95-a20b-4493-ab22-66609c5fc08e/workflow_n8n.json).
2. No seu painel n8n, clique em **Workflows > Import from File**.
3. **Configurar Credenciais:** 
   - No nó **SSH**, crie uma credencial com seu usuário do Windows e a senha (ou chave privada). 
   - No nó **GitHub**, crie uma credencial colando o **PAT Token** que você gerou no passo 1.
4. **Webhook:** Copie a URL gerada no nó `Webhook` e cole no seu repositório GitHub em **Settings > Webhooks**.

---

## 4. Como o Fluxo Funciona

- O script [build_ci.bat](file:///c:/Users/User/Desktop/arquivo%20executavel/projeto_automacao_judicial/build_ci.bat) foi criado na raiz do seu projeto.
- Ele faz o build limpo (sem pausar no final).
- O n8n dá o comando via SSH, aguarda o Inno Setup terminar de gerar o `.exe`.
- O n8n pega esse arquivo e o anexa na aba **Releases** do seu GitHub automaticamente.

> [!NOTE]
> Quando você migrar para uma VPS, o processo será idêntico, bastando trocar o IP do nó SSH no n8n!

> [!IMPORTANT]
> Certifique-se de que o PyInstaller e o Inno Setup estejam no **PATH** do sistema do Windows para que o SSH consiga executá-los sem precisar do caminho completo o tempo todo.
