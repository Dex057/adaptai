"""Painel de consumo em HTML autocontido, gerado a partir do banco.

Sem Metabase, sem serviço extra, sem CDN: um arquivo .html que abre em qualquer
navegador, inclusive offline. Serve para (a) validar tudo localmente antes de subir e
(b) ser o painel de fato enquanto uma ferramenta dedicada não se justificar.

Quando o Metabase entrar, este módulo continua útil como conferência: se o número dele
divergir daqui, um dos dois está errado.
"""
from __future__ import annotations

import datetime as dt
import html
import json
from decimal import Decimal

from sqlalchemy import text

# Paleta validada com scripts/validate_palette.js (ver docs/DECISOES.md).
# Ordem fixa, nunca ciclada: a 6ª categoria vira "Outros".
SERIES_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
SERIES_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"]
OUTROS_LIGHT, OUTROS_DARK = "#898781", "#898781"
MAX_SERIES = 5
# As séries são referenciadas por variável CSS, nunca por hex literal: um `fill="#2a78d6"`
# inline no SVG não responde a @media (prefers-color-scheme), e o modo escuro tem passos
# próprios — validados contra a superfície escura, não um espelho automático do claro.
SERIES_VAR = [f"var(--s{i})" for i in range(MAX_SERIES)]
OUTROS_VAR = "var(--sx)"

# Declarações do modo escuro, uma vez só, usadas em DOIS seletores distintos:
# a media query (preferência do sistema) e o data-theme (escolha explícita no botão).
# Não dá para uni-los numa lista de seletores — uma at-rule não pode fechar uma lista,
# e o navegador descarta o bloco inteiro em silêncio se você tentar.
_ESCURO = ("--surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;"
           "--grid:#2c2c2a;--axis:#383835;--seq:#3987e5;--border:#2c2c2a;"
           + ";".join(f"--s{i}:{c}" for i, c in enumerate(SERIES_DARK))
           + ";--sx:#a3a196")


def _d(v) -> Decimal:
    return Decimal(str(v or 0))


