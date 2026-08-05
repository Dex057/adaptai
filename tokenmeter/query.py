"""Consulta e métrica normalizada. Filtros combináveis, inclusive nas dimensões livres."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import and_, distinct, func, select

from .event import to_utc_naive


def _bounds(start, end):
    return (to_utc_naive(start) if start else None, to_utc_naive(end) if end else None)


def _tag_filters(ev, tag, tags: dict | None):
    """Semi-join por IN: entra pelo índice (tag_key, tag_value, event_id) como covering.

    A forma com EXISTS dá o mesmo resultado dirigindo pela tabela de eventos — muito mais
    lenta em base grande (medimos 273 ms vs 0,5 ms com 200 mil eventos).
    """
    conds = []
    for k, v in (tags or {}).items():
        sub = select(tag.c.event_id).where(and_(tag.c.tag_key == k, tag.c.tag_value == str(v)))
        conds.append(ev.c.event_id.in_(sub))
    return conds


def _where(ev, tag, start, end, feature, provider, model, environment, service, status, tags):
    s, e = _bounds(start, end)
    conds = []
    if s: conds.append(ev.c.occurred_at >= s)
    if e: conds.append(ev.c.occurred_at < e)
    if feature: conds.append(ev.c.feature.in_([feature] if isinstance(feature, str) else feature))
    if provider: conds.append(ev.c.provider == provider)
    if model: conds.append(ev.c.model.in_([model] if isinstance(model, str) else model))
    if environment: conds.append(ev.c.environment == environment)
    if service: conds.append(ev.c.service == service)
    if status: conds.append(ev.c.status == status)
    conds += _tag_filters(ev, tag, tags)
    return conds


class TokenAggregationError(ValueError):
    """Somar tokens entre modelos com tokenizadores diferentes produz número sem sentido."""


def query(store, *, start=None, end=None, feature=None, provider=None, model=None,
          environment=None, service=None, status=None, tags=None,
          group_by: list[str] | None = None, allow_token_mixing: bool = False):
    """Agregação com filtros combináveis.

    Modelos usam tokenizadores diferentes (o Sonnet 5 conta 1,0–1,35x mais tokens que os
    anteriores para o MESMO texto). Por isso, agregar tokens sem quebrar por `model` é
    barrado: o número seria um degrau de tokenizador disfarçado de consumo.
    """
    ev, tag = store.ev, store.tag
    group_by = list(group_by or [])
    if group_by and "model" not in group_by and not allow_token_mixing:
        raise TokenAggregationError(
            "agregação de tokens sem 'model' no group_by. Modelos têm tokenizadores "
            "diferentes — inclua 'model', ou passe allow_token_mixing=True se você só "
            "vai olhar cost_usd (que é comparável entre modelos)."
        )
    cols = [ev.c[g] for g in group_by]
    stmt = select(
        *cols,
        func.count().label("calls"),
        func.sum(ev.c.input_tokens).label("input_tokens"),
        func.sum(ev.c.output_tokens).label("output_tokens"),
        func.sum(ev.c.cache_read_tokens).label("cache_read_tokens"),
        func.sum(ev.c.total_tokens).label("total_tokens"),
        func.sum(ev.c.cost_usd).label("cost_usd"),
        func.sum(ev.c.priced).label("priced_calls"),
    ).where(and_(True, *_where(ev, tag, start, end, feature, provider, model,
                              environment, service, status, tags)))
    if cols:
        stmt = stmt.group_by(*cols).order_by(func.sum(ev.c.cost_usd).desc())
    with store.connect() as con:
        return [dict(r._mapping) for r in con.execute(stmt)]


def cost_per_unit(store, *, unit: str, start=None, end=None, **filters):
    """Custo por unidade de negócio: SUM(cost) / COUNT(DISTINCT dimensão).

    unit = "run_id" | "tags.<chave>"  (ex.: "tags.entity_id" -> custo por laudo)
    Esta é a métrica que atravessa troca de modelo e de tokenizador sem perder sentido.
    """
    ev, tag = store.ev, store.tag
    conds = _where(ev, tag, start, end, filters.get("feature"), filters.get("provider"),
                   filters.get("model"), filters.get("environment"), filters.get("service"),
                   filters.get("status"), filters.get("tags"))
    if unit.startswith("tags."):
        key = unit.split(".", 1)[1]
        j = ev.join(tag, and_(tag.c.event_id == ev.c.event_id, tag.c.tag_key == key))
        stmt = select(func.sum(ev.c.cost_usd), func.count(distinct(tag.c.tag_value)),
                      func.count()).select_from(j).where(and_(True, *conds))
    else:
        col = ev.c[unit]
        stmt = select(func.sum(ev.c.cost_usd), func.count(distinct(col)),
                      func.count()).where(and_(True, *conds))
    with store.connect() as con:
        total, units, calls = con.execute(stmt).first()
    total = Decimal(str(total or 0))
    units = int(units or 0)
    return {
        "unit": unit,
        "total_cost_usd": total,
        "units": units,
        "calls": int(calls or 0),
        "calls_per_unit": (Decimal(calls) / units) if units else None,
        "cost_per_unit": (total / units) if units else None,
    }


def coverage(store, *, start=None, end=None):
    """Termômetro do projeto: % de chamadas com atribuição explícita."""
    ev, tag = store.ev, store.tag
    conds = _where(ev, tag, start, end, None, None, None, None, None, None, None)
    stmt = (select(ev.c.feature_source, func.count().label("calls"))
            .where(and_(True, *conds)).group_by(ev.c.feature_source))
    with store.connect() as con:
        rows = {r[0]: r[1] for r in con.execute(stmt)}
    total = sum(rows.values()) or 0
    good = rows.get("explicit", 0) + rows.get("context", 0)
    return {"por_origem": rows, "total": total,
            "pct_atribuido": (100.0 * good / total) if total else None}


def unpriced(store):
    ev = store.ev
    stmt = select(ev.c.provider, ev.c.model, func.count().label("calls")).where(
        ev.c.priced == 0).group_by(ev.c.provider, ev.c.model)
    with store.connect() as con:
        return [dict(r._mapping) for r in con.execute(stmt)]
