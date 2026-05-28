"""Engine + sessões SQLModel/SQLAlchemy do gastometro.

Configuração via variáveis de ambiente (todas opcionais):

- `GASTOMETRO_DB_URL`: URL completa do SQLAlchemy. Quando definida,
  vence tudo. Exemplos:
    `sqlite:///dados/gastometro.db` (padrão local)
    `postgresql+psycopg://user:senha@host:5432/gastometro` (Fase 5)
- `GASTOMETRO_DADOS_DIR`: pasta onde o `.db` mora quando `_DB_URL` não
  estiver definida. Útil pra apontar pra uma pasta sincronizada com
  iCloud / Drive / Dropbox sem mover código.
- `GASTOMETRO_ECHO_SQL`: se `1`/`true`, imprime SQL no stdout
  (útil em debugging local; ruidoso em produção).

Carrega `.env` da raiz do projeto se python-dotenv estiver disponível
e o arquivo existir.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

RAIZ = Path(__file__).resolve().parent.parent

load_dotenv(RAIZ / ".env", override=False)


def _dir_dados() -> Path:
    """Pasta onde o banco vive quando usando SQLite local."""
    override = os.getenv("GASTOMETRO_DADOS_DIR")
    base = Path(override).expanduser().resolve() if override else RAIZ / "dados"
    base.mkdir(parents=True, exist_ok=True)
    return base


def url_padrao() -> str:
    """Resolve a URL final do banco, com defaults sensatos pra dev local."""
    explicita = os.getenv("GASTOMETRO_DB_URL")
    if explicita:
        return explicita
    db_path = _dir_dados() / "gastometro.db"
    return f"sqlite:///{db_path}"


def _echo() -> bool:
    return os.getenv("GASTOMETRO_ECHO_SQL", "").strip().lower() in {"1", "true", "yes"}


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Engine global cacheada — uma por processo.

    Habilita PRAGMA foreign_keys em SQLite (não é o default).
    Pra Postgres/outros, é no-op.
    """
    url = url_padrao()
    connect_args: dict = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    eng = create_engine(url, echo=_echo(), connect_args=connect_args)

    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _pragma_foreign_keys(dbapi_conn, _):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return eng


@contextmanager
def get_session() -> Iterator[Session]:
    """Context manager idiomático: commit no sucesso, rollback no erro."""
    with Session(get_engine()) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def resetar_engine_cache() -> None:
    """Força recriação da engine na próxima chamada. Útil em testes."""
    get_engine.cache_clear()


def garantir_schema() -> None:
    """Aplica `alembic upgrade head` programaticamente (idempotente).

    Útil pro usuário final que não conhece Alembic: rodar `gastometro`
    pela primeira vez cria o banco e aplica todas as migrations sem
    precisar lembrar de comandos extras. Em produção/CI, prefira o
    comando explícito (`alembic upgrade head`).
    """
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url_padrao())
    command.upgrade(cfg, "head")
