import logging
from supabase import create_client, Client
import config
from datetime import datetime
from typing import Optional, Dict, Any

class SupabaseManager:
    def __init__(self):
        self.url = config.SUPABASE_URL
        self.key = config.SUPABASE_KEY
        self.client: Optional[Client] = None
        
        if self.url and self.key:
            try:
                self.client = create_client(self.url, self.key)
                logging.info("Supabase Client inicializado com sucesso.")
            except Exception as e:
                logging.error(f"Erro ao inicializar Supabase Client: {e}")
        else:
            logging.warning("Configurações do Supabase ausentes em config.py ou .env")

    def verificar_licenca_online(self, chave: str) -> Optional[Dict[str, Any]]:
        """
        Consulta a licença no banco de dados do Supabase pela chave.
        """
        if not self.client:
            return None
            
        try:
            response = self.client.table('licencas').select('*').eq('chave', chave).execute()
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            logging.error(f"Erro ao verificar licença online: {e}")
            return None

    def ativar_licenca_online(self, chave: str, machine_id: str, aceitou_termos: bool = True) -> bool:
        """
        Vincula o machine_id à chave e marca como ativa no banco.
        """
        if not self.client:
            return False
            
        try:
            data = {
                'machine_id': machine_id,
                'terms_accepted': aceitou_termos,
                'activated_at': datetime.now().isoformat(),
                'status': 'ativo',
                'updated_at': datetime.now().isoformat()
            }
            response = self.client.table('licencas').update(data).eq('chave', chave).execute()
            return len(response.data) > 0
        except Exception as e:
            logging.error(f"Erro ao ativar licença no Supabase: {e}")
            return False

    def registrar_log(self, chave: str, machine_id: str, acao: str, versao: str = config.VERSION):
        """
        Registra um log de uso/acesso.
        """
        if not self.client:
            return
            
        try:
            data = {
                'chave_referencia': chave,
                'machine_id': machine_id,
                'versao_app': versao,
                'acao': acao
            }
            self.client.table('logs_acesso').insert(data).execute()
        except Exception as e:
            logging.error(f"Erro ao registrar log no Supabase: {e}")
