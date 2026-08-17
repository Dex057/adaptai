"""PriceBook: (provider, model, instante) -> tarifas. Decimal em todo o caminho."""
from __future__ import annotations

import datetime as dt
import fnmatch
import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import yaml

log = logging.getLogger("tokenmeter")

MTOK = Decimal(1_000_000)
_DEFAULT_YAML = Path(__file__).with_name("pricing.yaml")


@dataclass(frozen=True)
class Rate:
    input_per_mtok: Decimal
    output_per_mtok: Decimal
    cache_write_per_mtok: Decimal | None
    cache_read_per_mtok: Decimal | None
    # Preço por CHAMADA (não por token) — cobre operações que não tokenizam,
    # como geração de imagem: o provedor cobra por unidade gerada, não por
    # entrada/saída de texto. Somado ao custo de token (que fica 0 nesse caso),
    # não exige um campo novo por operação — só um jeito diferente de tarifar.
    per_call_usd: Decimal | None
    version: str
    specificity: int


def _dec(v) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def _ts(v) -> dt.datetime | None:
    if v in (None, ""):
        return None
    if isinstance(v, dt.datetime):
        return v.replace(tzinfo=None)
    if isinstance(v, dt.date):
        return dt.datetime(v.year, v.month, v.day)
    return dt.datetime.fromisoformat(str(v))


class PriceBook:
    """Cascata: YAML embarcado -> arquivo em TOKENMETER_PRICING.

    A tabela no banco entra quando houver mais de um consumidor lendo o mesmo preço.
    """

    def __init__(self, path: str | os.PathLike | None = None):
        p = Path(path or os.environ.get("TOKENMETER_PRICING") or _DEFAULT_YAML)
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        self.version: str = str(raw.get("version", "?"))
        self.reviewed_at: dt.date | None = None
        if raw.get("reviewed_at"):
            r = raw["reviewed_at"]
            self.reviewed_at = r if isinstance(r, dt.date) else dt.date.fromisoformat(str(r))
        self.source: str | None = raw.get("source")
        self.path = str(p)
        self._rows = []
        for e in raw.get("prices", []):
            self._rows.append((
                e["provider"], e["model_pattern"], int(e.get("specificity", 1)),
                _ts(e["effective_from"]), _ts(e.get("effective_to")),
                Rate(_dec(e["input_per_mtok"]), _dec(e["output_per_mtok"]),
                     _dec(e.get("cache_write_per_mtok")), _dec(e.get("cache_read_per_mtok")),
                     _dec(e.get("per_call_usd")),
                     self.version, int(e.get("specificity", 1))),
            ))

    def resolve(self, provider: str, model: str, at: dt.datetime) -> Rate | None:
        """Mais específico vence. Vigência decide entre versões do mesmo padrão."""
        best: Rate | None = None
        for prov, pattern, spec, eff_from, eff_to, rate in self._rows:
            if prov != provider or not fnmatch.fnmatch(model, pattern):
                continue
            if eff_from and at < eff_from:
                continue
            if eff_to and at >= eff_to:
                continue
            if best is None or spec > best.specificity:
                best = rate
        return best

    def cost(self, provider: str, model: str, at: dt.datetime, *, input_tokens: int,
             output_tokens: int, cache_write_tokens: int = 0,
             cache_read_tokens: int = 0, calls: int = 0) -> tuple[Decimal | None, str | None]:
        """Retorna (custo, versão). Modelo desconhecido -> (None, None), NUNCA exceção.

        `calls` é quantas unidades tarifadas por chamada este evento representa
        (normalmente 0 para chat, 1 para uma imagem gerada). Só produz custo se
        a tarifa resolvida tiver `per_call_usd` — sem isso, `calls` é ignorado
        em silêncio, então chamadas de chat comuns não precisam se preocupar
        com o parâmetro.
        """
        rate = self.resolve(provider, model, at)
        if rate is None:
            log.warning(
                "tokenmeter: sem preço para %s/%s em %s — evento gravado com priced=0. "
                "Os tokens não se perdem; um reprocessamento posterior precifica.",
                provider, model, at.date())
            return None, None
        total = (Decimal(input_tokens) * rate.input_per_mtok
                 + Decimal(output_tokens) * rate.output_per_mtok
                 + Decimal(cache_write_tokens) * (rate.cache_write_per_mtok or rate.input_per_mtok)
                 + Decimal(cache_read_tokens) * (rate.cache_read_per_mtok or rate.input_per_mtok))
        total = total / MTOK
        if rate.per_call_usd is not None and calls:
            total += Decimal(calls) * rate.per_call_usd
        return total.quantize(Decimal("0.0000000001")), rate.version

    def age_days(self, today: dt.date | None = None) -> int | None:
        if not self.reviewed_at:
            return None
        return ((today or dt.date.today()) - self.reviewed_at).days
