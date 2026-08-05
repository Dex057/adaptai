"""Kit de validação local: roda o ciclo inteiro sem infraestrutura nenhuma.

O que ele prova, na sua máquina, antes de qualquer deploy:

  1. captura   — a chamada de IA vira evento sem uma linha de tracking no serviço
  2. atribuição— tenant/usuário/entidade chegam pelo contexto, não por parâmetro
  3. resiliência— banco fora do ar não derruba a feature; o evento volta depois
  4. consulta  — filtro combinável, custo por unidade de negócio
  5. extrato   — CSV
  6. painel    — HTML autocontido, o mesmo que roda em produção
  7. doctor    — a ferramenta medindo a si mesma

Usa SQLite e um client falso. Não precisa de MySQL, de Docker, nem de chave de API.

    python examples/validar_local.py

Ao final, abra o arquivo painel-local.html no navegador. O que você vê ali é
exatamente o que verá apontando para o MySQL de produção — muda só o --dsn.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import tokenmeter as tm
from fake_anthropic import Anthropic

logging.basicConfig(level=logging.ERROR, format="  [%(levelname)s] %(message)s")

BASE = Path("/tmp/tm-validacao")
DB = BASE / "usage.db"
DL = BASE / "deadletter.jsonl"
SAIDA = Path(__file__).resolve().parents[1]

FEATURES = ["material_adaptado", "redacao_correcao", "pei_geracao",
            "planejamento_trimestre", "analise_qualitativa"]


def titulo(n: int, t: str) -> None:
    print(f"\n{'=' * 72}\n{n}. {t}\n{'=' * 72}")


# ---------------------------------------------------------------- camada "app"
# Repare: nenhuma destas funções fala com o tokenmeter. Elas só chamam o client.
_client = None


def get_client():
    return _client


@tm.feature("material_adaptado", entity_type="material", entity_from="material_id")
async def adaptar_material(material_id: int, tamanho: int = 900):
    return get_client().messages.create(
        model="claude-sonnet-4-6", max_tokens=tamanho,
        messages=[{"role": "user", "content": "adapta " + "x" * tamanho}])


@tm.feature("redacao_correcao", entity_type="redacao", entity_from="redacao_id")
async def corrigir_redacao(redacao_id: int):
    return get_client().messages.create(
        model="claude-sonnet-4-6", max_tokens=1200,
        messages=[{"role": "user", "content": "corrige " + "y" * 1400}])


@tm.feature("pei_geracao", entity_type="pei", entity_from="pei_id")
async def gerar_pei(pei_id: int):
    return get_client().messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=600,
        messages=[{"role": "user", "content": "pei " + "z" * 500}])


def _espalhar_no_tempo(dias_atras: list[int]) -> None:
    """Reescreve occurred_at/occurred_date para dar série temporal à demo.

    Isto NÃO é comportamento da biblioteca — ela sempre grava o instante real, em UTC.
    É só o gerador de dados da demo, porque as 100 chamadas acontecem no mesmo segundo.
    """
    from sqlalchemy import text
    store = tm._require()
    with store.connect() as con:
        ids = [r[0] for r in con.execute(
            text(f"SELECT event_id FROM {store.ev.name} ORDER BY recorded_at"))]
        for ev, d in zip(ids, dias_atras):
            con.execute(text(
                f"UPDATE {store.ev.name} SET "
                f"occurred_at = datetime(occurred_at, '-{d} days'), "
                f"occurred_date = date(occurred_at, '-{d} days') WHERE event_id = :e"),
                {"e": ev})
        con.commit()


async def main() -> int:
    global _client
    if BASE.exists():
        shutil.rmtree(BASE)
    BASE.mkdir(parents=True)

    titulo(1, "Captura — o serviço não tem código de tracking")
    tm.configure(f"sqlite:///{DB}", service="adaptai", environment="local",
                 deadletter_path=str(DL), migrate_on_start=True)
    _client = tm.wrap(Anthropic())
    print("   client envolvido uma vez. É o único ponto instrumentado do 'repositório'.")

    # tráfego espalhado em 14 dias, para o painel ter série temporal de verdade
    hoje = dt.datetime.now(dt.timezone.utc)
    escolas = ["escola-12", "escola-3", "escola-7"]
    dias_atras: list[int] = []
    n = 0
    for d in range(13, -1, -1):
        dia = hoje - dt.timedelta(days=d)
        volume = 3 if dia.weekday() >= 5 else 8      # fim de semana é fraco
        for i in range(volume):
            dias_atras.append(d)
            escola = escolas[(i + d) % len(escolas)]
            with tm.context(tags={"tenant_id": escola, "user_id": f"prof-{i % 5}"}):
                if i % 3 == 0:
                    await adaptar_material(material_id=100 + i, tamanho=700 + i * 30)
                elif i % 3 == 1:
                    await corrigir_redacao(redacao_id=200 + i)
                else:
                    await gerar_pei(pei_id=300 + i)
                n += 1
    print(f"   {n} chamadas de IA feitas. Nenhuma delas escreveu \'tokenmeter\' no código.")
    _espalhar_no_tempo(dias_atras)
    print("   (as datas foram reescritas depois, no banco, só para o painel ter série\n"
          "    temporal nesta demo — a lib sempre carimba o instante real da chamada.)")

    titulo(2, "Atribuição — quem gastou, sobre o quê")
    # A consulta recusa somar tokens sem 'model' no group_by: tokenizadores diferentes
    # contam a mesma frase de forma diferente, então "total de tokens" entre modelos é
    # um número que parece certo e não é. Aqui só olhamos custo, que é comparável.
    try:
        tm.query(group_by=["feature"], tags={"tenant_id": "escola-12"})
    except Exception as e:
        print(f"   guarda-corpo disparou: {type(e).__name__}")
        print(f"     {str(e).splitlines()[0][:96]}")
    linhas = tm.query(group_by=["feature"], tags={"tenant_id": "escola-12"},
                      allow_token_mixing=True)
    for r in linhas:
        print(f"   escola-12 · {r['feature']:<24} {r['calls']:>4} chamadas  "
              f"US$ {float(r['cost_usd'] or 0):.6f}")

    titulo(3, "Resiliência — banco fora do ar não derruba a feature")
    # dispose() antes de mexer no arquivo: sem isso a conexão do pool segue com o
    # descritor antigo aberto e a escrita passa — a falha seria fingida.
    # E o snapshot precisa levar o -wal/-shm junto: em WAL, parte das tabelas mora
    # no sidecar, e restaurar só o .db devolve um banco sem tabela nenhuma.
    tm._require().engine.dispose()
    snap = {f: f.read_bytes() for f in BASE.glob("usage.db*")}
    DB.write_bytes(b"isto nao e um banco sqlite")     # corrompe de proposito
    with tm.context(tags={"tenant_id": "escola-12"}):
        r = await adaptar_material(material_id=999)
    print(f"   feature respondeu normalmente: {r.usage.output_tokens} tokens de saída, "
          f"sem exceção")
    print(f"   dead-letter: {tm._stats()['deadlettered']} evento(s) em disco")
    tm._require().engine.dispose()
    for f, b in snap.items():                         # banco volta, inteiro
        f.write_bytes(b)
    with tm.context(tags={"tenant_id": "escola-12"}):
        await adaptar_material(material_id=998)       # o drain oportunista dispara aqui
    print(f"   banco voltou -> recuperados sozinhos: {tm._stats()['replayed']}  "
          f"(sem reiniciar a aplicação)")

    titulo(4, "Métrica normalizada — custo por unidade de negócio")
    for unidade, rotulo in (("tags.entity_id", "por entidade processada"),
                            ("run_id", "por execução")):
        u = tm.cost_per_unit(unit=unidade)
        print(f"   {rotulo:<26} US$ {float(u['cost_per_unit'] or 0):.6f}  "
              f"({u['units']} unidades)")

    titulo(5, "Extrato em CSV")
    csv = tm.export_csv(tm.query(group_by=["feature", "model"]),
                        str(SAIDA / "extrato-local.csv"))
    print(f"   {csv}")

    titulo(6, "Painel HTML")
    from tokenmeter.panel import gerar
    html = gerar(tm._require(), str(SAIDA / "painel-local.html"), dias=30,
                 titulo="AdaptAI — validação local", orcamento=20.0)
    print(f"   {html}")
    print("   abra no navegador. arquivo único, offline, sem servidor.")

    titulo(7, "doctor — a ferramenta medindo a si mesma")
    rep = tm.doctor()
    cob = rep["coverage"]
    print(f"   tabela de preço : {rep['pricing_version']} "
          f"(revisada há {rep['pricing_age_days']} dias)")
    print(f"   modelos sem preço: {len(rep['unpriced_models'])}")
    print(f"   cobertura        : {cob['pct_atribuido']:.1f}% com origem explícita")
    print(f"   dead-letter      : {rep['deadletter_pending']} pendente(s)")

    print(f"\n{'=' * 72}")
    print("Tudo isso rodou sem MySQL, sem Docker e sem chave de API.")
    print("Para apontar em produção muda UMA coisa: o --dsn.")
    print(f"{'=' * 72}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
