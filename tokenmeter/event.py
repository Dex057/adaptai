"""UsageEvent canônico + validação. Módulo puro: sem I/O, sem rede."""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import uuid
from dataclasses import dataclass, field, asdict
from decimal import Decimal
from typing import Any

log = logging.getLogger("tokenmeter")

_KEY_RE = re.compile(r"[^a-z0-9_]+")
TAG_VALUE_WARN_LEN = 64
TAG_VALUE_MAX_LEN = 255


class TokenmeterError(ValueError):
    """Erro de uso da biblioteca. Nunca escapa do caminho de gravação."""


def utcnow() -> dt.datetime:
    """UTC naive, sempre. Um único lugar no código produz 'agora'."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def to_utc_naive(value: dt.datetime) -> dt.datetime:
    """Aware -> UTC naive. Naive é REJEITADO, nunca assumido como UTC."""
    if not isinstance(value, dt.datetime):
        raise TokenmeterError(f"esperado datetime, recebido {type(value).__name__}")
    if value.tzinfo is None:
        raise TokenmeterError(
            "datetime sem timezone recebido. Passe um datetime aware "
            "(ex.: datetime.now(timezone.utc)) — assumir UTC é como o bug entra."
        )
    return value.astimezone(dt.timezone.utc).replace(tzinfo=None)


def normalize_tag_key(key: str) -> str:
    """tenant_id e tenantId viram a MESMA dimensão."""
    k = _KEY_RE.sub("_", str(key).strip().lower()).strip("_")
    if not k:
        raise TokenmeterError(f"chave de tag inválida: {key!r}")
    return k[:64]


def normalize_tag_value(key: str, value: Any) -> str:
    """Sempre string. Guarda de PHI: avisa quando o valor parece conteúdo, não identificador."""
    if isinstance(value, bool):
        v = "true" if value else "false"
    elif isinstance(value, (int, Decimal)):
        v = str(value)
    elif value is None:
        v = ""
    else:
        v = str(value)
    if len(v) > TAG_VALUE_WARN_LEN or v.count(" ") >= 4:
        log.warning(
            "tokenmeter: valor da tag %r parece conteúdo, não identificador (%d chars). "
            "Valores de tag devem ser IDs opacos ou enums — nunca texto livre, atributo "
            "clínico ou nome de pessoa.", key, len(v),
        )
    return v[:TAG_VALUE_MAX_LEN]


def normalize_tags(tags: dict[str, Any] | None) -> dict[str, str]:
    if not tags:
        return {}
    out: dict[str, str] = {}
    for k, v in tags.items():
        nk = normalize_tag_key(k)
        out[nk] = normalize_tag_value(nk, v)
    return out


@dataclass
class UsageEvent:
    # identidade
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    schema_version: int = 1
    # tempo (UTC naive sempre)
    occurred_at: dt.datetime = field(default_factory=utcnow)
    recorded_at: dt.datetime | None = None
    # origem
    service: str = "unknown"
    environment: str = "dev"
    sdk_version: str = "0.1.0"
    # o que foi chamado
    provider: str = "anthropic"
    model: str = ""
    model_family: str | None = None
    operation: str = "chat"
    # atribuição
    feature: str = "__unknown__"
    feature_source: str = "unknown"          # explicit | context | inferred | unknown
    run_id: str | None = None
    # consumo
    input_tokens: int = 0                    # entrada NÃO cacheada
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    total_tokens: int = 0
    # custo (sempre USD)
    cost_usd: Decimal | None = None
    priced: int = 0
    pricing_version: str | None = None
    # qualidade do registro
    status: str = "ok"                       # ok | partial | error
    error_type: str | None = None
    duration_ms: int | None = None
    provider_request_id: str | None = None
    # dimensões livres
    tags: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is not None:
            self.occurred_at = to_utc_naive(self.occurred_at)
        self.tags = normalize_tags(self.tags)
        self.total_tokens = (
            self.input_tokens + self.output_tokens
            + self.cache_write_tokens + self.cache_read_tokens
        )

    @property
    def occurred_date(self) -> dt.date:
        return self.occurred_at.date()

    def to_json(self) -> str:
        d = asdict(self)
        d["occurred_at"] = self.occurred_at.isoformat()
        d["recorded_at"] = self.recorded_at.isoformat() if self.recorded_at else None
        d["cost_usd"] = str(self.cost_usd) if self.cost_usd is not None else None
        return json.dumps(d, sort_keys=True, ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> "UsageEvent":
        d = json.loads(raw)
        d["occurred_at"] = dt.datetime.fromisoformat(d["occurred_at"])
        d["recorded_at"] = dt.datetime.fromisoformat(d["recorded_at"]) if d.get("recorded_at") else None
        d["cost_usd"] = Decimal(d["cost_usd"]) if d.get("cost_usd") else None
        d.pop("total_tokens", None)
        return cls(**d)
