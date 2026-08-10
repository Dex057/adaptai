"""Confere os IDs de modelo do repositório contra a realidade.

Responde três perguntas que costumam ficar sem dono:

  1. Que IDs de modelo existem hardcoded no código?
  2. Algum deles foi APOSENTADO pelo provedor? (uma chamada a modelo aposentado falha,
     e se aquele ponto não tiver tracking, falha em silêncio por meses)
  3. Algum deles está fora da tabela de preços? (evento grava, mas com custo NULL)

A verificação (2) precisa da API do provedor — é a única fonte que não envelhece. As
outras duas rodam offline.
"""
from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

# IDs de modelo de qualquer provedor conhecido
MODELO_RE = re.compile(r"^(claude|gpt|gemini|o[134])[-\w.]*$", re.I)
IGNORAR = {".git", ".venv", "venv", "env", "node_modules", "__pycache__", "build",
           "dist", ".mypy_cache", ".pytest_cache", ".ruff_cache"}


@dataclass
class Ocorrencia:
    path: str
    line: int
    model: str
    contexto: str            # "chamada" | "atribuicao" | "config" | "literal"

    def __str__(self) -> str:
        return f"{self.path}:{self.line}  {self.model}  ({self.contexto})"


@dataclass
class Relatorio:
    ocorrencias: list[Ocorrencia] = field(default_factory=list)
    aposentados: dict[str, list[Ocorrencia]] = field(default_factory=dict)
    sem_preco: dict[str, list[Ocorrencia]] = field(default_factory=dict)
    vivos: list[str] = field(default_factory=list)
    consultou_api: bool = False


def _varrer(root: Path) -> list[Ocorrencia]:
    out: list[Ocorrencia] = []
    for f in sorted(root.rglob("*.py")):
        if any(p in IGNORAR for p in f.relative_to(root).parts):
            continue
        try:
            arv = ast.parse(f.read_text(encoding="utf-8", errors="ignore"), filename=str(f))
        except SyntaxError:
            continue
        rel = str(f.relative_to(root))
        for node in ast.walk(arv):
            # model="..." numa chamada — o caso que quebra em runtime
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if not kw.arg or not isinstance(kw.value, ast.Constant):
                        continue
                    v = kw.value.value
                    if not isinstance(v, str) or not MODELO_RE.match(v):
                        continue
                    k = kw.arg.lower()
                    if k in ("model", "model_name", "modelo"):
                        ctx = "chamada"          # vira requisição de verdade
                    elif "model" in k or "modelo" in k:
                        ctx = "config"           # coluna/preferência guardada
                    else:
                        continue
                    out.append(Ocorrencia(rel, node.lineno, v, ctx))
            # MODELO = "..." / self.model = "..." — vira chamada mais tarde.
            # AnnAssign entra junto: `campo: Optional[str] = "claude-..."` (default de
            # campo Pydantic) é AnnAssign, não Assign. Sem isso o scanner passava por
            # cima de todo default de schema — foi assim que ele deu "0 referências"
            # num repositório que tinha duas.
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                alvo = node.targets[0] if isinstance(node, ast.Assign) else node.target
                nome = (alvo.id if isinstance(alvo, ast.Name)
                        else alvo.attr if isinstance(alvo, ast.Attribute) else "")
                parece_campo_de_modelo = "model" in nome.lower() or "modelo" in nome.lower()
                valor = node.value
                if valor is None:                     # `campo: str` sem atribuição
                    continue
                if isinstance(valor, ast.Constant) and isinstance(valor.value, str) \
                        and MODELO_RE.match(valor.value):
                    ctx = "atribuicao" if parece_campo_de_modelo else "literal"
                    out.append(Ocorrencia(rel, node.lineno, valor.value, ctx))
                elif parece_campo_de_modelo:
                    # Literal enterrado no valor, quando o NOME do alvo já diz que é
                    # campo de modelo: Column(String(100), default="claude-..."),
                    # Field(default="claude-..."), etc. A regra de `Call` acima não
                    # pega porque a keyword se chama `default`, não `model`.
                    for sub in ast.walk(valor):
                        if isinstance(sub, ast.Constant) and isinstance(sub.value, str) \
                                and MODELO_RE.match(sub.value):
                            out.append(Ocorrencia(rel, getattr(sub, "lineno", node.lineno),
                                                  sub.value, "config"))

    # Dedup: um mesmo literal pode ser visto pela regra de Call e pela de Assign.
    # Precedência pelo quanto dói: chamada quebra em runtime, config é latente.
    peso = {"chamada": 0, "atribuicao": 1, "config": 2, "literal": 3}
    melhor: dict[tuple, Ocorrencia] = {}
    for o in out:
        chave = (o.path, o.line, o.model)
        if chave not in melhor or peso[o.contexto] < peso[melhor[chave].contexto]:
            melhor[chave] = o
    return sorted(melhor.values(), key=lambda o: (o.path, o.line))


def _modelos_vivos(api_key: str | None = None) -> list[str] | None:
    """Consulta a API do provedor. None se não der para consultar."""
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        # A própria lib precisa de um client aqui, e ele NÃO deve ser instrumentado:
        # listar modelos não consome token e não é uso de feature nenhuma. As duas
        # supressões abaixo evitam que o `check` acuse o próprio tokenmeter no CI do
        # projeto hospedeiro (a pasta da lib fica dentro do repo em muitas adoções).
        from anthropic import Anthropic  # tokenmeter: allow
        cli = Anthropic(api_key=key)  # tokenmeter: allow
        return [m.id for m in cli.models.list(limit=100).data]
    except Exception:
        return None


def verificar(root: str | Path, *, pricebook=None, live: bool = True,
              api_key: str | None = None) -> Relatorio:
    root = Path(root).resolve()
    rep = Relatorio(ocorrencias=_varrer(root))

    vivos = _modelos_vivos(api_key) if live else None
    if vivos is not None:
        rep.consultou_api = True
        rep.vivos = vivos
        for o in rep.ocorrencias:
            # só acusa se o provedor for reconhecível pelo prefixo do id
            if o.model.lower().startswith("claude") and o.model not in vivos:
                rep.aposentados.setdefault(o.model, []).append(o)

    if pricebook is not None:
        import datetime as dt
        agora = dt.datetime.utcnow()
        for o in rep.ocorrencias:
            if pricebook.resolve("anthropic", o.model, agora) is None:
                rep.sem_preco.setdefault(o.model, []).append(o)

    return rep
