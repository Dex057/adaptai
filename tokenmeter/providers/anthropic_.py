"""Extração de uso do SDK anthropic. Defensiva: nenhuma leitura pode derrubar a feature."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RawUsage:
    input_tokens: int = 0          # entrada NÃO cacheada (semântica canônica)
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    model: str = ""
    request_id: str | None = None


def _i(obj, name: str) -> int:
    v = getattr(obj, name, None)
    if v is None and isinstance(obj, dict):
        v = obj.get(name)
    try:
        return int(v or 0)
    except Exception:
        return 0


def extract(response) -> RawUsage:
    """Na Anthropic, input_tokens JÁ exclui os tokens de cache — não subtrair aqui.

    (Na OpenAI, prompt_tokens INCLUI os cacheados; quando o segundo adapter chegar, é lá
    que a subtração precisa acontecer, ou o custo sai inflado.)
    """
    usage = getattr(response, "usage", None) or {}
    return RawUsage(
        input_tokens=_i(usage, "input_tokens"),
        output_tokens=_i(usage, "output_tokens"),
        cache_write_tokens=_i(usage, "cache_creation_input_tokens"),
        cache_read_tokens=_i(usage, "cache_read_input_tokens"),
        model=str(getattr(response, "model", "") or ""),
        request_id=getattr(response, "_request_id", None) or getattr(response, "id", None),
    )


def model_family(model: str) -> str | None:
    """claude-sonnet-4-5-20250929 -> claude-sonnet-4-5 (agregação estável entre releases)."""
    if not model:
        return None
    parts = model.split("-")
    while parts and parts[-1].isdigit() and len(parts[-1]) == 8:
        parts.pop()
    return "-".join(parts) or None