def coletar(store, *, dias: int = 30, service: str | None = None,
            environment: str | None = None, tag_tenant: str = "tenant_id") -> dict:
    """Roda as agregações. Uma consulta por bloco do painel — nenhuma é pesada."""
    ev = f"{store.ev.name}"
    tg = f"{store.tag.name}"
    onde = ["e.occurred_at >= :ini"]
    p: dict = {"ini": dt.datetime.utcnow() - dt.timedelta(days=dias)}
    if service:
        onde.append("e.service = :svc"); p["svc"] = service
    if environment:
        onde.append("e.environment = :env"); p["env"] = environment
    W = " AND ".join(onde)

    with store.connect() as con:
        def q(sql, **extra):
            return [dict(r._mapping) for r in con.execute(text(sql), {**p, **extra})]

        resumo = q(f"""SELECT COUNT(*) AS chamadas, COALESCE(SUM(cost_usd),0) AS custo,
                       COALESCE(SUM(total_tokens),0) AS tokens,
                       COUNT(DISTINCT run_id) AS execucoes,
                       MIN(occurred_at) AS ini, MAX(occurred_at) AS fim
                       FROM {ev} e WHERE {W}""")[0]
        por_dia = q(f"""SELECT e.occurred_date AS dia, e.feature AS k,
                        COALESCE(SUM(e.cost_usd),0) AS custo
                        FROM {ev} e WHERE {W} GROUP BY e.occurred_date, e.feature
                        ORDER BY e.occurred_date""")
        por_feature = q(f"""SELECT e.feature AS k, COUNT(*) AS chamadas,
                            COALESCE(SUM(e.cost_usd),0) AS custo
                            FROM {ev} e WHERE {W} GROUP BY e.feature ORDER BY custo DESC""")
        por_modelo = q(f"""SELECT e.model AS k, COUNT(*) AS chamadas,
                           COALESCE(SUM(e.total_tokens),0) AS tokens,
                           COALESCE(SUM(e.cost_usd),0) AS custo
                           FROM {ev} e WHERE {W} GROUP BY e.model ORDER BY custo DESC""")
        por_tenant = q(f"""SELECT t.tag_value AS k, COUNT(*) AS chamadas,
                           COALESCE(SUM(e.cost_usd),0) AS custo
                           FROM {ev} e JOIN {tg} t
                             ON t.event_id = e.event_id AND t.tag_key = :tk
                           WHERE {W} GROUP BY t.tag_value ORDER BY custo DESC""",
                       tk=tag_tenant)
        cobertura = q(f"""SELECT e.feature_source AS k, COUNT(*) AS n
                          FROM {ev} e WHERE {W} GROUP BY e.feature_source""")
        status = q(f"""SELECT e.status AS k, COUNT(*) AS n FROM {ev} e WHERE {W}
                       GROUP BY e.status""")
        sem_preco = q(f"""SELECT e.model AS k, COUNT(*) AS n FROM {ev} e
                          WHERE {W} AND e.priced = 0 GROUP BY e.model""")
        por_entidade = q(f"""SELECT COUNT(DISTINCT t.tag_value) AS unidades,
                             COALESCE(SUM(e.cost_usd),0) AS custo
                             FROM {ev} e JOIN {tg} t
                               ON t.event_id = e.event_id AND t.tag_key = 'entity_id'
                             WHERE {W}""")[0]
        servicos = q(f"""SELECT e.service AS k, COUNT(*) AS chamadas,
                         COALESCE(SUM(e.cost_usd),0) AS custo
                         FROM {ev} e WHERE {W} GROUP BY e.service ORDER BY custo DESC""")
    return {"dias": dias, "resumo": resumo, "por_dia": por_dia, "por_feature": por_feature,
            "por_modelo": por_modelo, "por_tenant": por_tenant, "cobertura": cobertura,
            "status": status, "sem_preco": sem_preco, "por_entidade": por_entidade,
            "servicos": servicos, "tag_tenant": tag_tenant}


def _topn(linhas: list[dict], n: int = MAX_SERIES) -> tuple[list[str], dict]:
    """Top N por custo; o resto vira 'Outros'. Nunca gera cor nova."""
    ordenado = sorted(linhas, key=lambda r: _d(r["custo"]), reverse=True)
    top = [str(r["k"]) for r in ordenado[:n]]
    resto = sum(_d(r["custo"]) for r in ordenado[n:])
    return top, {"Outros": resto} if resto > 0 else {}


def _fmt(v: Decimal, casas: int = 2) -> str:
    s = f"{v:,.{casas}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _fim_do_mes() -> str:
    h = dt.date.today()
    prox = dt.date(h.year + (h.month == 12), (h.month % 12) + 1, 1)
    return (prox - dt.timedelta(days=1)).strftime("%d/%m")


