from datetime import datetime
import config
from validate_docbr import CPF, CNPJ
import re

class PeticionamentoHelper:
    def __init__(self, numero_processo):
        self.numero_processo = numero_processo
        self.dados_peticao = {}
        self.cpf_validator = CPF()
        self.cnpj_validator = CNPJ()
    
    def definir_tipo_peticao(self):
        """Define tipo de petição como RPV"""
        self.dados_peticao['tipo'] = 'RPV - Requisição de Pequeno Valor'
        return self.dados_peticao['tipo']
    
    def calcular_diferenca_rpv(self, valor_planilha, dados_validacao_manual=None):
        """
        Calcula diferença se valor ultrapassar limite de RPV e retorna todos os valores calculados.
        
        Args:
            valor_planilha: Valor total da execução
            dados_validacao_manual: Dict opcional com validação do usuário
            
        Returns:
            dict: Dicionário com todos os valores calculados e por extenso
        """
        from utils.numero_extenso import valor_por_extenso
        
        # Se houve validação manual, usamos os valores validados
        if dados_validacao_manual:
            limite = dados_validacao_manual['limite_rpv']
            decisao = dados_validacao_manual['tipo_requisicao']
            
            self.registrar_validacao_humana(valor_planilha, limite, decisao)
            
            if decisao == "PRECATÓRIO":
                diferenca = valor_planilha - limite
                self.dados_peticao['excede_rpv'] = True
                self.dados_peticao['valor_excedente'] = diferenca
                self.dados_peticao['valor_rpv'] = limite
                print(f"⚠ [VALIDADO PELO USUÁRIO] Valor excede limite de RPV")
                
                return {
                    'valor': valor_planilha,
                    'valor_extenso': valor_por_extenso(valor_planilha),
                    'valor_limite_rpv': limite,
                    'valor_limite_rpv_extenso': valor_por_extenso(limite),
                    'valor_renuncia': round(diferenca, 2),
                    'valor_renuncia_extenso': valor_por_extenso(diferenca),
                    'texto_status_rpv': f'EXCEDE O LIMITE DE R$ {limite:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'),
                    'codigo_peticionamento': '1265'
                }
            else:
                self.dados_peticao['excede_rpv'] = False
                self.dados_peticao['valor_rpv'] = valor_planilha
                print(f"✓ [VALIDADO PELO USUÁRIO] Valor confirmado dentro do RPV: R$ {valor_planilha:.2f}")
                
                return {
                    'valor': valor_planilha,
                    'valor_extenso': valor_por_extenso(valor_planilha),
                    'valor_limite_rpv': limite,
                    'valor_limite_rpv_extenso': valor_por_extenso(limite),
                    'valor_renuncia': 0,
                    'valor_renuncia_extenso': 'zero reais',
                    'texto_status_rpv': f'DENTRO DO LIMITE DE R$ {limite:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'),
                    'codigo_peticionamento': '1266'
                }
                
        # Fallback para lógica automática (config) se não houver validação manual
        else:
            if valor_planilha > config.LIMITE_RPV:
                diferenca = valor_planilha - config.LIMITE_RPV
                self.dados_peticao['excede_rpv'] = True
                self.dados_peticao['valor_excedente'] = diferenca
                self.dados_peticao['valor_rpv'] = config.LIMITE_RPV
                
                print(f"⚠ Valor excede limite de RPV (Automático)")
                print(f"  Valor total: R$ {valor_planilha:.2f}")
                print(f"  Valor RPV: R$ {config.LIMITE_RPV:.2f}")
                print(f"  Diferença: R$ {diferenca:.2f}")
                
                return {
                    'valor': valor_planilha,
                    'valor_extenso': valor_por_extenso(valor_planilha),
                    'valor_limite_rpv': config.LIMITE_RPV,
                    'valor_limite_rpv_extenso': valor_por_extenso(config.LIMITE_RPV),
                    'valor_renuncia': round(diferenca, 2),
                    'valor_renuncia_extenso': valor_por_extenso(diferenca),
                    'texto_status_rpv': f'EXCEDE O LIMITE DE R$ {config.LIMITE_RPV:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'),
                    'codigo_peticionamento': '1266'
                }
            else:
                self.dados_peticao['excede_rpv'] = False
                self.dados_peticao['valor_rpv'] = valor_planilha
                print(f"✓ Valor dentro do limite de RPV: R$ {valor_planilha:.2f}")
                
                return {
                    'valor': valor_planilha,
                    'valor_extenso': valor_por_extenso(valor_planilha),
                    'valor_limite_rpv': config.LIMITE_RPV,
                    'valor_limite_rpv_extenso': valor_por_extenso(config.LIMITE_RPV),
                    'valor_renuncia': 0,
                    'valor_renuncia_extenso': 'zero reais',
                    'texto_status_rpv': f'DENTRO DO LIMITE DE R$ {config.LIMITE_RPV:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'),
                    'codigo_peticionamento': '1266'
                }

    def registrar_validacao_humana(self, valor, limite, decisao):
        """Registra log de validação humana"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = (
                f"\n[{timestamp}] RPV VALIDADO MANUALMENTE\n"
                f"Usuário responsável: Advogado (Sessão Atual)\n"
                f"Valor da Execução: R$ {valor:.2f}\n"
                f"Limite Aplicado: R$ {limite:.2f}\n"
                f"Decisão: {decisao}\n"
                f"Confirmação: Checkbox 'Revisei o valor' marcado\n"
                f"{'-'*40}\n"
            )
            
            log_file = config.LOGS_DIR / "rpv_validation.log"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
                
            print(f"✓ Validação registrada em logs/rpv_validation.log")
            
        except Exception as e:
            print(f"⚠ Erro ao registrar log de validação: {e}")

    
    def _converter_data(self, data_str):
        """Converte string de data para datetime"""
        try:
            # Tenta formatos comuns
            for fmt in ["%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y"]:
                try:
                    return datetime.strptime(data_str, fmt)
                except ValueError:
                    continue
            raise ValueError("Formato de data desconhecido")
        except Exception as e:
            print(f"Erro ao converter data '{data_str}': {e}")
            return None

    def definir_datas(self, data_julgamento, data_transito):
        """Define datas de julgamento e trânsito em julgado"""
        dt_julgamento = self._converter_data(data_julgamento)
        dt_transito = self._converter_data(data_transito)
        
        self.dados_peticao['data_julgamento'] = dt_julgamento
        self.dados_peticao['data_transito_julgado'] = dt_transito
        
        fmt = "%d/%m/%Y"
        print(f"Data de Julgamento: {dt_julgamento.strftime(fmt) if dt_julgamento else 'Inválida'}")
        print(f"Data de Trânsito em Julgado: {dt_transito.strftime(fmt) if dt_transito else 'Inválida'}")
    
    def definir_embargos(self, houve_embargos):
        """Define se houve embargos/impugnação"""
        self.dados_peticao['embargos'] = houve_embargos
        
        if houve_embargos:
            print("⚠ Processo com embargos/impugnação")
        else:
            print("✓ Processo sem embargos/impugnação")
        
        return houve_embargos
    
    def definir_entidade_devedora(self, entidade):
        """Define dados da entidade devedora com validação"""
        nome = entidade.get('nome', '')
        cnpj = entidade.get('cnpj', '')
        tipo = entidade.get('tipo', 'Municipal')
        
        # Validação de CNPJ
        if cnpj and not self.cnpj_validator.validate(cnpj):
            print(f"⚠ ALERTA: CNPJ {cnpj} inválido!")
        
        # Validação de consistência Nome vs Tipo
        nome_lower = nome.lower()
        if tipo == 'Municipal' and 'estado' in nome_lower and 'são paulo' in nome_lower:
             print(f"⚠ ALERTA: Entidade marcada como Municipal mas nome sugere Estadual: {nome}")
        elif tipo == 'Estadual' and 'prefeitura' in nome_lower:
             print(f"⚠ ALERTA: Entidade marcada como Estadual mas nome sugere Municipal: {nome}")

        self.dados_peticao['entidade_devedora'] = {
            'nome': nome,
            'cnpj': cnpj,
            'tipo': tipo
        }
        
        print(f"Entidade Devedora: {nome} ({tipo})")
    
    def definir_natureza_credito(self, natureza='indenizatória'):
        """Define natureza do crédito"""
        self.dados_peticao['natureza_credito'] = natureza
        print(f"Natureza do Crédito: {natureza}")
    
    def adicionar_parte_requisicao(self, dados_parte):
        """Adiciona informações da parte para requisição com validação"""
        cpf = dados_parte.get('cpf', '')
        
        if cpf and not self.cpf_validator.validate(cpf):
             print(f"⚠ ALERTA: CPF {cpf} inválido!")
        
        parte = {
            'nome': dados_parte.get('nome', ''),
            'cpf': cpf,
            'rg': dados_parte.get('rg', ''),
            'data_nascimento': dados_parte.get('data_nascimento', ''),
            'endereco': dados_parte.get('endereco', ''),
            'telefone': dados_parte.get('telefone', ''),
            'email': dados_parte.get('email', '')
        }
        
        self.dados_peticao['parte'] = parte
        print(f"✓ Dados da parte adicionados: {parte['nome']}")
    
    def gerar_resumo_peticao(self):
        """Gera resumo dos dados para peticionamento"""
        print("\n" + "="*60)
        print("RESUMO PARA PETICIONAMENTO ELETRÔNICO")
        print("="*60)
        
        print(f"\nNúmero do Processo: {self.numero_processo}")
        print(f"Tipo de Petição: {self.dados_peticao.get('tipo', 'N/A')}")
        
        if self.dados_peticao.get('excede_rpv'):
            print(f"\n⚠ ATENÇÃO: Valor excede RPV")
            print(f"  Valor RPV: R$ {self.dados_peticao['valor_rpv']:.2f}")
            print(f"  Valor Excedente: R$ {self.dados_peticao['valor_excedente']:.2f}")
        else:
            print(f"\nValor RPV: R$ {self.dados_peticao.get('valor_rpv', 0):.2f}")
        
        dt_julg = self.dados_peticao.get('data_julgamento')
        dt_trans = self.dados_peticao.get('data_transito_julgado')
        
        print(f"\nData Julgamento: {dt_julg.strftime('%d/%m/%Y') if dt_julg else 'N/A'}")
        print(f"Data Trânsito: {dt_trans.strftime('%d/%m/%Y') if dt_trans else 'N/A'}")
        print(f"Embargos: {'Sim' if self.dados_peticao.get('embargos') else 'Não'}")
        
        if 'entidade_devedora' in self.dados_peticao:
            ent = self.dados_peticao['entidade_devedora']
            print(f"\nEntidade Devedora: {ent.get('nome', 'N/A')}")
            print(f"CNPJ: {ent.get('cnpj', 'N/A')}")
        
        print(f"\nNatureza do Crédito: {self.dados_peticao.get('natureza_credito', 'N/A')}")
        
        if 'parte' in self.dados_peticao:
            parte = self.dados_peticao['parte']
            print(f"\n--- Dados da Parte ---")
            print(f"Nome: {parte.get('nome', 'N/A')}")
            print(f"CPF: {parte.get('cpf', 'N/A')}")
            print(f"Data Nascimento: {parte.get('data_nascimento', 'N/A')}")
        
        print("="*60 + "\n")
        
        return self.dados_peticao
    
    def exportar_checklist(self):
        """Gera checklist para conferência antes de peticionar"""
        checklist = [
            "☐ Contrato.pdf gerado e conferido",
            "☐ Juntada_Completa.pdf gerado e conferido",
            "☐ Renúncia assinada",
            "☐ Dados da parte conferidos (CPF, RG, endereço)",
            "☐ Valores conferidos (RPV e/ou excedente)",
            "☐ Datas de julgamento e trânsito corretas",
            "☐ Natureza do crédito correta",
            "☐ Entidade devedora correta",
            "☐ Tipo de petição: RPV"
        ]
        
        print("\n📋 CHECKLIST PARA PETICIONAMENTO")
        print("-" * 50)
        for item in checklist:
            print(item)
        print("-" * 50 + "\n")
        
        return checklist