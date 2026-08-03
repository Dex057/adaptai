"""Contexto ambiente de atribuição. contextvars propaga em asyncio e em asyncio.to_thread."""
from __future__ import annotations

import contextvars
import functools
import inspect
import logging
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from .event import normalize_tags

log = logging.getLogger("tokenmeter")

_UNKNOWN = "__unknown__"

_feature: contextvars.ContextVar[str | None] = contextvars.ContextVar("tm_feature", default=None)
_tags: contextvars.ContextVar[dict[str, str]] = contextvars.ContextVar("tm_tags", default={})
_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("tm_run_id", default=None)

_known_features: set[str] = set()


def set_known_features(names) -> None:
    global _known_features
    _known_features = set(names or ())


@contextmanager
def context(feature: str | None = None, tags: dict[str, Any] | None = None,
            run_id: str | None = None) -> Iterator[str]:
    """Abre um escopo de atribuição. Use nos PONTOS DE ENTRADA, não nos pontos de chamada."""
    if feature and _known_features and feature not in _known_features:
        log.warning(
            "tokenmeter: feature %r não registrada. Nomes divergentes fragmentam o relatório "
            "sem ninguém perceber — registre em known_features.", feature)
    merged = {**_tags.get(), **normalize_tags(tags)}      # escopo interno vence
    rid = run_id or _run_id.get() or str(uuid.uuid4())
    t_f = _feature.set(feature or _feature.get())
    t_t = _tags.set(merged)
    t_r = _run_id.set(rid)
    try:
        yield rid
    finally:
        _feature.reset(t_f)
        _tags.reset(t_t)
        _run_id.reset(t_r)


def tag(**kwargs: Any) -> None:
    """Acrescenta tags ao escopo de atribuição ATUAL, sem abrir um novo.

    Existe para o caso em que a informação de atribuição só aparece depois que o
    escopo foi aberto — o caso clássico é autenticação: o middleware abre o escopo
    no início do request, mas quem é o usuário e a escola só se sabe depois que a
    dependência de auth resolveu o token.

    Sem isso, a única saída seria passar tenant/usuário por parâmetro até a camada
    de serviço — que é exatamente o acoplamento que a biblioteca existe para evitar.

    Nunca levanta exceção: perder uma tag não pode derrubar a rota.
    """
    try:
        limpos = {k: v for k, v in kwargs.items() if v is not None}
        if not limpos:
            return
        _tags.set({**_tags.get(), **normalize_tags(limpos)})
    except Exception:
        log.warning("tokenmeter: falha ao acrescentar tags", exc_info=True)


def current_tags() -> dict[str, str]:
    return dict(_tags.get())


def current_run_id() -> str | None:
    return _run_id.get()


def _infer_from_stack() -> str | None:
    """Último recurso: deriva a feature do frame chamador, fora do próprio pacote."""
    _SKIP = ("tokenmeter", "asyncio", "concurrent", "threading", "contextlib",
             "functools", "runpy", "importlib")
    try:
        for frame in inspect.stack()[2:20]:
            mod = frame.frame.f_globals.get("__name__", "")
            if not mod or mod.startswith(_SKIP):
                continue
            return f"{mod}:{frame.function}"[:128]
    except Exception:
        pass
    return None


def resolve_feature(explicit: str | None = None) -> tuple[str, str]:
    """Cascata explicit -> context -> inferred -> unknown.

    feature_source é gravado junto para você MEDIR a qualidade da própria atribuição.
    """
    if explicit:
        return explicit, "explicit"
    ctx = _feature.get()
    if ctx:
        return ctx, "context"
    guess = _infer_from_stack()
    if guess:
        return guess, "inferred"
    return _UNKNOWN, "unknown"


def feature(nome: str, *, entity_type: str | None = None,
            entity_from: str | None = None, tags_from: dict[str, str] | None = None):
    """Decorator: declara a feature de uma função, e opcionalmente de onde vem a entidade.

    Preferido a envolver o corpo com `with context(...)`: é uma linha acima do `def`,
    não reindenta nada, e por isso o diff numa base existente fica trivial de revisar.

        @tm.feature(F.PEI_GERACAO, entity_type="pei", entity_from="pei_id")
        async def gerar_pei(pei_id: int, ...):
            ...

    entity_from é o NOME de um parâmetro. Se o valor for um objeto, tenta `.id`.
    tags_from mapeia nome_da_tag -> nome_do_parâmetro, para dimensões extras.

    Funciona em função síncrona e assíncrona. Nunca altera o retorno nem engole
    exceção da função decorada — só falha de atribuição é silenciada.
    """
    def _extrair(fn, args, kwargs) -> dict:
        extra: dict = {}
        try:
            ligado = inspect.signature(fn).bind_partial(*args, **kwargs)
            ligado.apply_defaults()
            val = ligado.arguments

            def _id(v):
                if v is None:
                    return None
                return getattr(v, "id", v)          # aceita objeto ORM ou id cru

            if entity_from:
                eid = _id(val.get(entity_from))
                if eid is not None:
                    extra["entity_id"] = eid
                    if entity_type:
                        extra["entity_type"] = entity_type
            for tag_nome, param in (tags_from or {}).items():
                v = _id(val.get(param))
                if v is not None:
                    extra[tag_nome] = v
        except Exception:
            log.debug("tokenmeter: não consegui extrair entidade de %s", getattr(fn, "__name__", "?"))
        return extra

    def deco(fn):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def _async(*args, **kwargs):
                with context(feature=nome, tags=_extrair(fn, args, kwargs)):
                    return await fn(*args, **kwargs)
            return _async

        @functools.wraps(fn)
        def _sync(*args, **kwargs):
            with context(feature=nome, tags=_extrair(fn, args, kwargs)):
                return fn(*args, **kwargs)
        return _sync

    return deco
