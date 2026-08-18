"""
Leitura do conteudo gerado de um Material (Biblioteca de Materiais).

Existe para que a rota do PROFESSOR (routes/materiais.py) e a do ALUNO
(routes/student_materiais.py) leiam o material exatamente da mesma forma.
Antes cada uma chamava storage_service direto, com regras ligeiramente
diferentes — e foi assim que o portal do aluno acabou suportando so dois dos
seis tipos existentes.

2026-08-17 — de onde vem o conteudo:
  1) `Material.conteudo_gerado` (banco) — FONTE DE VERDADE desde a migration 012.
  2) `storage/materiais/{id}.html|json` — FALLBACK para linhas gravadas antes
     dessa migration. O disco do servico web no Railway e efemero (nao ha
     volume montado, ver railway.json), entao esse arquivo pode simplesmente
     nao existir mais — e o motivo de a coluna ter sido criada.
"""
from __future__ import annotations

import json
from typing import Any, Optional, Tuple

from app.models.material import Material, TipoMaterial
from app.services.storage_service import storage_service

# Tipos cujo conteudo gerado e JSON estruturado; o resto e HTML.
TIPOS_JSON = (TipoMaterial.MAPA_MENTAL, TipoMaterial.GEOMETRIA)


def formato_conteudo(tipo: TipoMaterial) -> str:
    """'json' ou 'html' — como o frontend deve interpretar o conteudo."""
    return "json" if tipo in TIPOS_JSON else "html"


def ler_conteudo(material: Material) -> Tuple[str, Optional[Any]]:
    """Devolve (formato, conteudo). `conteudo` e None quando nao ha nada
    gravado nem no banco nem no storage."""
    formato = formato_conteudo(material.tipo)

    if material.conteudo_gerado:
        if formato == "json":
            try:
                return formato, json.loads(material.conteudo_gerado)
            except json.JSONDecodeError:
                # Linha corrompida: tenta o storage em vez de estourar 500.
                pass
        else:
            return formato, material.conteudo_gerado

    if formato == "json":
        return formato, storage_service.ler_json(material.id)
    return formato, storage_service.ler_html(material.id)
