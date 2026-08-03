"""CLI: migrate | check | doctor | export. É por aqui que a ferramenta é usada no dia a dia."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:                       # py<3.11
    tomllib = None


def _dsn(args) -> str:
    d = args.dsn or os.environ.get("TOKENMETER_DSN")
    if not d:
        sys.exit("erro: informe --dsn ou defina TOKENMETER_DSN")
    return d


def _load_check_cfg(root: Path) -> dict:
    p = root / "pyproject.toml"
    if not p.exists() or tomllib is None:
        return {}
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
        return data.get("tool", {}).get("tokenmeter", {}).get("check", {})
    except Exception:
        return {}


def _iso(s: str | None):
    if not s:
        return None
    return dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser("tokenmeter")
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("migrate", help="cria/atualiza as tabelas")
    m.add_argument("--dsn"); m.add_argument("--prefix", default="")

    c = sub.add_parser("check", help="acha chamadas de LLM que escapam do tracking")
    c.add_argument("--path", default=".")
    c.add_argument("--allow", action="append", default=None,
                   help="módulo autorizado a construir o client (repetível)")
    c.add_argument("--report", action="store_true",
                   help="apenas lista (exit 0) — use para levantar o inventário inicial")

    d = sub.add_parser("doctor", help="saúde da ferramenta: preço, cobertura, dead-letter")
    d.add_argument("--dsn"); d.add_argument("--prefix", default="")
    d.add_argument("--service", default="cli"); d.add_argument("--json", action="store_true")

    mo = sub.add_parser("models", help="confere os IDs de modelo do repo contra a API e o pricing")
    mo.add_argument("--path", default=".")
    mo.add_argument("--offline", action="store_true", help="não consulta a API do provedor")
    mo.add_argument("--api-key", default=None, help="senão, usa ANTHROPIC_API_KEY")

    e = sub.add_parser("export", help="extrato em CSV")
    e.add_argument("--dsn"); e.add_argument("--prefix", default="")
    e.add_argument("--start"); e.add_argument("--end")
    e.add_argument("--group-by", default="feature,model")
    e.add_argument("--out", default="extrato.csv")

    args = ap.parse_args(argv)

    if args.cmd == "check":
        from .check import scan
        root = Path(args.path).resolve()
        cfg = _load_check_cfg(root)
        allowed = args.allow or cfg.get("allowed_client_modules") or []
        providers = cfg.get("providers") or ["anthropic"]
        if not allowed:
            print("aviso: nenhum módulo autorizado configurado "
                  "([tool.tokenmeter.check] allowed_client_modules ou --allow)\n")
        found = scan(root, allowed, providers)
        erros = [f for f in found if f.severity == "error"]
        avisos = [f for f in found if f.severity != "error"]
        if not found:
            print(f"tokenmeter check: OK — nenhuma chamada de LLM fora de {allowed or '[]'}")
            return 0
        if erros:
            print(f"tokenmeter check: {len(erros)} ponto(s) fora do tracking\n")
            for f in erros:
                print(" ", f)
            print("\nCada um desses é consumo que acontece e não é medido.")
            print("Correção: mover a construção do client para", allowed or "um módulo único",
                  "e envolver com tokenmeter.wrap().")
        else:
            print(f"tokenmeter check: OK — nenhuma construção de client fora de {allowed}")
        if avisos:
            print(f"\n{len(avisos)} aviso(s) — import do SDK sem construir client "
                  f"(uso legítimo: tipos de exceção). Silencie com `# tokenmeter: allow`:")
            for f in avisos:
                print(" ", f)
        return 0 if (args.report or not erros) else 1

    if args.cmd == "models":
        from .models_check import verificar
        from .pricing import PriceBook
        try:
            pb = PriceBook()
        except Exception:
            pb = None
        rep = verificar(args.path, pricebook=pb, live=not args.offline, api_key=args.api_key)

        print(f"tokenmeter models: {len(rep.ocorrencias)} referência(s) a modelo no código")
        if not rep.consultou_api:
            print("  (sem consulta à API — defina ANTHROPIC_API_KEY ou tire --offline)\n")
        else:
            print(f"  ({len(rep.vivos)} modelos ativos na conta)\n")

        if rep.aposentados:
            print("MODELO APOSENTADO — estas chamadas FALHAM em runtime:")
            for m, ocs in sorted(rep.aposentados.items()):
                print(f"\n  {m}")
                for o in ocs:
                    print(f"     {o.path}:{o.line}  ({o.contexto})")
            print()
        elif rep.consultou_api:
            print("Nenhum modelo aposentado em uso.\n")

        se_preco = {m: o for m, o in rep.sem_preco.items() if m not in rep.aposentados}
        if se_preco:
            print("SEM PREÇO no pricing.yaml — evento grava, mas com cost_usd NULL:")
            for m, ocs in sorted(se_preco.items()):
                print(f"  {m}  ({len(ocs)} ocorrência(s))")
            print()

        if rep.consultou_api and not rep.aposentados and not se_preco:
            print("Tudo certo.")
        return 1 if rep.aposentados else 0

    import tokenmeter as tm

    if args.cmd == "migrate":
        tm.configure(_dsn(args), service="cli", table_prefix=args.prefix,
                     migrate_on_start=True, drain_on_start=False)
        print("tokenmeter: schema criado/atualizado")
        return 0

    if args.cmd == "doctor":
        tm.configure(_dsn(args), service=args.service, table_prefix=args.prefix,
                     drain_on_start=False)
        rep = tm.doctor()
        if args.json:
            print(json.dumps(rep, indent=2, default=str)); return 0
        cov = rep["coverage"]
        print("=== tokenmeter doctor ===")
        print(f"tabela de preço : {rep['pricing_version']}  ({rep['pricing_path']})")
        idade = rep["pricing_age_days"]
        print(f"revisada há     : {idade} dias" + ("   <-- VENCIDA" if rep["pricing_stale"] else ""))
        if rep["unpriced_models"]:
            print("modelos SEM preço (eventos gravados com priced=0):")
            for u in rep["unpriced_models"]:
                print(f"   - {u['provider']}/{u['model']}: {u['calls']} chamada(s)")
        else:
            print("modelos sem preço: nenhum")
        pct = cov["pct_atribuido"]
        print(f"cobertura       : {pct:.1f}% atribuído" if pct is not None else "cobertura: sem dados")
        for k, v in sorted(cov["por_origem"].items()):
            print(f"   {k:<10} {v}")
        print(f"dead-letter     : {rep['deadletter_pending']} evento(s) pendentes")
        return 0

    if args.cmd == "export":
        tm.configure(_dsn(args), service="cli", table_prefix=args.prefix, drain_on_start=False)
        gb = [g.strip() for g in args.group_by.split(",") if g.strip()]
        rows = tm.query(start=_iso(args.start), end=_iso(args.end), group_by=gb)
        path = tm.export_csv(rows, args.out)
        print(f"tokenmeter: {len(rows)} linha(s) -> {path}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
