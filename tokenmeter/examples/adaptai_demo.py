"""Demo ponta a ponta simulando a estrutura do AdaptAI.

O ponto a observar: as funções da camada de serviço (analisar_laudo, gerar_feedback,
classificar) NÃO têm uma única linha de tracking. Elas só chamam o client. O registro
acontece porque o client foi envolvido uma vez, no factory.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import tokenmeter as tm
from fake_anthropic import Anthropic

logging.basicConfig(level=logging.WARNING, format="  [%(levelname)s] %(message)s")

DB = Path(os.environ.get("DEMO_DB", "/tmp/tm-demo/usage.db"))
DL = Path("/tmp/tm-demo/deadletter.jsonl")
DB.parent.mkdir(parents=True, exist_ok=True)
for f in (DB, DL):
    f.unlink(missing_ok=True)

SONNET = "claude-sonnet-5-20260601"
HAIKU = "claude-haiku-4-5-20251001"


# ============ o que o projeto hospedeiro escreve: 3 pontos, uma vez ============

class F:                                   # registro leve de features (decisão 10)
    ANALISE_LAUDO = "analise_laudo"
    FEEDBACK = "feedback_aluno"
    CLASSIFICACAO = "classificacao_cid"
    ALL = ["analise_laudo", "feedback_aluno", "classificacao_cid"]


# (1) startup da aplicação
tm.configure(
    dsn=f"sqlite:///{DB}",
    service="adaptai",
    environment="prod",
    deadletter_path=str(DL),
    known_features=F.ALL,
    migrate_on_start=True,
)

# (2) o ÚNICO lugar do repositório que constrói um client
_client = tm.wrap(Anthropic(api_key="sk-..."))

def get_client():
    return _client


# ============ camada de serviço: ZERO linhas de tracking ============

def analisar_laudo(laudo_id: str) -> str:
    r = get_client().messages.create(model=SONNET, max_tokens=2000,
                                     messages=[{"role": "user", "content": "..."}], cache=True)
    return r.id

def gerar_feedback(aluno_id: str) -> str:
    r = get_client().messages.create(model=SONNET, max_tokens=800,
                                     messages=[{"role": "user", "content": "..."}])
    return r.id

def classificar(texto: str) -> str:
    r = get_client().messages.create(model=HAIKU, max_tokens=200,
                                     messages=[{"role": "user", "content": "..."}])
    return r.id

def resumir_streaming(laudo_id: str, abortar_em=None) -> None:
    with get_client().messages.stream(model=SONNET, abortar_em=abortar_em) as s:
        for _ in s:
            pass


# ============ pontos de entrada: aqui é onde a atribuição é aberta ============

async def rota_processar_laudo(escola_id: str, laudo_id: str):
    """Equivalente a uma rota FastAPI. Uma linha de contexto cobre tudo lá dentro."""
    with tm.context(feature=F.ANALISE_LAUDO,
                    tags={"tenant_id": escola_id, "entity_id": laudo_id,
                          "entity_type": "laudo"}):
        # pipeline com 3 chamadas -> mesmo run_id -> "custo por laudo" fecha
        await asyncio.to_thread(analisar_laudo, laudo_id)
        await asyncio.to_thread(classificar, "...")
        await asyncio.to_thread(resumir_streaming, laudo_id)


async def rota_feedback(escola_id: str, aluno_id: str):
    with tm.context(feature=F.FEEDBACK,
                    tags={"tenant_id": escola_id, "entity_id": aluno_id,
                          "entity_type": "aluno"}):
        await asyncio.to_thread(gerar_feedback, aluno_id)


def job_sem_contexto():
    """Ponto que ninguém instrumentou — a lib infere do stack em vez de perder o evento."""
    classificar("...")


# ============ execução ============

async def main():
    print("=" * 78)
    print("1. TRÁFEGO SIMULADO  (nenhuma função de serviço tem código de tracking)")
    print("=" * 78)
    escolas = ["escola-7", "escola-7", "escola-7", "escola-12", "escola-12"]
    for n, esc in enumerate(escolas):
        await rota_processar_laudo(esc, f"laudo-{n+1}")
    for n, esc in enumerate(["escola-7", "escola-12"]):
        await rota_feedback(esc, f"aluno-{n+1}")
    job_sem_contexto()                       # feature inferida
    resumir_streaming("laudo-x", abortar_em=4)   # stream abortado -> status=partial

    st = tm._stats()
    print(f"  {st['written']} eventos gravados | dead-letter: {st['deadlettered']} | perdidos: {st['lost']}")

    print()
    print("=" * 78)
    print("2. CONSULTA POR FEATURE E MODELO")
    print("=" * 78)
    rows = tm.query(group_by=["feature", "model"])
    print(f"  {'feature':<22}{'modelo':<28}{'chamadas':>9}{'tokens':>10}{'custo USD':>12}")
    for r in rows:
        print(f"  {r['feature']:<22}{r['model']:<28}{r['calls']:>9}"
              f"{r['total_tokens']:>10}{float(r['cost_usd'] or 0):>12.6f}")

    print()
    print("=" * 78)
    print("3. FILTRO COMBINADO NAS DIMENSÕES LIVRES  (escola-7, tipo laudo)")
    print("=" * 78)
    rows = tm.query(tags={"tenant_id": "escola-7", "entity_type": "laudo"},
                    group_by=["feature", "model"])
    for r in rows:
        print(f"  {r['feature']:<22}{r['model']:<28}{r['calls']:>9}"
              f"{float(r['cost_usd'] or 0):>12.6f}")

    print()
    print("=" * 78)
    print("4. MÉTRICA NORMALIZADA  (o requisito nº 5 do briefing)")
    print("=" * 78)
    for unidade, rotulo in [("tags.entity_id", "por entidade (laudo/aluno)"),
                            ("run_id", "por execução de pipeline")]:
        m = tm.cost_per_unit(unit=unidade)
        print(f"  {rotulo:<32} {m['units']:>3} unidades  "
              f"{float(m['cost_per_unit'] or 0):.6f} USD/unidade  "
              f"({float(m['calls_per_unit'] or 0):.1f} chamadas cada)")
    m = tm.cost_per_unit(unit="tags.entity_id", tags={"entity_type": "laudo"})
    print(f"  {'só laudos':<32} {m['units']:>3} unidades  "
          f"{float(m['cost_per_unit'] or 0):.6f} USD/laudo")

    print()
    print("=" * 78)
    print("5. COBERTURA DA ATRIBUIÇÃO  (a métrica de sucesso do projeto)")
    print("=" * 78)
    cov = tm.coverage()
    print(f"  {cov['pct_atribuido']:.1f}% das chamadas com atribuição explícita")
    for k, v in sorted(cov["por_origem"].items()):
        nota = "  <-- ponto sem tm.context(); evento salvo mesmo assim" if k == "inferred" else ""
        print(f"     {k:<10} {v}{nota}")

    print()
    print("=" * 78)
    print("6. GUARDA CONTRA SOMAR TOKENS ENTRE MODELOS")
    print("=" * 78)
    try:
        tm.query(group_by=["feature"])
    except Exception as e:
        print(f"  bloqueado: {type(e).__name__}")
        print(f"  {e}")
    rows = tm.query(group_by=["feature"], allow_token_mixing=True)
    print(f"  com allow_token_mixing=True: {len(rows)} linhas (custo USD segue comparável)")

    print()
    print("=" * 78)
    print("7. EXTRATO CSV")
    print("=" * 78)
    rows = tm.query(group_by=["feature", "model"])
    out = tm.export_csv(rows, "/tmp/tm-demo/extrato.csv")
    print(f"  {out}")
    print("  " + "\n  ".join(Path(out).read_text().splitlines()[:4]))


asyncio.run(main())
