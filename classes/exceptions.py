class TribunalException(Exception):
    """Exceção base para todos os erros relacionados ao portal do tribunal."""
    def __init__(self, message: str, can_retry: bool = True):
        super().__init__(message)
        self.can_retry = can_retry

class LoginException(TribunalException):
    """Falha durante o processo de autenticação (senha, certificado ou MFA)."""
    def __init__(self, message: str):
        super().__init__(f"Falha de Login: {message}", can_retry=False)

class PortalIndisponivelException(TribunalException):
    """O portal e-SAJ retornou erro 500, timeout ou está offline."""
    def __init__(self, message: str = "Portal do Tribunal temporariamente indisponível"):
        super().__init__(message, can_retry=True)

class ProcessoNaoEncontradoException(TribunalException):
    """O número do processo não foi localizado no sistema do tribunal."""
    def __init__(self, numero: str):
        super().__init__(f"Processo {numero} não localizado no e-SAJ", can_retry=False)

class PeticionamentoException(TribunalException):
    """Erro crítico durante o preenchimento ou protocolo da petição."""
    def __init__(self, etapa: str, message: str):
        super().__init__(f"Erro no Peticionamento ({etapa}): {message}", can_retry=True)

class DocumentoInvalidoException(TribunalException):
    """Falha na validação de documentos (ex: PDF corrompido ou formato errado)."""
    def __init__(self, doc_name: str, reason: str):
        super().__init__(f"Documento Inválido ({doc_name}): {reason}", can_retry=False)

class BrowserCrashException(TribunalException):
    """
    Falha de infraestrutura: o processo do Chromium crashou (Target crashed,
    Session closed, etc.). Totalmente retentarável pois não é erro de credencial.
    """
    def __init__(self, contexto: str, causa: Exception):
        super().__init__(f"Browser crash em '{contexto}': {causa}", can_retry=True)
        self.causa_original = causa
