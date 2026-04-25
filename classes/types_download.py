from dataclasses import dataclass
from enum import Enum

class StatusDownload(Enum):
    SUCESSO = "✅"
    NAO_ENCONTRADO = "❌"
    ERRO = "⚠️"

@dataclass
class ResultadoDownload:
    documento: str
    status: StatusDownload
    mensagem: str
    caminho_arquivo: str = None
    metadata: dict = None
