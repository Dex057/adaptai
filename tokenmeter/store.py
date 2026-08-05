"""Persistência. Engine PRÓPRIO, isolado da transação de negócio.

SQLAlchemy Core (não ORM) para não impor um Base ao projeto hospedeiro.
Tipos em denominador comum entre MySQL 8, PostgreSQL e SQLite.
"""
from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Column, Date, DateTime, ForeignKey, Index, Integer, MetaData,
    Numeric, SmallInteger, String, Table, Text, create_engine, insert, select,
)

from .event import UsageEvent, utcnow

log = logging.getLogger("tokenmeter")


def build_tables(prefix: str = "") -> tuple[MetaData, Table, Table]:
    md = MetaData()
    ev = Table(
        f"{prefix}usage_event", md,
        Column("event_id", String(36), primary_key=True),
        Column("schema_version", SmallInteger, nullable=False, default=1),
        # DateTime sem timezone: no MySQL vira DATETIME (nunca TIMESTAMP, que converte
        # pelo time_zone da sessão); no Postgres, TIMESTAMP WITHOUT TIME ZONE.
        Column("occurred_at", DateTime, nullable=False),
        Column("recorded_at", DateTime, nullable=False),
        Column("occurred_date", Date, nullable=False),
        Column("service", String(64), nullable=False),
        Column("environment", String(32), nullable=False),
        Column("sdk_version", String(32), nullable=False),
        Column("provider", String(64), nullable=False),
        Column("model", String(128), nullable=False),
        Column("model_family", String(64)),
        Column("operation", String(32), nullable=False),
        Column("feature", String(128), nullable=False, default="__unknown__"),
        Column("feature_source", String(16), nullable=False),
        Column("run_id", String(36)),
        Column("input_tokens", BigInteger, nullable=False, default=0),
        Column("output_tokens", BigInteger, nullable=False, default=0),
        Column("cache_write_tokens", BigInteger, nullable=False, default=0),
        Column("cache_read_tokens", BigInteger, nullable=False, default=0),
        Column("total_tokens", BigInteger, nullable=False, default=0),
        Column("cost_usd", Numeric(20, 10)),
        Column("priced", SmallInteger, nullable=False, default=0),
        Column("pricing_version", String(64)),
        Column("status", String(16), nullable=False, default="ok"),
        Column("error_type", String(64)),
        Column("duration_ms", Integer),
        Column("provider_request_id", String(128)),
        Column("tags_json", Text),
    )
    Index(f"ix_{prefix}ue_occurred", ev.c.occurred_at)
    Index(f"ix_{prefix}ue_feature_date", ev.c.feature, ev.c.occurred_date)

    tag = Table(
        f"{prefix}usage_event_tag", md,
        Column("event_id", String(36),
               ForeignKey(f"{prefix}usage_event.event_id", ondelete="CASCADE"),
               primary_key=True),
        Column("tag_key", String(64), primary_key=True),
        Column("tag_value", String(255), nullable=False),
    )
    Index(f"ix_{prefix}uet_lookup", tag.c.tag_key, tag.c.tag_value, tag.c.event_id)
    return md, ev, tag


class Store:
    def __init__(self, dsn: str, table_prefix: str = "", echo: bool = False,
                 connect_timeout: int = 5, pool_recycle: int = 180):
        kw: dict = {"pool_pre_ping": True, "future": True, "echo": echo}
        self.is_sqlite = dsn.startswith("sqlite")
        if self.is_sqlite:
            # SQLite é single-writer: uma transação de negócio aberta bloqueia a gravação
            # de uso. Esperar seria pior que dead-letter (viraria latência na feature),
            # então o timeout é curto de propósito e o dead-letter absorve.
            # Consequência: SQLite serve para dev e teste, não para produção concorrente.
            kw["connect_args"] = {"timeout": 0.25}
        else:
            # Banco pendurado não pode virar latência na feature monitorada — daí o
            # timeout curto. Mas curto demais gera dead-letter espúrio quando o DBaaS
            # está só lento, então 5s é o meio-termo (o padrão do driver é 10s+).
            kw["connect_args"] = {"connect_timeout": connect_timeout}
            kw["pool_size"] = 2
            kw["max_overflow"] = 1
            # DBaaS gerenciado costuma derrubar conexão ociosa em silêncio. Com volume
            # baixo, TODA conexão do pool estaria velha na próxima chamada; reciclar
            # proativamente evita depender só do pool_pre_ping.
            kw["pool_recycle"] = pool_recycle
        self.engine = create_engine(dsn, **kw)
        if self.is_sqlite:
            from sqlalchemy import event as _sa_event

            @_sa_event.listens_for(self.engine, "connect")
            def _wal(dbapi_con, _):
                cur = dbapi_con.cursor()
                cur.execute("PRAGMA journal_mode=WAL")   # leitura concorrente com escrita
                cur.close()
        self.md, self.ev, self.tag = build_tables(table_prefix)

    def migrate(self) -> None:
        self.md.create_all(self.engine)

    def _row(self, e: UsageEvent) -> dict:
        return {
            "event_id": e.event_id, "schema_version": e.schema_version,
            "occurred_at": e.occurred_at, "recorded_at": e.recorded_at or utcnow(),
            "occurred_date": e.occurred_date, "service": e.service,
            "environment": e.environment, "sdk_version": e.sdk_version,
            "provider": e.provider, "model": e.model, "model_family": e.model_family,
            "operation": e.operation, "feature": e.feature,
            "feature_source": e.feature_source, "run_id": e.run_id,
            "input_tokens": e.input_tokens, "output_tokens": e.output_tokens,
            "cache_write_tokens": e.cache_write_tokens,
            "cache_read_tokens": e.cache_read_tokens, "total_tokens": e.total_tokens,
            "cost_usd": e.cost_usd, "priced": e.priced,
            "pricing_version": e.pricing_version, "status": e.status,
            "error_type": e.error_type, "duration_ms": e.duration_ms,
            "provider_request_id": e.provider_request_id,
            "tags_json": __import__("json").dumps(e.tags, sort_keys=True, ensure_ascii=False),
        }

    def write(self, events: list[UsageEvent]) -> int:
        """Transação própria, commit imediato. Um rollback do negócio não apaga isto."""
        written = 0
        with self.engine.begin() as con:
            for e in events:
                # Idempotência portátil: SELECT de existência. As sintaxes de upsert
                # (INSERT IGNORE / ON CONFLICT / INSERT OR IGNORE) divergem entre os
                # três bancos-alvo, então não dá para usar sem quebrar portabilidade.
                exists = con.execute(
                    select(self.ev.c.event_id).where(self.ev.c.event_id == e.event_id)
                ).first()
                if exists:
                    continue
                con.execute(insert(self.ev), self._row(e))
                if e.tags:
                    con.execute(insert(self.tag), [
                        {"event_id": e.event_id, "tag_key": k, "tag_value": v}
                        for k, v in e.tags.items()
                    ])
                written += 1
        return written

    def connect(self):
        return self.engine.connect()
