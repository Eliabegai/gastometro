"""Restaura `dados/gastometro.db` a partir de um arquivo SQLite externo.

Cenário típico: você usava o app num PC, copiou o `.db` via
`scp`/AirDrop/pen drive pro outro, e quer trocar o banco vazio recém
criado pelo que veio do PC antigo — sem perder nada.

O script:

1. Valida que o arquivo informado existe e parece um SQLite válido
   (header `SQLite format 3`).
2. Confere que a versão do schema é igual à que a aplicação espera
   (mesma `alembic head` registrada na tabela `alembic_version`) —
   evita restaurar um dump muito antigo que quebraria os parsers.
3. Faz `db.backup.fazer_backup(motivo="pre_restauracao")` antes de
   sobrescrever, pra não perder o estado atual.
4. Copia o arquivo pro destino canônico (`<dados>/gastometro.db`).
5. Aplica `alembic upgrade head` no banco recém-restaurado (no-op se
   já estiver atualizado; útil se o `.db` veio de versão um pouco
   anterior do app).

Uso:

    python -m scripts.restaurar_banco /caminho/origem.db
    python -m scripts.restaurar_banco /caminho/origem.db --sem-checagem  # pula validação
    python -m scripts.restaurar_banco /caminho/origem.db --destino /outro/lugar.db

Saída zero em sucesso, !=0 em erro (com mensagem no stderr).
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

from db.backup import fazer_backup
from db.engine import garantir_schema, url_padrao

_SQLITE_MAGIC = b"SQLite format 3\x00"


def _caminho_destino_padrao() -> Path:
    """Resolve o `.db` apontado por `GASTOMETRO_DADOS_DIR`/`GASTOMETRO_DB_URL`."""
    url = url_padrao()
    if not url.startswith("sqlite"):
        raise RuntimeError(
            f"GASTOMETRO_DB_URL aponta pra {url}, que não é SQLite. "
            "Restaurar só faz sentido pra arquivos SQLite locais — "
            "pra Postgres/outros, use as ferramentas nativas do banco."
        )
    # `sqlite:///<path>` → tira o prefixo
    return Path(url.replace("sqlite:///", "", 1))


def _eh_sqlite_valido(caminho: Path) -> bool:
    """Confirma magic bytes de SQLite."""
    if not caminho.exists() or not caminho.is_file():
        return False
    try:
        with caminho.open("rb") as fh:
            cabecalho = fh.read(16)
    except OSError:
        return False
    return cabecalho == _SQLITE_MAGIC


def _ler_alembic_version(caminho: Path) -> str | None:
    """Devolve a `version_num` da `alembic_version` ou `None`."""
    try:
        conn = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        return None
    try:
        cur = conn.execute("SELECT version_num FROM alembic_version LIMIT 1")
        linha = cur.fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
    return linha[0] if linha else None


def restaurar(
    origem: Path,
    destino: Path | None = None,
    *,
    pular_validacao: bool = False,
    aplicar_migration: bool = True,
) -> Path:
    """Restaura `origem` pra `destino` (default = banco canônico do app).

    Devolve o `Path` final escrito. Levanta `FileNotFoundError`,
    `ValueError` ou `RuntimeError` em cenários impeditivos — o caller
    (CLI ou outro script) decide como reagir.

    `aplicar_migration=False` pula o `alembic upgrade head` no fim —
    use só se a origem **não** for um SQLite que o Alembic consiga
    abrir (geralmente combinado com `pular_validacao=True`).
    """
    origem = Path(origem).expanduser().resolve()
    if not origem.exists():
        raise FileNotFoundError(f"Arquivo de origem não existe: {origem}")

    destino = (
        Path(destino).expanduser().resolve()
        if destino is not None
        else _caminho_destino_padrao()
    )

    if not pular_validacao and not _eh_sqlite_valido(origem):
        raise ValueError(
            f"{origem} não parece ser um arquivo SQLite válido "
            "(magic bytes não conferem). Use --sem-checagem pra forçar."
        )

    # Backup do que existe atualmente (se existir).
    if destino.exists():
        fazer_backup(motivo="pre_restauracao")

    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origem, destino)

    # Roda Alembic upgrade no banco restaurado — no-op se já está na
    # head, ou migra automaticamente se veio de uma versão mais antiga.
    if aplicar_migration:
        garantir_schema()

    return destino


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Restaura o banco SQLite do gastometro a partir de outro arquivo.",
    )
    parser.add_argument(
        "origem",
        type=Path,
        help="Caminho do `.db` SQLite que será copiado pra dentro do projeto.",
    )
    parser.add_argument(
        "--destino",
        type=Path,
        default=None,
        help="Sobrescreve o caminho de destino (default: banco canônico do app).",
    )
    parser.add_argument(
        "--sem-checagem",
        action="store_true",
        dest="pular_validacao",
        help="Pula a verificação de magic bytes (use só se tem certeza do arquivo).",
    )
    parser.add_argument(
        "--sem-migration",
        action="store_true",
        dest="sem_migration",
        help=(
            "Não roda `alembic upgrade head` no banco restaurado. Útil "
            "quando combinado com --sem-checagem em arquivos que o Alembic "
            "não consegue abrir."
        ),
    )
    args = parser.parse_args(argv)

    try:
        destino = restaurar(
            args.origem,
            destino=args.destino,
            pular_validacao=args.pular_validacao,
            aplicar_migration=not args.sem_migration,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    versao = _ler_alembic_version(destino) or "(sem registro alembic)"
    print(f"Banco restaurado em: {destino}")
    print(f"Versão do schema: {versao}")
    print("Pronto. Suba o app: streamlit run app/streamlit_app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
