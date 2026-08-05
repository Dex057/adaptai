"""tokenmeter — rastreamento de consumo de LLM, plugável em qualquer projeto Python.

Integração mínima (3 linhas no projeto hospedeiro):

    import tokenmeter as tm
    tm.configure(dsn=os.environ["TOKENMETER_DSN"], service="adaptai", environment="prod")
    client = tm.wrap(Anthropic())          # no ÚNICO factory de client do repositório

A partir daí, toda chamada feita com esse client é registrada — sem uma linha por feature.
"""
from __future__ import annotations

import logging
import time
from decimal import Decimal
from typing import Any

from . import query as _q
from .context import (context, current_run_id, current_tags, resolve_feature,
                      set_known_features, tag)
from .context import feature
from .event import UsageEvent, TokenmeterError, utcnow
from .pricing import PriceBook
from .providers import anthropic_ as _anthropic
from .recorder import Recorder
from .store import Store

__version__ = "0.1.0"
__all__ = ["configure", "wrap", "context", "tag", "feature", "record", "query", "cost_per_unit",
           "coverage", "export_csv", "doctor", "migrate", "UsageEvent", "TokenmeterError"]

log = logging.getLogger("tokenmeter")


class _Config:
    store: Store | None = None
    recorder: Recorder | None = None
    prices: PriceBook | None = None
    service: str = "unknown"
    environment: str = "dev"
    enabled: bool = True


_cfg = _Config()


def configure(dsn: str, *, service: str, environment: str = "dev",
              deadletter_path: str | None = None, table_prefix: str = "",
              pricing_path: str | None = None, known_features=None,
              enabled: bool = True, migrate_on_start: bool = False,
              drain_on_start: bool = True, connect_timeout: int = 5,
              pool_recycle: int = 180) -> None:
    """Inicialização única, no startup da aplicação."""
    _cfg.store = Store(dsn, table_prefix=table_prefix,
                       connect_timeout=connect_timeout, pool_recycle=pool_recycle)
    _cfg.recorder = Recorder(_cfg.store, deadletter_path)
    _cfg.prices = PriceBook(pricing_path)
    _cfg.service, _cfg.environment, _cfg.enabled = service, environment, enabled
    set_known_features(known_features)
    if migrate_on_start:
        _cfg.store.migrate()
    if drain_on_start:
        try:
            n = _cfg.recorder.drain()
            if n:
                log.info("tokenmeter: %d evento(s) recuperados do dead-letter no startup", n)
        except Exception:
            log.warning("tokenmeter: drain do dead-letter falhou", exc_info=True)


def migrate() -> None:
    _require().migrate()


def _require() -> Store:
    if _cfg.store is None:
        raise TokenmeterError("tokenmeter.configure(...) não foi chamado")
    return _cfg.store


def record(*, model: str, input_tokens: int = 0, output_tokens: int = 0,
           cache_write_tokens: int = 0, cache_read_tokens: int = 0,
           provider: str = "anthropic", operation: str = "chat",
           feature: str | None = None, tags: dict[str, Any] | None = None,
           status: str = "ok", error_type: str | None = None,
           duration_ms: int | None = None, provider_request_id: str | None = None,
           occurred_at=None) -> None:
    """Escape hatch manual. Nunca levanta exceção — nem se você passar lixo."""
    if not _cfg.enabled or _cfg.recorder is None:
        return
    try:
        feat, src = resolve_feature(feature)
        merged = {**current_tags(), **(tags or {})}
        ev = UsageEvent(
            occurred_at=occurred_at or utcnow(), service=_cfg.service,
            environment=_cfg.environment, sdk_version=__version__, provider=provider,
            model=model, model_family=_anthropic.model_family(model), operation=operation,
            feature=feat, feature_source=src, run_id=current_run_id(),
            input_tokens=input_tokens, output_tokens=output_tokens,
            cache_write_tokens=cache_write_tokens, cache_read_tokens=cache_read_tokens,
            status=status, error_type=error_type, duration_ms=duration_ms,
            provider_request_id=provider_request_id, tags=merged,
        )
        cost, version = _cfg.prices.cost(
            provider, model, ev.occurred_at, input_tokens=ev.input_tokens,
            output_tokens=ev.output_tokens, cache_write_tokens=ev.cache_write_tokens,
            cache_read_tokens=ev.cache_read_tokens)
        ev.cost_usd, ev.pricing_version, ev.priced = cost, version, int(cost is not None)
        _cfg.recorder.record(ev)
    except Exception:
        log.warning("tokenmeter: registro falhou e foi descartado", exc_info=True)
        # a feature monitorada segue intacta. sempre.


# --------------------------------------------------------------------------- captura

