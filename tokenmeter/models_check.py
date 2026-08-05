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
    contexto: str            # "chamada" | "atribuicao" | "literal"

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
            # MODELO = "..." / self.model = "..." — vira chamada mais tarde
            elif isinstance(node, ast.Assign):
                if isinstance(node.value, ast.Constant) and \
                        isinstance(node.value.value, str) and MODELO_RE.match(node.value.value):
                    alvo = node.targets[0]
                    nome = (alvo.id if isinstance(alvo, ast.Name)
                            else alvo.attr if isinstance(alvo, ast.Attribute) else "")
                    ctx = "atribuicao" if "model" in nome.lower() or "modelo" in nome.lower() \
                        else "literal"
                    out.append(Ocorrencia(rel, node.lineno, node.value.value, ctx))
    return out


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
