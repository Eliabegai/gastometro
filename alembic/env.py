"""Configuração do Alembic para o gastometro.

- URL do banco vem do `db.engine.url_padrao()` (respeitando
  `GASTOMETRO_DB_URL` / `GASTOMETRO_DADOS_DIR`), **não** do
  `sqlalchemy.url` do `alembic.ini`. Assim a mesma config funciona em
  dev local (SQLite), CI e Postgres no futuro.
- `target_metadata = SQLModel.metadata` ativa autogenerate.
- `render_as_batch=True` em SQLite torna ALTER TABLE viável (SQLite
  reconstrói tabelas atrás dos panos).
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

from alembic import context

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import db.models  # noqa: E402,F401  (registra tabelas no SQLModel.metadata)
from db.engine import url_padrao  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", url_padrao())

target_metadata = SQLModel.metadata


def _e_sqlite() -> bool:
    url = config.get_main_option("sqlalchemy.url") or ""
    return url.startswith("sqlite")


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_e_sqlite(),
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=_e_sqlite(),
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
