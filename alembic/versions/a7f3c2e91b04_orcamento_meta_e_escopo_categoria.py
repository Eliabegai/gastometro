"""orcamento_meta e escopo_categoria

Revision ID: a7f3c2e91b04
Revises: 418069adc183
Create Date: 2026-07-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "a7f3c2e91b04"
down_revision: Union[str, Sequence[str], None] = "418069adc183"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "escopo_categoria",
        sa.Column("categoria_id", sa.Integer(), nullable=False),
        sa.Column("escopo", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["categoria_id"], ["categoria.id"]),
        sa.PrimaryKeyConstraint("categoria_id"),
    )
    with op.batch_alter_table("escopo_categoria", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_escopo_categoria_escopo"), ["escopo"], unique=False
        )

    op.create_table(
        "orcamento_meta",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("referencia_mes", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("escopo", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("pessoa_id", sa.Integer(), nullable=True),
        sa.Column("categoria_id", sa.Integer(), nullable=True),
        sa.Column("valor_limite", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["categoria_id"], ["categoria.id"]),
        sa.ForeignKeyConstraint(["pessoa_id"], ["pessoa.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("orcamento_meta", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_orcamento_meta_referencia_mes"), ["referencia_mes"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_orcamento_meta_escopo"), ["escopo"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_orcamento_meta_pessoa_id"), ["pessoa_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_orcamento_meta_categoria_id"), ["categoria_id"], unique=False
        )


def downgrade() -> None:
    op.drop_table("orcamento_meta")
    op.drop_table("escopo_categoria")
