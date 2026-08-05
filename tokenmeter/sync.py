"""Consolidação multi-projeto: copia eventos de N bancos de origem para um central.

MODELO: PULL, não push. Cada projeto continua gravando no PRÓPRIO banco, exatamente como
hoje. Um coletor externo lê periodicamente e consolida.

Por que pull e não um serviço de ingestão HTTP:

  - Nenhum projeto passa a depender de infraestrutura central. Se o coletor cair, ou o
    banco central sumir, nada acontece com nenhuma aplicação — o dado continua na origem.
  - O caminho de escrita das aplicações não muda, então tudo que já foi testado continua
    valendo. Um HttpSink introduziria rede no caminho quente de cada projeto.
  - Recuperação é reprocessar, não recuperar fila: baixou o coletor por 3 dias, roda de
    novo e ele busca o que falta.

O preço é latência (minutos, não segundos) — irrelevante para FinOps.

IDEMPOTÊNCIA: `event_id` é UUID gerado na origem e é PK no destino. Rodar o sync duas
vezes, ou com marcas d'água sobrepostas, não duplica nada. É o que torna seguro reprocessar
sem controle fino de estado.
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field

from sqlalchemy import (Column, DateTime, MetaData, String, Table, and_, create_engine,
                        func, insert, select)

from .store import Store, build_tables

log = logging.getLogger("tokenmeter")


def build_watermark_table(prefix: str = "") -> tuple[MetaData, Table]:
    """Marca d'água por origem. Vive só no banco central."""
    md = MetaData()
    wm = Table(
        f"{prefix}sync_watermark", md,
        Column("source", String(64), primary_key=True),   # nome lógico da origem
        Column("last_recorded_at", DateTime, nullable=False),
        Column("last_run_at", DateTime, nullable=False),
        Column("events_total", String(32), nullable=False, default="0"),
    )
    return md, wm


@dataclass
class ResultadoSync:
    source: str
    lidos: int = 0
    inseridos: int = 0
    duplicados: int = 0
    erro: str | None = None
    marca_de: dt.datetime | None = None
    marca_para: dt.datetime | None = None
    tags: int = 0


@dataclass
class Central:
    """Banco consolidado. Mesmo schema das origens + a tabela de marca d'água."""
    dsn: str
    table_prefix: str = ""

    def __post_init__(self):
        self.store = Store(self.dsn, table_prefix=self.table_prefix)
        self.md_wm, self.wm = build_watermark_table(self.table_prefix)

    def migrate(self) -> None:
        self.store.migrate()
        self.md_wm.create_all(self.store.engine)

    def watermark(self, source: str) -> dt.datetime:
        with self.store.connect() as con:
            r = con.execute(
                select(self.wm.c.last_recorded_at).where(self.wm.c.source == source)
            ).first()
        # Sobreposição de 1 hora de propósito: eventos que estavam no dead-letter da origem
        # chegam com recorded_at atrasado. A PK garante que reprocessar não duplica.
        return (r[0] - dt.timedelta(hours=1)) if r else dt.datetime(1970, 1, 1)


def sync_source(central: Central, source: str, dsn: str, *, table_prefix: str = "",
                lote: int = 1000, limite: int | None = None) -> ResultadoSync:
    """Puxa de UMA origem para o central. Nunca escreve na origem."""
    res = ResultadoSync(source=source)
    try:
        desde = central.watermark(source)
        res.marca_de = desde
        origem = create_engine(dsn, pool_pre_ping=True, future=True)
        _, ev_o, tag_o = build_tables(table_prefix)
        ev_c, tag_c = central.store.ev, central.store.tag

        maior = desde
        with origem.connect() as con_o:
            stmt = (select(ev_o).where(ev_o.c.recorded_at > desde)
                    .order_by(ev_o.c.recorded_at))
            if limite:
                stmt = stmt.limit(limite)
            linhas = [dict(r._mapping) for r in con_o.execute(stmt)]
            res.lidos = len(linhas)
            if not linhas:
                return res

            ids = [l["event_id"] for l in linhas]
            tags = []
            for i in range(0, len(ids), lote):
                fatia = ids[i:i + lote]
                tags += [dict(r._mapping) for r in con_o.execute(
                    select(tag_o).where(tag_o.c.event_id.in_(fatia)))]

        with central.store.engine.begin() as con_c:
            # Descobre o que já existe: uma consulta por lote, não uma por linha.
            existentes: set[str] = set()
            for i in range(0, len(ids), lote):
                fatia = ids[i:i + lote]
                existentes |= {r[0] for r in con_c.execute(
                    select(ev_c.c.event_id).where(ev_c.c.event_id.in_(fatia)))}

            novos = [l for l in linhas if l["event_id"] not in existentes]
            res.duplicados = len(linhas) - len(novos)
            if novos:
                for i in range(0, len(novos), lote):
                    con_c.execute(insert(ev_c), novos[i:i + lote])
                novos_ids = {l["event_id"] for l in novos}
                tags_novas = [t for t in tags if t["event_id"] in novos_ids]
                for i in range(0, len(tags_novas), lote):
                    con_c.execute(insert(tag_c), tags_novas[i:i + lote])
                res.tags = len(tags_novas)
            res.inseridos = len(novos)
            maior = max(l["recorded_at"] for l in linhas)

            agora = dt.datetime.utcnow()
            atual = con_c.execute(
                select(central.wm.c.source).where(central.wm.c.source == source)).first()
            if atual:
                con_c.execute(central.wm.update()
                              .where(central.wm.c.source == source)
                              .values(last_recorded_at=maior, last_run_at=agora,
                                      events_total=str(res.inseridos)))
            else:
                con_c.execute(insert(central.wm), {
                    "source": source, "last_recorded_at": maior,
                    "last_run_at": agora, "events_total": str(res.inseridos)})
        res.marca_para = maior
    except Exception as e:
        res.erro = f"{type(e).__name__}: {e}"
        # exc_info em DEBUG, não em WARNING: o chamador já recebe o erro no
        # ResultadoSync e o CLI o imprime na tabela. Traceback aqui só polui a saída.
        log.warning("tokenmeter sync: falha na origem %s — %s", source, res.erro)
        log.debug("tokenmeter sync: traceback da origem %s", source, exc_info=True)
        # Uma origem indisponível NÃO impede as outras — cada uma é independente.
    return res


def sync_all(central_dsn: str, fontes: dict[str, str], *, central_prefix: str = "",
             source_prefix: str = "", migrate: bool = False) -> list[ResultadoSync]:
    """fontes = {"adaptai": "mysql+pymysql://...", "projeto-b": "..."}"""
    central = Central(central_dsn, table_prefix=central_prefix)
    if migrate:
        central.migrate()
    return [sync_source(central, nome, dsn, table_prefix=source_prefix)
            for nome, dsn in fontes.items()]
