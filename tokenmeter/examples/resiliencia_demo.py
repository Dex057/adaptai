"""Os testes que decidem se a ferramenta é utilidade ou passivo.

Cada bloco corresponde a um critério de pronto do doc 03.
"""
from __future__ import annotations

import logging
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import tokenmeter as tm
from fake_anthropic import Anthropic
from sqlalchemy import text

logging.disable(logging.CRITICAL)          # a lib loga warnings; aqui só queremos o resultado

BASE = Path("/tmp/tm-resil")
BASE.mkdir(exist_ok=True)
DB, DL = BASE / "usage.db", BASE / "deadletter.jsonl"
for f in (DB, DL):
    f.unlink(missing_ok=True)

SONNET = "claude-sonnet-5-20260601"
tm.configure(dsn=f"sqlite:///{DB}", service="adaptai", environment="prod",
             deadletter_path=str(DL), migrate_on_start=True)
client = tm.wrap(Anthropic())

def total() -> int:
    with tm._require().connect() as c:
        return c.execute(text("SELECT COUNT(*) FROM usage_event")).scalar()

ok = lambda cond: "PASSOU" if cond else "*** FALHOU ***"
print("=" * 78)


# --- 1. banco fora do ar: a feature responde, o evento vai pro dead-letter ----
class BancoQuebrado:
    def __init__(self, real): self.real = real
    def write(self, e): raise ConnectionError("Can't connect to MySQL server (2003)")

store_real = tm._cfg.store
tm._cfg.recorder.store = BancoQuebrado(store_real)

with tm.context(feature="analise_laudo", tags={"tenant_id": "escola-7", "entity_id": "laudo-99"}):
    resp = client.messages.create(model=SONNET, max_tokens=100, messages=[])
antes = total()
print(f"1. BANCO FORA DO AR")
print(f"   a feature respondeu normalmente?          {ok(resp.id.startswith('msg_'))}  (id={resp.id})")
print(f"   nenhuma exceção vazou pro caller?         {ok(True)}")
print(f"   evento foi para o dead-letter?            {ok(DL.exists() and tm._cfg.recorder.deadletter_size() == 1)}")
print(f"   linhas no banco: {antes}  |  pendentes no dead-letter: {tm._cfg.recorder.deadletter_size()}")


# --- 2. banco volta: replay recupera, e replay repetido não duplica -----------
tm._cfg.recorder.store = store_real
n = tm._cfg.recorder.drain()
depois = total()
tm._cfg.recorder.drain(); tm._cfg.recorder.drain()
print(f"\n2. BANCO VOLTA (drain no startup)")
print(f"   eventos recuperados:                      {n}")
print(f"   perda permanente?                         {ok(depois == antes + 1)}  ({antes} -> {depois})")
print(f"   3 replays seguidos duplicam?              {ok(total() == depois)}  (total segue {total()})")


# --- 3. sink E dead-letter quebrados: ainda assim nada vaza -------------------
tm._cfg.recorder.store = BancoQuebrado(None)
tm._cfg.recorder.dl = Path("/proc/impossivel/dl.jsonl")
vazou = False
try:
    with tm.context(feature="feedback_aluno"):
        client.messages.create(model=SONNET, max_tokens=100, messages=[])
except Exception as e:
    vazou = True
print(f"\n3. SINK **E** DEAD-LETTER INDISPONÍVEIS")
print(f"   exceção vazou pro caller?                 {ok(not vazou)}")
print(f"   contabilizado como perdido?               {ok(tm._cfg.recorder.stats['lost'] == 1)}  "
      f"(stats={tm._cfg.recorder.stats})")
tm._cfg.recorder.store, tm._cfg.recorder.dl = store_real, DL


# --- 4. rollback do negócio não apaga o registro de uso ----------------------
from sqlalchemy import create_engine
neg = create_engine(f"sqlite:///{DB}")
antes = total()
with neg.connect() as con:
    trans = con.begin()
    con.execute(text("CREATE TABLE IF NOT EXISTS pedido (id INTEGER PRIMARY KEY)"))
    con.execute(text("INSERT INTO pedido (id) VALUES (1)"))
    with tm.context(feature="analise_laudo", tags={"entity_id": "laudo-rollback"}):
        client.messages.create(model=SONNET, max_tokens=100, messages=[])
    dl_durante = tm._cfg.recorder.deadletter_size()
    trans.rollback()                        # o negócio desfez tudo
with neg.connect() as con:
    pedidos = con.execute(text("SELECT COUNT(*) FROM pedido")).scalar()
tm._cfg.recorder.drain()                    # o que caiu no dead-letter volta
print(f"\n4. ROLLBACK DA TRANSAÇÃO DE NEGÓCIO")
print(f"   o pedido sumiu (rollback funcionou)?      {ok(pedidos == 0)}")
print(f"   o registro de uso sobreviveu?             {ok(total() == antes + 1)}  "
      f"(o token foi gasto e cobrado de qualquer jeito)")
if dl_durante:
    print(f"   NOTA: no SQLite a transação de negócio segura o lock de escrita (single-writer),")
    print(f"   então o evento caiu no dead-letter e voltou no drain — sem perda, com atraso.")
    print(f"   MySQL e Postgres gravam em conexões concorrentes sem essa contenção.")


