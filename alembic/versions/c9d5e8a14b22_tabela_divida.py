"""tabela divida

Revision ID: c9d5e8a14b22
Revises: a7f3c2e91b04
Create Date: 2026-09-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "c9d5e8a14b22"
down_revision: Union[str, Sequence[str], None] = "a7f3c2e91b04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "divida",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("tipo", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("credor", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("saldo", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("taxa_juros_aa", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column("indexador", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "sistema_amortizacao", sqlmodel.sql.sqltypes.AutoString(), nullable=False
        ),
        sa.Column("parcela_mensal", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("parcelas_totais", sa.Integer(), nullable=True),
        sa.Column("parcelas_pagas", sa.Integer(), nullable=True),
        sa.Column("dia_vencimento", sa.Integer(), nullable=True),
        sa.Column("data_contratacao", sa.Date(), nullable=True),
        sa.Column("data_fim_prevista", sa.Date(), nullable=True),
        sa.Column("pessoa_id", sa.Integer(), nullable=True),
        sa.Column("categoria_id", sa.Integer(), nullable=True),
        sa.Column("observacao", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["categoria_id"], ["categoria.id"]),
        sa.ForeignKeyConstraint(["pessoa_id"], ["pessoa.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("divida", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_divida_nome"), ["nome"], unique=False)
        batch_op.create_index(batch_op.f("ix_divida_tipo"), ["tipo"], unique=False)
        batch_op.create_index(batch_op.f("ix_divida_status"), ["status"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_divida_pessoa_id"), ["pessoa_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_divida_categoria_id"), ["categoria_id"], unique=False
        )


def downgrade() -> None:
    op.drop_table("divida")
