"""
Servico de email transacional via Resend.

Usa httpx (ja e dependencia do projeto) para chamar a API REST do Resend,
evitando adicionar um SDK novo. Em producao, configure RESEND_API_KEY e um
EMAIL_FROM com dominio verificado no Resend (o sender padrao onboarding@resend.dev
so entrega para o email dono da conta, util apenas em testes).
"""
import httpx

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


def _enviar_email(to_email: str, subject: str, html: str) -> bool:
    """
    Envia um email via Resend. Retorna True se aceito, False caso contrario.

    Nunca levanta excecao para o chamador: uma falha de envio de email nao deve
    quebrar o fluxo de negocio (ex: forgot-password continua retornando 200).
    """
    if not settings.RESEND_API_KEY:
        logger.warning("RESEND_API_KEY nao configurada - email nao enviado", extra={"to": to_email})
        return False

    try:
        resp = httpx.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.EMAIL_FROM,
                "to": [to_email],
                "subject": subject,
                "html": html,
            },
            timeout=10.0,
        )
        if resp.status_code >= 400:
            logger.error(
                "Resend retornou erro ao enviar email",
                extra={"status": resp.status_code, "body": resp.text[:300]},
            )
            return False
        return True
    except Exception:
        logger.exception("Falha ao enviar email via Resend", extra={"to": to_email})
        return False


def send_password_reset_email(to_email: str, reset_link: str) -> bool:
    """Envia o email de redefinicao de senha com o link contendo o token."""
    subject = "Redefinicao de senha - AdaptAI"
    html = f"""\
    <div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto; color: #1f2937;">
      <h2 style="color: #4f46e5; margin-bottom: 8px;">Redefinicao de senha</h2>
      <p>Voce solicitou a redefinicao da sua senha no AdaptAI.</p>
      <p>Clique no botao abaixo para criar uma nova senha. O link expira em 30 minutos.</p>
      <p style="margin: 24px 0;">
        <a href="{reset_link}"
           style="background: #4f46e5; color: #ffffff; padding: 12px 20px; border-radius: 8px; text-decoration: none; display: inline-block;">
          Redefinir minha senha
        </a>
      </p>
      <p style="font-size: 13px; color: #6b7280; word-break: break-all;">
        Se o botao nao funcionar, copie e cole este endereco no navegador:<br>{reset_link}
      </p>
      <p style="font-size: 13px; color: #6b7280; margin-top: 16px;">
        Se voce nao solicitou isso, pode ignorar este email com seguranca - sua senha continua a mesma.
      </p>
    </div>
    """
    return _enviar_email(to_email, subject, html)
