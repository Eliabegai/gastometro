"""Camada de persistência: SQLite + SQLModel.

Pontos de entrada:
  - `db.engine`: cria engine + sessão a partir de `GASTOMETRO_DB_URL`
    (fallback: `sqlite:///dados/gastometro.db`).
  - `db.models`: tabelas (Pessoa, Conta, Categoria, Fatura, Lancamento,
    OverrideCategoria).
  - `db.repository`: operações de alto nível (upsert_fatura,
    upsert_lancamento, listar_lancamentos, etc.).
  - `db.backup`: snapshot rotacionado do arquivo .db antes de cada
    escrita (defesa em profundidade contra corrupção/perda).
  - `db.seed`: popula categorias iniciais a partir de `categorias.py`.
"""

from db.engine import get_engine, get_session
from db.models import (
    Categoria,
    Conta,
    EscopoCategoria,
    Fatura,
    Lancamento,
    OrcamentoMeta,
    OverrideCategoria,
    Pessoa,
)

__all__ = [
    "Categoria",
    "Conta",
    "EscopoCategoria",
    "Fatura",
    "Lancamento",
    "OrcamentoMeta",
    "OverrideCategoria",
    "Pessoa",
    "get_engine",
    "get_session",
]
