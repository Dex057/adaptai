"""denormalize escola_id onto provas/materiais/relatorios/peis

Tarefa 1.0 do ROTEIRO_REMEDIACAO_ADAPTAI_COWORK. Adiciona a coluna escola_id
(FK escolas.id, nullable, indexada) nas 4 tabelas de conteudo e faz o backfill a
partir do pai:

    provas.escola_id, materiais.escola_id  <- users.escola_id    via criado_por_id
    relatorios.escola_id, peis.escola_id   <- students.escola_id  via student_id

PRIMEIRA migration do projeto (alembic/versions/ estava vazio): down_revision = None.
Se mais tarde for gerado o baseline_schema (ver alembic/README_ADOCAO.md), ajuste
este down_revision para a revisao do baseline para manter um unico head.

O backfill usa UPDATE com subquery correlacionada (portavel MySQL/SQLite) e e
idempotente: so toca linhas com escola_id IS NULL. Linhas legadas sem pai
resolvivel ficam NULL de proposito (grandfather) -- por isso a coluna fica nullable
nesta fase.

Revision ID: a1f0escoladenorm
Revises:
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a1f0escoladenorm"
down_revision = None
branch_labels = None
depends_on = None


# (tabela, coluna_fk_para_o_pai, tabela_pai) -- ordem do backfill
_TABELAS = [
    ("provas", "criado_por_id", "users"),
    ("materiais", "criado_por_id", "users"),
    ("relatorios", "student_id", "students"),
    ("peis", "student_id", "students"),
]

# Sentencas de backfill (subquery correlacionada, portavel). Exportadas para o teste
# rodar exatamente o mesmo SQL e provar a corretude sem drift.
BACKFILL_SQL = [
    (
        f"UPDATE {tabela} SET escola_id = "
        f"(SELECT escola_id FROM {pai} WHERE {pai}.id = {tabela}.{fk}) "
        f"WHERE escola_id IS NULL"
    )
    for tabela, fk, pai in _TABELAS
]


def upgrade() -> None:
    for tabela, _fk, _pai in _TABELAS:
        op.add_column(tabela, sa.Column("escola_id", sa.Integer(), nullable=True))
        op.create_index(f"ix_{tabela}_escola_id", tabela, ["escola_id"])
        op.create_foreign_key(
            f"fk_{tabela}_escola_id", tabela, "escolas", ["escola_id"], ["id"]
        )
    # backfill apos criar todas as colunas
    for stmt in BACKFILL_SQL:
        op.execute(stmt)


def downgrade() -> None:
    for tabela, _fk, _pai in _TABELAS:
        op.drop_constraint(f"fk_{tabela}_escola_id", tabela, type_="foreignkey")
        op.drop_index(f"ix_{tabela}_escola_id", table_name=tabela)
        op.drop_column(tabela, "escola_id")