class _StreamProxy:
    """Registra no fechamento do stream, não só na exaustão feliz.

    Stream abandonado no meio (break, timeout, disconnect) gastou tokens de verdade;
    sem isso, vira consumo invisível.
    """

    def __init__(self, inner, feature, tags, t0):
        self._inner, self._feature, self._tags, self._t0 = inner, feature, tags, t0
        self._done = False
        self._final = None          # usage definitivo (só chega no último chunk)
        self._last = None           # melhor snapshot conhecido até agora
        self._completo = False

    def __enter__(self):
        self._stream = self._inner.__enter__()
        return self

    def __exit__(self, *exc):
        try:
            self._flush()           # registra mesmo se o bloco saiu por exceção ou break
        finally:
            return self._inner.__exit__(*exc)

    def __iter__(self):
        try:
            for chunk in self._stream:
                msg = getattr(chunk, "message", None)
                if msg is not None:
                    self._last = msg
                yield chunk
            self._completo = True
        finally:
            self._flush()

    def get_final_message(self):
        msg = self._stream.get_final_message()
        self._last = msg
        self._completo = True
        return msg

    def _flush(self) -> None:
        """Stream abandonado no meio gastou tokens de verdade.

        O usage definitivo só chega no último chunk, mas message_start já traz
        input_tokens. Registrar o snapshot parcial marcado como 'partial' é muito melhor
        que não registrar nada — que era o comportamento antes desta correção.
        """
        if self._done:
            return
        self._done = True
        msg = self._last
        partial = not self._completo
        if msg is None:
            return
        u = _anthropic.extract(msg)
        record(model=u.model, input_tokens=u.input_tokens, output_tokens=u.output_tokens,
               cache_write_tokens=u.cache_write_tokens, cache_read_tokens=u.cache_read_tokens,
               feature=self._feature, tags=self._tags, status="partial" if partial else "ok",
               duration_ms=int((time.perf_counter() - self._t0) * 1000),
               provider_request_id=u.request_id)


class _MessagesProxy:
    def __init__(self, inner, feature, tags):
        self._inner, self._feature, self._tags = inner, feature, tags

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def create(self, *a, **kw):
        t0 = time.perf_counter()
        try:
            resp = self._inner.create(*a, **kw)
        except Exception as exc:
            record(model=str(kw.get("model", "")), status="error",
                   error_type=type(exc).__name__, feature=self._feature, tags=self._tags,
                   duration_ms=int((time.perf_counter() - t0) * 1000))
            raise                                   # o erro do provedor é do caller
        u = _anthropic.extract(resp)
        record(model=u.model or str(kw.get("model", "")), input_tokens=u.input_tokens,
               output_tokens=u.output_tokens, cache_write_tokens=u.cache_write_tokens,
               cache_read_tokens=u.cache_read_tokens, feature=self._feature, tags=self._tags,
               duration_ms=int((time.perf_counter() - t0) * 1000),
               provider_request_id=u.request_id)
        return resp

    def stream(self, *a, **kw):
        return _StreamProxy(self._inner.stream(*a, **kw), self._feature, self._tags,
                            time.perf_counter())


class _ClientProxy:
    def __init__(self, inner, feature=None, tags=None):
        object.__setattr__(self, "_tm_inner", inner)
        object.__setattr__(self, "_tm_feature", feature)
        object.__setattr__(self, "_tm_tags", tags or {})
        object.__setattr__(self, "_tm_wrapped", True)

    def __getattr__(self, name):
        inner = object.__getattribute__(self, "_tm_inner")
        attr = getattr(inner, name)
        if name == "messages":
            return _MessagesProxy(attr, object.__getattribute__(self, "_tm_feature"),
                                  object.__getattribute__(self, "_tm_tags"))
        if name in ("with_options", "copy", "with_raw_response", "with_streaming_response"):
            # Esses métodos devolvem um NOVO client. Sem re-embrulhar, uma chamada como
            # client.with_options(timeout=120) escaparia do tracking em silêncio — o pior
            # tipo de furo, porque parece instrumentado. Descoberto ao migrar o AdaptAI,
            # onde prova_ai_service precisa de timeout próprio.
            feature = object.__getattribute__(self, "_tm_feature")
            tags = object.__getattribute__(self, "_tm_tags")

            def _rewrap(*a, **kw):
                return _ClientProxy(attr(*a, **kw), feature, tags)

            return _rewrap
        return attr

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, "_tm_inner"), name, value)


def wrap(client, *, feature: str | None = None, tags: dict[str, Any] | None = None):
    """Envolve o client do provedor. Idempotente: embrulhar duas vezes não conta duas vezes."""
    if getattr(client, "_tm_wrapped", False):
        return client
    return _ClientProxy(client, feature, tags)


# --------------------------------------------------------------------------- consulta

def query(**kw):
    return _q.query(_require(), **kw)


def cost_per_unit(**kw):
    return _q.cost_per_unit(_require(), **kw)


def coverage(**kw):
    return _q.coverage(_require(), **kw)


def unpriced():
    return _q.unpriced(_require())


def export_csv(rows: list[dict], path: str) -> str:
    from .export import export_csv as _e
    return _e(rows, path)


def doctor(price_age_warn_days: int = 90) -> dict:
    """Saúde da própria ferramenta. É o que substitui um dono formal da tabela de preço."""
    store = _require()
    cov = _q.coverage(store)
    unp = _q.unpriced(store)
    age = _cfg.prices.age_days() if _cfg.prices else None
    return {
        "pricing_version": _cfg.prices.version if _cfg.prices else None,
        "pricing_path": _cfg.prices.path if _cfg.prices else None,
        "pricing_age_days": age,
        "pricing_stale": bool(age is not None and age > price_age_warn_days),
        "unpriced_models": unp,
        "coverage": cov,
        "deadletter_pending": _cfg.recorder.deadletter_size() if _cfg.recorder else 0,
        "recorder_stats": dict(_cfg.recorder.stats) if _cfg.recorder else {},
    }


def _stats() -> dict:
    return dict(_cfg.recorder.stats) if _cfg.recorder else {}
