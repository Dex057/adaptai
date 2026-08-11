#!/usr/bin/env python
"""
Reparo de double-encoding UTF-8 (2026-08-11)
============================================

SINTOMA
-------
Na UI aparecem "CiÃªncias", "HistÃ³ria", "LÃngua Portuguesa", "MatemÃ¡tica",
"EducaÃ§Ã£o FÃsica" — enquanto o texto estatico do React, na MESMA tela,
aparece correto.

DIAGNOSTICO
-----------
Isso prova que a corrupcao NAO e de renderizacao: e do dado gravado. Bytes
UTF-8 foram interpretados como Latin-1 e re-codificados em UTF-8 no momento do
INSERT (o script de importacao da BNCC leu o arquivo com a codificacao padrao
do SO — no Windows, cp1252).

    "ê"  correto  = C3AA
    "ê"  corrompido = C383C2AA   <- dois bytes viraram quatro

COMO USAR
---------
    # 1) Sempre comece pelo diagnostico (nao altera nada)
    python -m scripts.reparar_encoding --diagnosticar

    # 2) Simulacao: mostra o que MUDARIA, sem gravar
    python -m scripts.reparar_encoding --dry-run

    # 3) Aplicar (faca backup do banco antes)
    python -m scripts.reparar_encoding --aplicar

!!! ATENCAO !!!
A conversao NAO e idempotente: rodar duas vezes corrompe de novo. A protecao e
o filtro `WHERE col REGEXP 'Ã|Â'`, que so pega linhas ainda corrompidas — nao
remova esse filtro. E ainda assim: FACA BACKUP ANTES.

Recomendado: rode primeiro em staging, confira o resultado com --diagnosticar,
e so entao aplique em producao.
"""

import argparse
import sys

from sqlalchemy import text

from app.database import SessionLocal

# (tabela, [colunas de texto]) — acrescente aqui o que mais vier de importacao.
ALVOS = [
    ("curriculo_nacional", ["componente", "habilidade", "objeto_conhecimento", "unidade_tematica"]),
    ("materiais", ["titulo", "descricao", "materia"]),
    ("temas_redacao", ["titulo", "tema", "proposta", "area_tematica"]),
    ("students", ["name", "grade_level", "notes"]),
]

# Marcadores de mojibake. "Ã" e "Â" praticamente nunca aparecem sozinhos em
# texto pt-BR legitimo, entao servem como filtro seguro.
FILTRO_CORROMPIDO = "REGEXP 'Ã|Â'"

# Reinterpreta os bytes UTF-8 como Latin-1 e converte de volta corretamente.
def _expr_conversao(coluna: str) -> str:
    return (
        f"CONVERT(CAST(CONVERT({coluna} USING latin1) AS BINARY) USING utf8mb4)"
    )


def _colunas_existentes(db, tabela: str, colunas: list) -> list:
    """Ignora colunas que nao existem — o schema varia entre ambientes."""
    linhas = db.execute(
        text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
        ),
        {"t": tabela},
    ).fetchall()
    presentes = {r[0] for r in linhas}
    return [c for c in colunas if c in presentes]


def diagnosticar(db) -> int:
    print("\n=== CHARSET DA CONEXAO ===")
    for linha in db.execute(text("SHOW VARIABLES LIKE 'character_set%'")).fetchall():
        print(f"  {linha[0]:<28} {linha[1]}")

    print("\n=== COLUNAS FORA DE utf8mb4 ===")
    fora = db.execute(
        text(
            "SELECT TABLE_NAME, COLUMN_NAME, CHARACTER_SET_NAME, COLLATION_NAME "
            "FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND CHARACTER_SET_NAME IS NOT NULL "
            "AND CHARACTER_SET_NAME <> 'utf8mb4' ORDER BY TABLE_NAME"
        )
    ).fetchall()
    if not fora:
        print("  (nenhuma — schema OK)")
    for t, c, cs, col in fora:
        print(f"  {t}.{c}: {cs} / {col}")

    print("\n=== LINHAS COM MOJIBAKE ===")
    total = 0
    for tabela, colunas in ALVOS:
        cols = _colunas_existentes(db, tabela, colunas)
        if not cols:
            continue
        for coluna in cols:
            try:
                n = db.execute(
                    text(f"SELECT COUNT(*) FROM {tabela} WHERE {coluna} {FILTRO_CORROMPIDO}")
                ).scalar()
            except Exception as e:
                print(f"  {tabela}.{coluna}: nao verificavel ({type(e).__name__})")
                continue
            if n:
                total += n
                exemplo = db.execute(
                    text(
                        f"SELECT {coluna}, HEX({coluna}) FROM {tabela} "
                        f"WHERE {coluna} {FILTRO_CORROMPIDO} LIMIT 1"
                    )
                ).fetchone()
                print(f"  {tabela}.{coluna}: {n} linha(s)")
                if exemplo:
                    print(f"      exemplo: {exemplo[0]!r}")
    if total == 0:
        print("  (nenhuma — dados OK)")
    print(f"\nTOTAL DE LINHAS AFETADAS: {total}\n")
    return total


def reparar(db, aplicar: bool) -> int:
    total = 0
    for tabela, colunas in ALVOS:
        cols = _colunas_existentes(db, tabela, colunas)
        for coluna in cols:
            try:
                n = db.execute(
                    text(f"SELECT COUNT(*) FROM {tabela} WHERE {coluna} {FILTRO_CORROMPIDO}")
                ).scalar()
            except Exception:
                continue
            if not n:
                continue

            sql = (
                f"UPDATE {tabela} SET {coluna} = {_expr_conversao(coluna)} "
                f"WHERE {coluna} {FILTRO_CORROMPIDO}"
            )
            if aplicar:
                db.execute(text(sql))
                print(f"  [OK] {tabela}.{coluna}: {n} linha(s) reparada(s)")
            else:
                print(f"  [DRY] {tabela}.{coluna}: {n} linha(s) seriam reparadas")
                print(f"        {sql}")
            total += n

    if aplicar:
        db.commit()
        print("\nCOMMIT executado.")
    else:
        print("\nNada foi gravado (dry-run). Use --aplicar para efetivar.")
    return total


def main() -> int:
    p = argparse.ArgumentParser(description="Repara double-encoding UTF-8 no MySQL")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--diagnosticar", action="store_true", help="So relata, nao altera")
    g.add_argument("--dry-run", action="store_true", help="Mostra os UPDATEs sem executar")
    g.add_argument("--aplicar", action="store_true", help="Executa os UPDATEs (FACA BACKUP)")
    args = p.parse_args()

    db = SessionLocal()
    try:
        if args.diagnosticar:
            diagnosticar(db)
            return 0

        afetadas = diagnosticar(db)
        if afetadas == 0:
            print("Nada a reparar.")
            return 0

        if args.aplicar:
            print("!! Isto vai ALTERAR dados. Certifique-se de ter backup. !!")
            if input("Digite 'CONFIRMO' para continuar: ").strip() != "CONFIRMO":
                print("Abortado.")
                return 1

        reparar(db, aplicar=args.aplicar)

        if args.aplicar:
            print("\n=== VERIFICACAO POS-REPARO ===")
            diagnosticar(db)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
