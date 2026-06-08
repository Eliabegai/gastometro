"""Configuração do pytest.

Adiciona a raiz do projeto ao `sys.path` para permitir importar
`categorias`, `extrator` e `parsers` direto, sem precisar instalar o
pacote. Também isola cada teste do `categorias_usuario.json` do
usuário (overrides locais), apontando o módulo para um JSON temporário
durante a execução.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolar_categorias_usuario(tmp_path, monkeypatch):
    """Cada teste roda com um `categorias_usuario.json` vazio em diretório
    temporário, sem tocar no arquivo real do usuário."""
    import categorias

    fake = tmp_path / "categorias_usuario.json"
    monkeypatch.setattr(categorias, "CATEGORIAS_USUARIO_ARQUIVO", fake)
    categorias._regras_compiladas.cache_clear()
    categorias._carregar_categorias_usuario.cache_clear()
    yield
    categorias._regras_compiladas.cache_clear()
    categorias._carregar_categorias_usuario.cache_clear()


@pytest.fixture
def banco_temporario(tmp_path, monkeypatch):
    """Aponta `GASTOMETRO_DB_URL` pra um SQLite efêmero por teste.

    Reseta o cache da engine antes e depois, roda `seed_inicial()` pra
    aplicar migrations e popular tabelas básicas. Cada teste fica
    completamente isolado — não toca o `dados/gastometro.db` real.

    Yields o caminho do `.db` (útil pra testes que validam o arquivo).
    """
    db_path = tmp_path / "gastometro_test.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("GASTOMETRO_DB_URL", db_url)
    monkeypatch.setenv("GASTOMETRO_DADOS_DIR", str(tmp_path))

    from db import engine as db_engine

    db_engine.resetar_engine_cache()

    from db.seed import seed_inicial

    seed_inicial()

    yield db_path

    db_engine.resetar_engine_cache()
