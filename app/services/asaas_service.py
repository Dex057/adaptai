"""
Servico de integracao com o gateway de pagamento Asaas.

Cobre o necessario para o checkout/assinatura do AdaptAI:
- criar/garantir cliente (customer)
- criar assinatura recorrente (subscription)
- buscar o link de pagamento da cobranca atual

Autenticacao: header 'access_token' com a API Key (settings.ASAAS_API_KEY).
Ambiente (sandbox/producao) e URL base vem de settings.asaas_base_url.

A chave NUNCA e logada. Se ASAAS_API_KEY nao estiver configurada, o servico
fica "desligado" (esta_configurado() == False) e o checkout segue sem gerar
cobranca (o trial e criado normalmente).
"""
import httpx
from typing import Optional, Dict, Any

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# User-Agent e obrigatorio em contas Asaas criadas a partir de 13/06/2024.
_USER_AGENT = "AdaptAI/1.0"
_TIMEOUT = 20.0


class AsaasError(Exception):
    """Erro de comunicacao/validacao com a API do Asaas."""


class AsaasService:
    def esta_configurado(self) -> bool:
        """True se ha API Key configurada (integracao habilitada)."""
        return bool(settings.ASAAS_API_KEY and settings.ASAAS_API_KEY.strip())

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
            "access_token": settings.ASAAS_API_KEY.strip(),
        }

    def _request(self, method: str, path: str, json: Optional[dict] = None) -> Dict[str, Any]:
        if not self.esta_configurado():
            raise AsaasError("Integracao Asaas nao configurada (ASAAS_API_KEY ausente).")
        url = f"{settings.asaas_base_url}{path}"
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                resp = client.request(method, url, headers=self._headers(), json=json)
        except httpx.HTTPError as e:
            logger.warning("Falha de rede ao chamar Asaas: %s", type(e).__name__)
            raise AsaasError("Nao foi possivel comunicar com o Asaas.") from e

        if resp.status_code >= 400:
            # Mensagem amigavel; detalhes vao para o log (sem expor a chave)
            try:
                erros = resp.json().get("errors", [])
                descr = "; ".join(e.get("description", "") for e in erros) or resp.text[:200]
            except Exception:
                descr = resp.text[:200]
            logger.warning("Asaas %s %s -> %s: %s", method, path, resp.status_code, descr)
            raise AsaasError(f"Asaas retornou erro {resp.status_code}.")

        try:
            return resp.json()
        except Exception as e:
            raise AsaasError("Resposta invalida do Asaas.") from e

    # ------------------------------------------------------------------
    # Clientes
    # ------------------------------------------------------------------
    def criar_cliente(
        self,
        nome: str,
        email: str,
        cpf_cnpj: Optional[str] = None,
        telefone: Optional[str] = None,
        external_reference: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cria um cliente no Asaas. Retorna o objeto (com 'id' = cus_...)."""
        payload: Dict[str, Any] = {"name": nome, "email": email}
        if cpf_cnpj:
            payload["cpfCnpj"] = cpf_cnpj
        if telefone:
            payload["mobilePhone"] = telefone
        if external_reference:
            payload["externalReference"] = external_reference
        return self._request("POST", "/customers", json=payload)

    # ------------------------------------------------------------------
    # Assinaturas
    # ------------------------------------------------------------------
    def criar_assinatura(
        self,
        customer_id: str,
        valor: float,
        descricao: str,
        next_due_date: str,  # 'YYYY-MM-DD'
        billing_type: str = "UNDEFINED",  # cliente escolhe PIX/BOLETO/CARTAO
        cycle: str = "MONTHLY",
        external_reference: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cria uma assinatura recorrente. Retorna o objeto (com 'id' = sub_...)."""
        payload: Dict[str, Any] = {
            "customer": customer_id,
            "billingType": billing_type,
            "value": round(float(valor), 2),
            "nextDueDate": next_due_date,
            "cycle": cycle,
            "description": descricao,
        }
        if external_reference:
            payload["externalReference"] = external_reference
        return self._request("POST", "/subscriptions", json=payload)

    def listar_pagamentos_assinatura(self, subscription_id: str) -> Dict[str, Any]:
        """Lista as cobrancas geradas por uma assinatura."""
        return self._request("GET", f"/subscriptions/{subscription_id}/payments")

    def obter_link_pagamento_assinatura(self, subscription_id: str) -> Optional[str]:
        """
        Retorna o link da cobranca mais recente da assinatura (invoiceUrl), se houver.
        Durante o trial pode nao existir cobranca ainda -> retorna None.
        """
        try:
            dados = self.listar_pagamentos_assinatura(subscription_id)
        except AsaasError:
            return None
        pagamentos = dados.get("data") or []
        if not pagamentos:
            return None
        # pega o mais recente que tenha invoiceUrl
        for pg in pagamentos:
            link = pg.get("invoiceUrl") or pg.get("bankSlipUrl")
            if link:
                return link
        return None


asaas_service = AsaasService()