def _svg_area(por_dia, feats, cores, proj_por_dia: Decimal, dias_restantes: int) -> str:
    """Área empilhada acumulada + projeção tracejada. Uma escala, um eixo."""
    dias = sorted({str(r["dia"]) for r in por_dia})
    if not dias:
        return '<p class="vazio">Sem dados no período.</p>'
    acc = {f: Decimal(0) for f in feats}
    serie = {f: [] for f in feats}
    total_dia = []
    for d in dias:
        for f in feats:
            acc[f] += sum(_d(r["custo"]) for r in por_dia
                          if str(r["dia"]) == d and (str(r["k"]) == f or
                             (f == "Outros" and str(r["k"]) not in feats)))
            serie[f].append(acc[f])
        total_dia.append(sum(acc.values()))

    W, H, PL, PR, PT, PB = 900, 300, 62, 16, 16, 34
    proj_total = total_dia[-1] + proj_por_dia * dias_restantes
    ymax = float(max(proj_total, total_dia[-1])) or 1.0
    n = len(dias)
    npro = dias_restantes if dias_restantes > 0 else 0
    total_pts = n + npro
    def X(i): return PL + (W - PL - PR) * (i / max(total_pts - 1, 1))
    def Y(v): return H - PB - (H - PT - PB) * (float(v) / ymax)

    out = []
    # grade + eixo Y
    for t in range(5):
        v = ymax * t / 4
        y = Y(v)
        out.append(f'<line class="grid" x1="{PL}" y1="{y:.1f}" x2="{W-PR}" y2="{y:.1f}"/>')
        out.append(f'<text class="ax" x="{PL-8}" y="{y+4:.1f}" text-anchor="end">'
                   f'US$ {_fmt(Decimal(v))}</text>')
    # áreas empilhadas, de baixo para cima, com 2px de respiro entre faixas.
    #
    # Com UM único dia, um polígono de área é degenerado: largura zero, nada aparece,
    # e a legenda passa a nomear três séries que não estão em lugar nenhum da tela.
    # É exatamente a forma do primeiro dia em produção. Nesse caso vira coluna.
    base = [Decimal(0)] * n
    if n == 1:
        LARG = 46
        x = PL + 10 + LARG / 2          # encostada no eixo, inteira dentro da área útil
        for idx, f in enumerate(feats):
            topo = base[0] + serie[f][0]
            y0, y1 = Y(topo), Y(base[0])
            alt = max(y1 - y0 - 2, 1.0)          # 2px de respiro entre faixas
            out.append(f'<rect class="area" fill="{cores[idx]}" x="{x-LARG/2:.1f}" '
                       f'y="{y0:.1f}" width="{LARG}" height="{alt:.1f}" rx="2"/>')
            base = [topo]
    else:
        for idx, f in enumerate(feats):
            topo = [base[i] + serie[f][i] for i in range(n)]
            pts_top = " ".join(f"{X(i):.1f},{Y(topo[i]):.1f}" for i in range(n))
            pts_bot = " ".join(f"{X(i):.1f},{Y(base[i]):.1f}" for i in reversed(range(n)))
            out.append(f'<polygon class="area" fill="{cores[idx]}" points="{pts_top} {pts_bot}"/>')
            out.append(f'<polyline class="borda" points="{pts_top}"/>')
            base = topo
    # projeção
    if npro:
        y0 = Y(total_dia[-1])
        x1, y1 = X(total_pts - 1), Y(proj_total)
        x0 = (PL + 10 + 46) if n == 1 else X(n - 1)
        out.append(f'<line class="proj" x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}"/>')
        out.append(f'<circle class="pt" cx="{x1:.1f}" cy="{y1:.1f}" r="4"/>')
        # o ponto de projeção fica SEMPRE no topo da escala (proj_total == ymax), então
        # um rótulo acima dele colide com o rótulo do eixo. Vai abaixo da linha.
        # o eixo X só rotula o trecho com dado; sem a data do fim, o leitor não sabe
        # até quando a tracejada vai.
        fim_mes = _fim_do_mes()
        out.append(f'<text class="rot" x="{x1-6:.1f}" y="{y1+18:.1f}" text-anchor="end">'
                   f'projeção {fim_mes}: US$ {_fmt(proj_total)}</text>')
    # eixo X: primeiro, meio, último — sem repetir quando há poucos dias
    for i in sorted({0, n // 2, n - 1}):
        out.append(f'<text class="ax" x="{X(i) if n > 1 else (PL + 10 + 23):.1f}" '
                   f'y="{H-12}" text-anchor="middle">{dias[i][5:]}</text>')
    # camada de hover
    for i, d in enumerate(dias):
        cx = X(i) if n > 1 else (PL + 10 + 23)
        larg = 12 if n > 1 else 50
        out.append(f'<rect class="hit" x="{cx-larg/2:.1f}" y="{PT}" width="{larg}" '
                   f'height="{H-PT-PB}" data-t="{html.escape(d)} · US$ '
                   f'{_fmt(total_dia[i], 4)} acumulado"/>')
    return f'<svg viewBox="0 0 {W} {H}" class="chart" role="img">{"".join(out)}</svg>'


def _svg_barras(linhas, cores=None, rotulo="", limite=8) -> str:
    """Barras horizontais com rótulo direto — atende a regra de relevo do contraste."""
    dados = [(str(r["k"]), _d(r["custo"]), int(r.get("chamadas") or 0))
             for r in linhas[:limite]]
    if not dados:
        return '<p class="vazio">Sem dados.</p>'
    vmax = float(max(v for _, v, _ in dados)) or 1.0
    linhas_html = []
    for i, (k, v, c) in enumerate(dados):
        pct = 100 * float(v) / vmax
        cor = (cores[i % len(cores)] if cores else "var(--seq)")
        linhas_html.append(
            f'<div class="brow" data-t="{html.escape(k)} · {c} chamada(s)">'
            f'<span class="blabel" title="{html.escape(k)}">{html.escape(k)}</span>'
            f'<span class="btrack"><span class="bfill" style="width:{pct:.1f}%;'
            f'background:{cor}"></span></span>'
            f'<span class="bval">US$ {_fmt(v, 4)}</span></div>')
    return f'<div class="bars" aria-label="{html.escape(rotulo)}">{"".join(linhas_html)}</div>'


def _tabela(linhas, colunas) -> str:
    th = "".join(f"<th>{html.escape(c[1])}</th>" for c in colunas)
    tr = []
    for r in linhas:
        tds = []
        for chave, _ in colunas:
            v = r.get(chave)
            tds.append(f"<td>{html.escape(str(v if v is not None else '—'))}</td>")
        tr.append(f"<tr>{''.join(tds)}</tr>")
    return f"<table><thead><tr>{th}</tr></thead><tbody>{''.join(tr)}</tbody></table>"


def render(dados: dict, *, titulo: str = "Consumo de IA", orcamento: float | None = None) -> str:
    r = dados["resumo"]
    custo = _d(r["custo"])
    hoje = dt.date.today()
    dias_periodo = max(dados["dias"], 1)
    media_dia = custo / dias_periodo
    fim_mes = (hoje.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    restantes = max((fim_mes - hoje).days, 0)

    feats_top, outros = _topn(dados["por_feature"])
    feats = feats_top + (["Outros"] if outros else [])

    # --- alertas: ícone + rótulo, nunca cor sozinha ---
    alertas = []
    cob = {str(x["k"]): int(x["n"]) for x in dados["cobertura"]}
    tot_cob = sum(cob.values()) or 1
    bem = cob.get("explicit", 0) + cob.get("context", 0)
    pct_cob = 100 * bem / tot_cob
    alertas.append(("good" if pct_cob >= 90 else "warning" if pct_cob >= 60 else "serious",
                    "Cobertura da atribuição", f"{pct_cob:.0f}% com contexto explícito",
                    f"{cob.get('inferred',0)} inferido(s), {cob.get('unknown',0)} sem origem"))
    if dados["sem_preco"]:
        m = ", ".join(str(x["k"]) for x in dados["sem_preco"][:3])
        alertas.append(("serious", "Modelo sem preço",
                        f"{sum(int(x['n']) for x in dados['sem_preco'])} evento(s)",
                        f"custo NULL em: {m}"))
    else:
        alertas.append(("good", "Precificação", "todos os modelos precificados", ""))
    erros = sum(int(x["n"]) for x in dados["status"] if str(x["k"]) != "ok")
    alertas.append(("good" if erros == 0 else "critical", "Chamadas com erro",
                    f"{erros} de {r['chamadas']}",
                    "status error/partial" if erros else "nenhuma"))

    ent = dados["por_entidade"]
    unidades = int(ent["unidades"] or 0)
    por_unidade = (_d(ent["custo"]) / unidades) if unidades else None
    execucoes = int(r["execucoes"] or 0)
    por_execucao = (custo / execucoes) if execucoes else None

    def tiles():
        t = [("Custo total", f"US$ {_fmt(custo, 2)}", f"{dados['dias']} dias"),
             ("Média diária", f"US$ {_fmt(media_dia, 2)}", f"projeção do mês: US$ "
              f"{_fmt(custo + media_dia * restantes, 2)}"),
             ("Chamadas", f"{int(r['chamadas']):,}".replace(",", "."),
              f"{int(r['tokens']):,}".replace(",", ".") + " tokens")]
        if por_execucao is not None:
            t.append(("Custo por request", f"US$ {_fmt(por_execucao, 4)}",
                      f"{execucoes} execuç(ões)"))
        if por_unidade is not None:
            t.append(("Custo por entidade", f"US$ {_fmt(por_unidade, 4)}",
                      f"{unidades} unidade(s) distintas"))
        if orcamento:
            pct = 100 * float(custo) / orcamento
            t.append(("Orçamento", f"{pct:.0f}%", f"de US$ {_fmt(Decimal(orcamento), 2)}"))
        return "".join(
            f'<div class="tile"><div class="tl">{html.escape(a)}</div>'
            f'<div class="tv">{html.escape(b)}</div>'
            f'<div class="ts">{html.escape(c)}</div></div>' for a, b, c in t)

    legenda = "".join(
        f'<span class="lg"><i style="background:{SERIES_VAR[i % len(SERIES_VAR)]}"></i>'
        f'{html.escape(f)}</span>' for i, f in enumerate(feats_top)) + (
        f'<span class="lg"><i style="background:{OUTROS_VAR}"></i>Outros</span>' if outros else "")

    area = _svg_area(dados["por_dia"], feats,
                     SERIES_VAR[:len(feats_top)] + ([OUTROS_VAR] if outros else []),
                     media_dia, restantes)

    n_dias_com_dado = len({str(x["dia"]) for x in dados["por_dia"]})
    if n_dias_com_dado <= 1:
        sub_area = ("Um único dia com dado — sem série temporal ainda. A projeção "
                    "extrapola esse dia e vale pouco; ela fica confiável depois de "
                    "alguns dias.")
    else:
        sub_area = ("Empilhado. A linha tracejada projeta o fim do mês pela média "
                    f"diária dos {n_dias_com_dado} dias com dado.")

    tabela_feat = _tabela(
        [{"feature": x["k"], "chamadas": x["chamadas"], "custo": f"US$ {_fmt(_d(x['custo']),6)}"}
         for x in dados["por_feature"]],
        [("feature", "Feature"), ("chamadas", "Chamadas"), ("custo", "Custo")])
    tabela_mod = _tabela(
        [{"model": x["k"], "chamadas": x["chamadas"], "tokens": x["tokens"],
          "custo": f"US$ {_fmt(_d(x['custo']),6)}"} for x in dados["por_modelo"]],
        [("model", "Modelo"), ("chamadas", "Chamadas"), ("tokens", "Tokens"), ("custo", "Custo")])

    alerta_html = "".join(
        f'<div class="al {sev}"><span class="ico" aria-hidden="true">'
        f'{"✓" if sev=="good" else "!" if sev in ("warning","serious") else "×"}</span>'
        f'<div><div class="an">{html.escape(nome)}</div>'
        f'<div class="av">{html.escape(val)}</div>'
        f'<div class="ad">{html.escape(det)}</div></div></div>'
        for sev, nome, val, det in alertas)

    servicos_html = ""
    if len(dados["servicos"]) > 1:
        servicos_html = f"""<section class="card"><h2>Por projeto</h2>
          <p class="sub">Cada aplicação que emite eventos para este banco.</p>
          {_svg_barras(dados['servicos'], SERIES_LIGHT, 'custo por projeto')}</section>"""

    gerado = dt.datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC")
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(titulo)}</title>
<style>
:root{{--surface:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
--grid:#e1e0d9;--axis:#c3c2b7;--seq:#2a78d6;--good:#0ca30c;--warning:#fab219;
--serious:#ec835a;--critical:#d03b3b;--border:#e1e0d9;
--s0:#2a78d6;--s1:#eb6834;--s2:#1baf7a;--s3:#eda100;--s4:#e87ba4;--sx:#898781}}
@media (prefers-color-scheme:dark){{:root:where(:not([data-theme="light"])){{{_ESCURO}}}}}
html[data-theme="dark"]{{{_ESCURO}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--plane);color:var(--ink);
font:14px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
.wrap{{max-width:1180px;margin:0 auto;padding:28px 20px 56px;position:relative}}
#tema{{position:absolute;top:28px;right:20px;background:var(--surface);color:var(--ink2);
border:1px solid var(--border);border-radius:6px;padding:5px 11px;font-size:12px;
cursor:pointer;font-family:inherit}}
#tema:hover{{color:var(--ink)}}
h1{{font-size:22px;margin:0 0 2px}} h2{{font-size:15px;margin:0 0 2px}}
.sub{{color:var(--ink2);margin:0 0 16px;font-size:13px}}
.meta{{color:var(--muted);font-size:12px;margin-bottom:22px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:18px}}
.card,.tile{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px 18px}}
.tl{{color:var(--ink2);font-size:12px}} .tv{{font-size:26px;font-weight:600;margin:4px 0 2px;
font-variant-numeric:tabular-nums}} .ts{{color:var(--muted);font-size:12px}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}}
@media(max-width:820px){{.grid2{{grid-template-columns:1fr}}}}
.chart{{width:100%;height:auto;margin-top:8px}}
.grid{{stroke:var(--grid);stroke-width:1}} .ax{{fill:var(--muted);font-size:11px}}
.area{{fill-opacity:.9}} .borda{{fill:none;stroke:var(--surface);stroke-width:2}}
.proj{{stroke:var(--muted);stroke-width:2;stroke-dasharray:5 4}}
.pt{{fill:var(--muted);stroke:var(--surface);stroke-width:2}}
/* halo da cor da superfície: o rótulo cruza a linha tracejada e precisa continuar legível */
.rot{{fill:var(--ink2);font-size:11px;paint-order:stroke;stroke:var(--surface);
stroke-width:3px;stroke-linejoin:round}}
.hit{{fill:transparent}} .hit:hover{{fill:var(--ink);fill-opacity:.05}}
.legend{{display:flex;gap:14px;flex-wrap:wrap;margin-top:10px;font-size:12px;color:var(--ink2)}}
.lg{{display:flex;align-items:center;gap:6px}}
.lg i{{width:10px;height:10px;border-radius:3px;display:inline-block}}
.bars{{margin-top:6px}}
.brow{{display:grid;grid-template-columns:150px 1fr 96px;gap:10px;align-items:center;padding:5px 0}}
.blabel{{color:var(--ink2);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.btrack{{background:var(--grid);border-radius:4px;height:14px;overflow:hidden}}
.bfill{{display:block;height:100%;border-radius:0 4px 4px 0}}
.bval{{text-align:right;font-size:12px;font-variant-numeric:tabular-nums;color:var(--ink)}}
.alerts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin-top:14px}}
.al{{display:flex;gap:10px;background:var(--surface);border:1px solid var(--border);
border-radius:10px;padding:14px 16px}}
.ico{{width:20px;height:20px;border-radius:50%;display:grid;place-items:center;color:#fff;
font-size:12px;font-weight:700;flex:none}}
.al.good .ico{{background:var(--good)}} .al.warning .ico{{background:var(--warning);color:#0b0b0b}}
.al.serious .ico{{background:var(--serious)}} .al.critical .ico{{background:var(--critical)}}
.an{{font-size:12px;color:var(--ink2)}} .av{{font-weight:600}} .ad{{font-size:12px;color:var(--muted)}}
details{{margin-top:12px}} summary{{cursor:pointer;color:var(--ink2);font-size:13px}}
table{{width:100%;border-collapse:collapse;margin-top:10px;font-size:12px}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--border)}}
th{{color:var(--ink2);font-weight:600}} td{{font-variant-numeric:tabular-nums}}
.vazio{{color:var(--muted);padding:20px 0}}
#tt{{position:fixed;pointer-events:none;background:var(--ink);color:var(--surface);
padding:6px 9px;border-radius:6px;font-size:12px;opacity:0;transition:opacity .1s;z-index:9}}
</style></head><body><div class="wrap">
<button id="tema" type="button" aria-label="Alternar tema claro/escuro">tema</button>
<h1>{html.escape(titulo)}</h1>
<p class="sub">Consumo de IA nos últimos {dados['dias']} dias.</p>
<p class="meta">Gerado em {gerado} · fonte: tabela de eventos do tokenmeter · valores em USD</p>

