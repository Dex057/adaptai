"""Check de cobertura: AST walk que impede o problema original de voltar.

Duas regras, quase zero falso positivo:
  1. instanciação de um client de provedor fora da allowlist
  2. import do SDK do provedor fora da allowlist

A ideia: o repositório tem UM ponto de construção de client. Aí "não esquecer de
instrumentar" deixa de ser disciplina e vira invariante que a máquina checa.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

CLIENT_NAMES = {
    "anthropic": {"Anthropic", "AsyncAnthropic", "AnthropicBedrock", "AnthropicVertex"},
    "openai": {"OpenAI", "AsyncOpenAI", "AzureOpenAI"},
}


@dataclass
class Finding:
    path: str
    line: int
    rule: str
    detail: str
    severity: str = "error"          # error = quebra o CI | warning = só informa

    def __str__(self) -> str:
        marca = "" if self.severity == "error" else " (aviso)"
        return f"{self.path}:{self.line}: [{self.rule}]{marca} {self.detail}"


def _module_name(path: Path, root: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = [p for p in rel.parts if p != "__init__"]
    return ".".join(parts)


def scan(root: str | Path, allowed_modules: list[str], providers: list[str] | None = None,
         exclude: list[str] | None = None) -> list[Finding]:
    root = Path(root).resolve()
    providers = providers or ["anthropic"]
    exclude = set(exclude or []) | {".venv", "venv", "node_modules", ".git", "__pycache__",
                                    "build", "dist", "tests", "test"}
    names = set()
    for p in providers:
        names |= CLIENT_NAMES.get(p, set())
    allowed = set(allowed_modules)
    out: list[Finding] = []

    for f in sorted(root.rglob("*.py")):
        if any(part in exclude for part in f.relative_to(root).parts):
            continue
        mod = _module_name(f, root)
        if mod in allowed or any(mod.startswith(a + ".") for a in allowed):
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        rel = str(f.relative_to(root))
        linhas = f.read_text(encoding="utf-8").splitlines()

        def liberado(lineno: int) -> bool:
            """Supressão inline: `# tokenmeter: allow` na mesma linha."""
            try:
                return "tokenmeter: allow" in linhas[lineno - 1]
            except IndexError:
                return False

        achados_arquivo: list[Finding] = []
        constroi_client = False

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                nm = fn.id if isinstance(fn, ast.Name) else (
                    fn.attr if isinstance(fn, ast.Attribute) else None)
                if nm in names:
                    constroi_client = True
                    if not liberado(node.lineno):
                        achados_arquivo.append(Finding(
                            rel, node.lineno, "client_outside_allowlist",
                            f"{nm}() construído fora de {sorted(allowed)} — essa chamada "
                            f"não passa pelo wrap() e não será medida"))

            elif isinstance(node, ast.ImportFrom):
                # `from anthropic import Anthropic` é erro; `from anthropic import APIError`
                # não é — importar o tipo de exceção não constrói client nenhum.
                if node.module and node.module.split(".")[0] in providers:
                    trazidos = {a.name for a in node.names}
                    se_client = trazidos & names
                    if se_client and not liberado(node.lineno):
                        achados_arquivo.append(Finding(
                            rel, node.lineno, "sdk_import_outside_allowlist",
                            f"from {node.module} import {', '.join(sorted(se_client))} "
                            f"fora de {sorted(allowed)}"))

            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] in providers and not liberado(node.lineno):
                        achados_arquivo.append(Finding(
                            rel, node.lineno, "sdk_module_import",
                            f"import {a.name} fora de {sorted(allowed)}",
                            severity="warning"))

        # `import anthropic` sozinho (sem construir client) é uso legítimo do SDK —
        # tipos de exceção, por exemplo. Só vira erro quando acompanha uma construção,
        # e nesse caso a própria construção já foi reportada como erro.
        for a in achados_arquivo:
            if a.rule == "sdk_module_import" and constroi_client:
                a.severity = "error"
        out += achados_arquivo
    return out
