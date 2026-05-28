"""Backup rotacionado do arquivo SQLite.

Estratégia: antes de cada escrita relevante (importação de fatura,
sincronização de planilha, edição via UI), copia `dados/gastometro.db`
para `dados/backups/gastometro_YYYY-MM-DD_HHMMSS.db` e mantém apenas os
últimos N arquivos (default 30).

Não-SQLite: a função é no-op silenciosa, mas registra um aviso em
debug. Pra Postgres/outros, use `pg_dump` agendado fora do app.
"""

from __future__ import annotations

import contextlib
import os
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from db.engine import url_padrao

FORMATO_TIMESTAMP = "%Y-%m-%d_%H%M%S"
PREFIXO_BACKUP = "gastometro_"
SUFIXO_BACKUP = ".db"


def _caminho_sqlite() -> Path | None:
    """Extrai o path do arquivo .db da URL atual, ou `None` se não for SQLite."""
    url = url_padrao()
    if not url.startswith("sqlite"):
        return None
    parsed = urlparse(url)
    raw = parsed.path
    if not raw:
        return None
    if raw.startswith("/") and len(raw) > 3 and raw[2] == ":":
        raw = raw[1:]
    return Path(raw).expanduser().resolve()


def _quantidade_a_manter() -> int:
    """Lê `GASTOMETRO_BACKUPS_KEEP` (default 30, mínimo 1)."""
    raw = os.getenv("GASTOMETRO_BACKUPS_KEEP", "30").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 30
    return max(1, n)


def pasta_backups() -> Path:
    """Pasta `dados/backups/`. Cria se não existir."""
    db = _caminho_sqlite()
    base = db.parent if db is not None else Path.cwd() / "dados"
    pasta = base / "backups"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def fazer_backup(*, motivo: str = "") -> Path | None:
    """Copia o `.db` atual pra `backups/` com timestamp; rotaciona.

    Devolve o path do backup criado ou `None` se não houver banco
    (primeira execução) ou se a URL não for SQLite. Idempotente: dois
    backups no mesmo segundo são desambiguados pelo sufixo de motivo
    (quando passado) ou simplesmente sobrescritos.
    """
    origem = _caminho_sqlite()
    if origem is None or not origem.exists():
        return None

    timestamp = datetime.now().strftime(FORMATO_TIMESTAMP)
    sufixo_motivo = f"_{motivo}" if motivo else ""
    destino = pasta_backups() / f"{PREFIXO_BACKUP}{timestamp}{sufixo_motivo}{SUFIXO_BACKUP}"
    shutil.copy2(origem, destino)
    rotacionar(_quantidade_a_manter())
    return destino


def rotacionar(manter: int) -> list[Path]:
    """Apaga backups antigos, mantendo apenas os `manter` mais recentes.

    Devolve a lista dos arquivos removidos (pra logging/debug).
    """
    backups = sorted(
        (
            p
            for p in pasta_backups().glob(f"{PREFIXO_BACKUP}*{SUFIXO_BACKUP}")
            if p.is_file()
        ),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    a_remover = backups[manter:]
    for p in a_remover:
        with contextlib.suppress(OSError):
            p.unlink()
    return a_remover
