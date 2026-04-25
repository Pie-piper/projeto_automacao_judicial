import re
from typing import Optional

class ProcessoContext:
    def __init__(self, numero_inicial: str):
        self.numero_original = numero_inicial.strip()
        self.numero_norm = self.normalizar_numero_processo(self.numero_original)
        self.tipo = self._identificar_tipo(self.numero_norm)
        
        self.numero_autos_principais: Optional[str] = None
        self.numero_cumprimento: Optional[str] = None
        self.data_transito_julgado: Optional[str] = None
        self.data_ajuizamento: Optional[str] = None
        
        if self.tipo == "CUMPRIMENTO":
            self.numero_cumprimento = self.numero_norm
        else:
            self.numero_autos_principais = self.numero_norm

    def _identificar_tipo(self, numero: str) -> str:
        # Padrão TJSP: Cumprimento costuma ter muitos zeros no início
        if numero.startswith("000"):
            return "CUMPRIMENTO"
        return "AUTOS_PRINCIPAIS"

    @staticmethod
    def normalizar_numero_processo(numero: str) -> str:
        if not numero:
            return ""
        return re.sub(r'[^\d]', '', numero)

    def atualizar_vinculo(self, numero: str, tipo_vinculo: str):
        num_norm = self.normalizar_numero_processo(numero)
        if tipo_vinculo == "CUMPRIMENTO":
            self.numero_cumprimento = num_norm
        else:
            self.numero_autos_principais = num_norm