<div class="tiles">{tiles()}</div>

<section class="card"><h2>Custo acumulado por feature</h2>
<p class="sub">{html.escape(sub_area)}</p>
{area}<div class="legend">{legenda}</div></section>

<div class="grid2">
<section class="card"><h2>Por feature</h2><p class="sub">Onde o dinheiro vai.</p>
{_svg_barras(dados['por_feature'], SERIES_VAR + [OUTROS_VAR], 'custo por feature')}
<details><summary>Ver como tabela</summary>{tabela_feat}</details></section>

<section class="card"><h2>Por modelo</h2>
<p class="sub">Nunca some tokens entre modelos — tokenizadores diferentes.</p>
{_svg_barras(dados['por_modelo'], SERIES_VAR + [OUTROS_VAR], 'custo por modelo')}
<details><summary>Ver como tabela</summary>{tabela_mod}</details></section>
</div>

<section class="card" style="margin-top:14px"><h2>Por {html.escape(dados['tag_tenant'])}</h2>
<p class="sub">Dimensão livre de atribuição.</p>
{_svg_barras(dados['por_tenant'], SERIES_VAR + [OUTROS_VAR], 'custo por tenant')}</section>

{servicos_html}

<h2 style="margin-top:24px">Saúde da medição</h2>
<p class="sub">O painel também mede a si mesmo.</p>
<div class="alerts">{alerta_html}</div>
</div><div id="tt"></div>
<script>
document.getElementById('tema').addEventListener('click',()=>{{
const r=document.documentElement;
const escuro=getComputedStyle(r).getPropertyValue('--surface').trim()==='#1a1a19';
r.dataset.theme=escuro?'light':'dark';}});
const tt=document.getElementById('tt');
document.addEventListener('mouseover',e=>{{const el=e.target.closest('[data-t]');
if(!el)return;tt.textContent=el.getAttribute('data-t');tt.style.opacity=1;}});
document.addEventListener('mousemove',e=>{{if(tt.style.opacity==='1'){{
tt.style.left=Math.min(e.clientX+14,innerWidth-tt.offsetWidth-8)+'px';
tt.style.top=(e.clientY+16)+'px';}}}});
document.addEventListener('mouseout',e=>{{if(e.target.closest('[data-t]'))tt.style.opacity=0;}});
</script></body></html>"""


def gerar(store, caminho: str, **kw) -> str:
    titulo = kw.pop("titulo", "Consumo de IA")
    orcamento = kw.pop("orcamento", None)
    dados = coletar(store, **kw)
    from pathlib import Path
    Path(caminho).write_text(render(dados, titulo=titulo, orcamento=orcamento),
                             encoding="utf-8")
    return caminho
