"""
Camada de provedores de geracao de imagem (ilustracao IA).

Objetivo: isolar o AdaptAI de QUAL servico gera a imagem. A regra do dominio
(escrever o prompt, salvar, vincular ao conteudo) mora em ilustracao_service;
aqui fica so o "manda o prompt, recebe os bytes da imagem".

Trocar de provedor = trocar settings.IMAGE_PROVIDER (e a chave). Hoje:
  - flux  -> Flux Pro via fal.ai (endpoint sincrono https://fal.run/{modelo})

KEY-READY: se a chave do provedor nao estiver configurada, gerar() levanta
ProvedorImagemIndisponivel com mensagem clara. A rota traduz isso para um 503
amigavel, e a parte de pictogramas ARASAAC (que nao usa provedor) segue viva.
"""
from __future__ import annotations

from typing import Optional
import httpx

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class ProvedorImagemIndisponivel(RuntimeError):
    """Provedor nao configurado (falta chave) ou desconhecido."""


class ErroGeracaoImagem(RuntimeError):
    """Falha ao gerar a imagem (rede, timeout, resposta invalida do provedor)."""


class ImageProvider:
    """Interface minima. Um provedor sabe transformar prompt -> bytes PNG/JPEG."""

    nome: str = "base"
    # Provedor de COBRANCA (ex.: "fal", a empresa que manda a fatura) e o
    # identificador do modelo dentro dele (ex.: o slug do fal.ai). `nome` acima
    # e o apelido interno do AdaptAI ("flux") - pode nao coincidir com quem
    # cobra, entao ficam campos separados. Expostos na interface para quem
    # instrumenta a chamada (tokenmeter) gravar sem precisar conhecer FluxProvider.
    provider: str = "unknown"
    model_id: str = "unknown"

    def disponivel(self) -> bool:
        raise NotImplementedError

    def gerar(self, prompt: str, *, tamanho: str = "quadrado") -> bytes:
        """Gera a imagem e devolve os BYTES. Levanta ErroGeracaoImagem em falha."""
        raise NotImplementedError


# Aspect ratios "amigaveis" -> dimensoes que os modelos Flux aceitam.
_DIMENSOES = {
    "quadrado": {"width": 1024, "height": 1024},
    "paisagem": {"width": 1344, "height": 768},
    "retrato": {"width": 768, "height": 1344},
}


class FluxProvider(ImageProvider):
    """Flux Pro via fal.ai (endpoint sincrono).

    fal.ai expoe cada modelo em https://fal.run/{model_id}. Autenticacao por
    header `Authorization: Key <FAL_API_KEY>`. A resposta traz
    {"images": [{"url": "...", "content_type": "image/..."}], ...}; baixamos a
    primeira imagem e devolvemos os bytes.
    """

    nome = "flux"
    provider = "fal"

    def __init__(self):
        self.api_key = (settings.FAL_API_KEY or "").strip()
        self.model_id = (settings.FLUX_MODEL or "fal-ai/flux-2-pro").strip()

    def disponivel(self) -> bool:
        return bool(self.api_key)

    def gerar(self, prompt: str, *, tamanho: str = "quadrado") -> bytes:
        if not self.disponivel():
            raise ProvedorImagemIndisponivel(
                "FAL_API_KEY nao configurada. Defina a chave do fal.ai no .env/Railway "
                "para habilitar a geracao de ilustracao por IA."
            )

        dims = _DIMENSOES.get(tamanho, _DIMENSOES["quadrado"])
        endpoint = "https://fal.run/%s" % self.model_id
        payload = {
            "prompt": prompt,
            "image_size": dims,          # aceita objeto {width,height} ou enum
            "output_format": "png",
            # Seguranca (publico infantil): checker on + tolerancia estrita.
            "enable_safety_checker": True,
        }
        headers = {
            "Authorization": "Key %s" % self.api_key,
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(endpoint, json=payload, headers=headers)
                resp.raise_for_status()
                dados = resp.json()
        except httpx.HTTPStatusError as e:
            corpo = ""
            try:
                corpo = e.response.text[:300]
            except Exception:
                pass
            logger.error("fal.ai retornou %s: %s", e.response.status_code, corpo)
            raise ErroGeracaoImagem("O provedor de imagem recusou a requisicao.") from e
        except Exception as e:
            logger.warning("Falha de rede ao chamar fal.ai", exc_info=True)
            raise ErroGeracaoImagem("Nao foi possivel falar com o provedor de imagem.") from e

        imagens = (dados or {}).get("images") or []
        if not imagens or not imagens[0].get("url"):
            logger.error("Resposta do fal.ai sem imagem: %s", str(dados)[:300])
            raise ErroGeracaoImagem("O provedor nao devolveu nenhuma imagem.")

        img_url = imagens[0]["url"]
        try:
            with httpx.Client(timeout=60.0) as client:
                img_resp = client.get(img_url)
                img_resp.raise_for_status()
                return img_resp.content
        except Exception as e:
            logger.warning("Falha ao baixar imagem gerada", exc_info=True)
            raise ErroGeracaoImagem("A imagem foi gerada mas nao pode ser baixada.") from e


_PROVEDORES = {
    "flux": FluxProvider,
}


def get_image_provider(nome: Optional[str] = None) -> ImageProvider:
    """Fabrica: devolve o provedor configurado (ou o pedido explicitamente).

    Levanta ProvedorImagemIndisponivel se o nome nao for reconhecido.
    """
    escolhido = (nome or settings.IMAGE_PROVIDER or "flux").strip().lower()
    cls = _PROVEDORES.get(escolhido)
    if cls is None:
        raise ProvedorImagemIndisponivel(
            "Provedor de imagem '%s' desconhecido. Disponiveis: %s"
            % (escolhido, ", ".join(sorted(_PROVEDORES)))
        )
    return cls()