# --- 5. erro do provedor: registrado como error, e o erro segue pro caller ----
antes = total()
levantou = False
try:
    with tm.context(feature="classificacao_cid"):
        client.messages.create(model=SONNET, max_tokens=100, messages=[], falhar=True)
except RuntimeError:
    levantou = True
with tm._require().connect() as c:
    st = c.execute(text("SELECT status, error_type FROM usage_event "
                        "ORDER BY recorded_at DESC LIMIT 1")).first()
print(f"\n5. ERRO DO PROVEDOR")
print(f"   o erro chegou ao caller (como deve)?      {ok(levantou)}")
print(f"   registrado com status/error_type?         {ok(st and st[0] == 'error')}  {tuple(st)}")


# --- 6. stream abortado no meio ----------------------------------------------
antes = total()
with tm.context(feature="analise_laudo", tags={"entity_id": "laudo-stream"}):
    with client.messages.stream(model=SONNET, abortar_em=3) as s:
        for i, _ in enumerate(s):
            if i >= 2:
                break                       # consumidor desiste
with tm._require().connect() as c:
    st = c.execute(text("SELECT status, input_tokens, output_tokens FROM usage_event "
                        "ORDER BY recorded_at DESC LIMIT 1")).first()
print(f"\n6. STREAM ABANDONADO NO MEIO")
print(f"   gerou evento (em vez de sumir)?           {ok(total() == antes + 1)}")
print(f"   marcado como parcial?                     {ok(st and st[0] == 'partial')}  "
      f"status={st[0]}, input={st[1]}, output={st[2]}")


# --- 7. modelo sem preço: grava mesmo assim ----------------------------------
antes = total()
with tm.context(feature="analise_laudo"):
    client.messages.create(model="modelo-que-nao-existe-v9", max_tokens=100, messages=[])
with tm._require().connect() as c:
    r = c.execute(text("SELECT priced, cost_usd, total_tokens FROM usage_event "
                       "ORDER BY recorded_at DESC LIMIT 1")).first()
print(f"\n7. MODELO SEM PREÇO NA TABELA")
print(f"   evento gravado mesmo sem saber o preço?   {ok(total() == antes + 1)}")
print(f"   marcado priced=0 e cost NULL?             {ok(r[0] == 0 and r[1] is None)}  "
      f"(tokens preservados: {r[2]})")


# --- 8. vigência do preço: a virada de 01/09/2026 ----------------------------
import datetime as dt
pb = tm._cfg.prices
c_ago, v_ago = pb.cost("anthropic", SONNET, dt.datetime(2026, 8, 15),
                       input_tokens=1_000_000, output_tokens=1_000_000)
c_set, v_set = pb.cost("anthropic", SONNET, dt.datetime(2026, 9, 15),
                       input_tokens=1_000_000, output_tokens=1_000_000)
print(f"\n8. VIGÊNCIA TEMPORAL DO PREÇO (1M entrada + 1M saída, Sonnet 5)")
print(f"   em 15/08/2026 (promocional):              USD {c_ago}")
print(f"   em 15/09/2026 (tarifa cheia):             USD {c_set}")
print(f"   variação:                                 {(c_set/c_ago - 1) * 100:.0f}%  "
      f"{ok(c_set > c_ago)} — preço hardcoded erraria por esse tanto a partir de 01/09")


# --- 9. datetime naive é rejeitado, não assumido -----------------------------
from tokenmeter.event import to_utc_naive, TokenmeterError
rejeitou = False
try:
    to_utc_naive(dt.datetime(2026, 7, 31, 12, 0))
except TokenmeterError:
    rejeitou = True
convertido = to_utc_naive(dt.datetime(2026, 7, 31, 12, 0,
                                      tzinfo=dt.timezone(dt.timedelta(hours=-3))))
print(f"\n9. TIMESTAMPS")
print(f"   datetime sem timezone é rejeitado?        {ok(rejeitou)}")
print(f"   12:00 em UTC-3 vira 15:00 UTC?            {ok(convertido.hour == 15)}  ({convertido})")


# --- 10. guarda de PHI nas tags ---------------------------------------------
import io, logging as _lg
logging.disable(_lg.NOTSET)
buf = io.StringIO()
h = _lg.StreamHandler(buf)
lg = _lg.getLogger("tokenmeter"); lg.addHandler(h); lg.setLevel(_lg.WARNING)
from tokenmeter.event import normalize_tags
normalize_tags({"entity_id": "laudo-8842"})                       # ok, sem warning
normalize_tags({"observacao": "paciente relata dificuldade de atencao em sala"})
lg.removeHandler(h)
avisos = buf.getvalue()
print(f"\n10. GUARDA DE PHI NAS TAGS")
print(f"   ID opaco passa sem aviso?                 {ok('entity_id' not in avisos)}")
print(f"   texto livre dispara aviso?                {ok('observacao' in avisos)}")
print(f"   -> {avisos.strip().splitlines()[0][:96] if avisos else '(nenhum)'}")

print("\n" + "=" * 78)
