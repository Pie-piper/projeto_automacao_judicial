import imaplib
import email
from email.header import decode_header
import re
import time
import ssl
import logging
import config


class ImapHandler:
    """Classe para gerenciar conexão IMAP e recuperar códigos 2FA"""
    
    MAX_RETRIES = 3
    RETRY_DELAY = 5
    
    def __init__(self):
        self.imap_server = config.IMAP_SERVER
        self.imap_port = config.IMAP_PORT
        self.email_user = config.EMAIL_USER
        self.email_pass = config.EMAIL_PASS
        
        if not self.email_user or not self.email_pass:
            raise ValueError("EMAIL_USER e EMAIL_PASS devem estar configurados no .env")
    
    def __enter__(self):
        """Permite uso com 'with'"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Fecha conexão ao sair do 'with'"""
        self.close()

    def connect(self):
        """Conecta ao servidor IMAP com retry"""
        last_error = None
        
        for tentativa in range(1, self.MAX_RETRIES + 1):
            try:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                
                logging.info(f"Conectando ao servidor IMAP: {self.imap_server}:{self.imap_port} (tentativa {tentativa})")
                self.mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port, ssl_context=context)
                self.mail.login(self.email_user, self.email_pass)
                logging.info("Login IMAP realizado com sucesso")
                self.mail.select("INBOX")
                return
            except Exception as e:
                last_error = e
                logging.warning(f"Tentativa {tentativa} falhou: {e}")
                if tentativa < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY)
        
        logging.error(f"Falha ao conectar após {self.MAX_RETRIES} tentativas")
        raise last_error

    def close(self):
        """Fecha conexão IMAP"""
        if hasattr(self, 'mail'):
            try:
                self.mail.close()
                self.mail.logout()
            except Exception:
                pass

    def get_2fa_code(self, timeout=None):
        """
        Busca código 2FA de 6 dígitos.
        """
        if timeout is None:
            timeout = config.TIMEOUT_2FA
            
        # Se não estiver conectado, conectar
        if not hasattr(self, 'mail'):
            self.connect()
        
        start = time.time()
        logging.info(f"Aguardando código 2FA no email (timeout: {timeout}s)...")
        
        while time.time() - start < timeout:
            try:
                # Otimização: Buscar apenas emails do dia atual ou não lidos se possível
                # Mas para garantir, vamos buscar os últimos 10 emails
                status, data = self.mail.search(None, 'ALL')
                
                if status != 'OK':
                    time.sleep(2)
                    continue
                
                email_ids = data[0].split()
                if not email_ids:
                    time.sleep(2)
                    continue
                
                # Olhar apenas os últimos X emails para ser mais rápido
                limit = getattr(config, 'IMAP_SEARCH_LIMIT', 10)
                recent_ids = email_ids[-limit:]
                
                for email_id in reversed(recent_ids):
                    try:
                        status, msg_data = self.mail.fetch(email_id, "(RFC822)")
                        if status != 'OK': continue
                        
                        raw_email = msg_data[0][1]
                        msg = email.message_from_bytes(raw_email)
                        subject = self._decode_subject(msg.get("Subject", ""))
                        
                        if "Portal e-SAJ - Validação de identificação" in subject or "validacao" in subject.lower():
                            body = self._extract_email_body(msg)
                            if body:
                                code_match = re.search(r"\b(\d{6})\b", body)
                                if code_match:
                                    code = code_match.group(1)
                                    logging.info(f"Código 2FA encontrado: {code}")
                                    return code
                    except Exception:
                        continue
                
                time.sleep(3)
                
            except Exception as e:
                logging.error(f"Erro ao ler emails: {e}")
                time.sleep(2)
        
        logging.warning(f"Nenhum código 2FA recebido no prazo de {timeout}s")
        return None
    
    def _decode_subject(self, subject):
        """
        Decodifica o assunto do email que pode estar em formato MIME
        
        Args:
            subject: Assunto do email
            
        Returns:
            str: Assunto decodificado
        """
        if not subject:
            return ""
        
        try:
            decoded_parts = decode_header(subject)
            decoded_subject = ""
            
            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    if encoding:
                        decoded_subject += part.decode(encoding)
                    else:
                        # Tentar UTF-8 primeiro, depois latin1
                        try:
                            decoded_subject += part.decode('utf-8')
                        except UnicodeDecodeError:
                            try:
                                decoded_subject += part.decode('latin1')
                            except UnicodeDecodeError:
                                decoded_subject += part.decode('utf-8', errors='ignore')
                else:
                    decoded_subject += str(part)
            
            return decoded_subject
        except Exception as e:
            logging.error(f"Erro ao decodificar assunto: {e}")
            return str(subject)
    
    def _extract_email_body(self, msg):
        """
        Extrai o corpo do email (suporta multipart)
        
        Args:
            msg: Objeto email.message
            
        Returns:
            str: Corpo do email ou None
        """
        body = None
        
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype in ["text/plain", "text/html"]:
                    try:
                        body = part.get_payload(decode=True).decode()
                    except UnicodeDecodeError:
                        try:
                            body = part.get_payload(decode=True).decode("latin1")
                        except Exception as e:
                            logging.error(f"Erro ao decodificar parte do email: {e}")
                            continue
                    break
        else:
            try:
                body = msg.get_payload(decode=True).decode()
            except UnicodeDecodeError:
                try:
                    body = msg.get_payload(decode=True).decode("latin1")
                except Exception as e:
                    logging.error(f"Erro ao decodificar email: {e}")
        
        return body
