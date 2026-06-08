"""Testes do `scripts.restaurar_banco` — migração one-shot do `.db`.

Cobre:
  - Validação dos magic bytes do SQLite.
  - Recusa de arquivos inválidos (com `--sem-checagem` força).
  - Cópia idempotente preservando dados originais e fazendo backup
    automático do banco anterior.
  - Erro claro quando a origem não existe.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import select

from db.engine import get_session
from db.models import Conta
from scripts import restaurar_banco as mod


def _criar_sqlite_falso(caminho: Path) -> None:
    """Grava bytes que NÃO começam com 'SQLite format 3'."""
    caminho.write_bytes(b"isso nao eh um sqlite, eh um xlsx\x00\x01")


def test_eh_sqlite_valido_aceita_banco_real(banco_temporario) -> None:
    """O `.db` criado pelo seed deve passar pela validação."""
    destino = mod._caminho_destino_padrao()
    assert destino.exists(), "fixture deveria ter criado o banco"
    assert mod._eh_sqlite_valido(destino) is True


def test_eh_sqlite_valido_rejeita_lixo(tmp_path: Path) -> None:
    falso = tmp_path / "falso.db"
    _criar_sqlite_falso(falso)
    assert mod._eh_sqlite_valido(falso) is False


def test_eh_sqlite_valido_arquivo_inexistente(tmp_path: Path) -> None:
    assert mod._eh_sqlite_valido(tmp_path / "nao_existe.db") is False


def test_restaurar_sobrescreve_e_aplica_alembic(
    banco_temporario, tmp_path: Path
) -> None:
    """Restaura um banco com dados próprios e confirma que o app passa
    a ler dele. Faz backup do banco atual antes."""

    # 1. Cria um arquivo `origem.db` cópia do banco vazio, modifica
    #    pra ter uma marca distinta ("Cartão Marciano").
    destino_canonico = mod._caminho_destino_padrao()
    origem = tmp_path / "origem.db"
    origem.write_bytes(destino_canonico.read_bytes())

    import sqlite3

    with sqlite3.connect(origem) as conn:
        conn.execute(
            "INSERT INTO conta (nome, tipo) VALUES ('Cartão Marciano', 'cartao_credito')"
        )
        conn.commit()

    # 2. Antes da restauração, o banco canônico NÃO tem essa conta.
    with get_session() as s:
        nomes = {c.nome for c in s.exec(select(Conta)).all()}
    assert "Cartão Marciano" not in nomes

    # 3. Reseta o cache da engine pra forçar re-leitura após `shutil.copy2`.
    from db.engine import resetar_engine_cache

    resetar_engine_cache()

    final = mod.restaurar(origem)
    assert final == destino_canonico

    # 4. Após restauração, o banco canônico passa a conter a marca.
    resetar_engine_cache()
    with get_session() as s:
        nomes_pos = {c.nome for c in s.exec(select(Conta)).all()}
    assert "Cartão Marciano" in nomes_pos

    # 5. Um backup foi criado (motivo=pre_restauracao).
    from db.backup import pasta_backups

    backups = list(pasta_backups().glob("gastometro_*pre_restauracao*.db"))
    assert backups, "esperava 1 backup com motivo pre_restauracao"


def test_restaurar_rejeita_arquivo_invalido(
    banco_temporario, tmp_path: Path
) -> None:
    """Sem `--sem-checagem`, um arquivo com header inválido é recusado."""
    falso = tmp_path / "fake.db"
    _criar_sqlite_falso(falso)

    with pytest.raises(ValueError, match="SQLite válido"):
        mod.restaurar(falso)


def test_restaurar_com_sem_checagem_forca(
    banco_temporario, tmp_path: Path
) -> None:
    """Com `pular_validacao=True` + `aplicar_migration=False`, mesmo um
    arquivo 'estranho' é copiado sem erro. Cenário de escape pra quando
    o usuário tem certeza absoluta da origem.
    """
    falso = tmp_path / "qualquer.bin"
    falso.write_bytes(b"qualquer coisa aqui")

    destino = mod._caminho_destino_padrao()
    final = mod.restaurar(
        falso, pular_validacao=True, aplicar_migration=False
    )
    assert final == destino
    assert destino.read_bytes() == b"qualquer coisa aqui"


def test_restaurar_falha_quando_origem_nao_existe(
    banco_temporario, tmp_path: Path
) -> None:
    with pytest.raises(FileNotFoundError, match="não existe"):
        mod.restaurar(tmp_path / "fantasma.db")


def test_main_imprime_versao_alembic(
    banco_temporario, tmp_path: Path, capsys
) -> None:
    """A CLI imprime a versão do schema após restaurar."""
    destino_canonico = mod._caminho_destino_padrao()
    origem = tmp_path / "origem.db"
    origem.write_bytes(destino_canonico.read_bytes())

    rc = mod.main([str(origem)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "Banco restaurado em" in out
    assert "Versão do schema" in out


def test_main_falha_origem_inexistente(
    banco_temporario, tmp_path: Path, capsys
) -> None:
    rc = mod.main([str(tmp_path / "nada.db")])
    err = capsys.readouterr().err
    assert rc == 1
    assert "não existe" in err
