"""Baixa a planilha familiar do Google Sheets via link público.

Como configurar:
  1. No Google Sheets, abra a planilha → **Compartilhar** → mude o
     acesso pra "Qualquer pessoa com o link" (pode ser só
     visualização).
  2. Copie a URL da barra de endereços (formato
     `https://docs.google.com/spreadsheets/d/<ID>/edit#gid=...`).
  3. Use a URL aqui — o script extrai o `<ID>` e troca pelo endpoint
     de export `.../export?format=xlsx`, baixando o arquivo `.xlsx`.

A URL pode ser passada de 3 formas (ordem de prioridade):
  1. Argumento da função / `argv[1]`.
  2. Arquivo de cache `dados/planilha_url.txt` (escrito pela UI).
  3. Variável de ambiente `GASTOMETRO_PLANILHA_URL`.

Uso CLI:

    # 1ª vez (informa a URL):
    python -m imports.baixar_planilha_familiar "https://docs.google.com/spreadsheets/d/.../edit"

    # Depois (usa a URL salva):
    python -m imports.baixar_planilha_familiar

O arquivo baixado vai pra `dados/planilha_familiar_baixada.xlsx` (
fora do controle de versão). Em seguida, rode:

    python -m imports.importar_planilha_familiar dados/planilha_familiar_baixada.xlsx

Ou use o botão da página **Importar** no Streamlit (faz tudo num
clique).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen

RAIZ = Path(__file__).resolve().parent.parent
DADOS_DIR = RAIZ / "dados"
ARQUIVO_BAIXADO = DADOS_DIR / "planilha_familiar_baixada.xlsx"
ARQUIVO_URL_CACHE = DADOS_DIR / "planilha_url.txt"
ENV_URL = "GASTOMETRO_PLANILHA_URL"

# XLSX é um ZIP; os 4 primeiros bytes devem ser o magic number.
_XLSX_MAGIC = b"PK\x03\x04"
_TIMEOUT_DEFAULT = 30.0


def url_salva() -> str:
    """Lê a URL salva (UI > arquivo de cache > variável de ambiente)."""
    if ARQUIVO_URL_CACHE.exists():
        texto = ARQUIVO_URL_CACHE.read_text(encoding="utf-8").strip()
        if texto:
            return texto
    return os.environ.get(ENV_URL, "").strip()


def salvar_url(url: str) -> Path:
    """Persiste a URL pra próximos runs (CLI ou UI)."""
    DADOS_DIR.mkdir(parents=True, exist_ok=True)
    ARQUIVO_URL_CACHE.write_text(url.strip() + "\n", encoding="utf-8")
    return ARQUIVO_URL_CACHE


def normalizar_url(url: str) -> str:
    """Converte qualquer URL do Google Sheets pra `.../export?format=xlsx`.

    Aceita formatos:
      - `https://docs.google.com/spreadsheets/d/<ID>/edit#gid=...`
      - `https://docs.google.com/spreadsheets/d/<ID>/export?format=xlsx`
      - `https://docs.google.com/spreadsheets/d/e/<ID>/pubhtml`
    """
    url = url.strip()
    if not url:
        raise ValueError("URL vazia.")
    if "/export?" in url and "format=" in url:
        return url
    m = re.search(r"/spreadsheets/d/(?:e/)?([a-zA-Z0-9_-]+)", url)
    if not m:
        raise ValueError(
            f"Não consegui extrair o ID da planilha em {url!r}. "
            "A URL precisa ser de uma planilha do Google "
            "(`docs.google.com/spreadsheets/d/<ID>/...`)."
        )
    sheet_id = m.group(1)
    return (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    )


def baixar(
    url: str | None = None,
    destino: Path | None = None,
    *,
    timeout: float = _TIMEOUT_DEFAULT,
) -> Path:
    """Baixa a planilha e devolve o caminho local.

    - `url`: se omitido, lê de `url_salva()`.
    - `destino`: se omitido, usa `dados/planilha_familiar_baixada.xlsx`.

    Levanta `RuntimeError` se a URL não devolver um XLSX válido (caso
    típico: planilha não está pública).
    """
    url_efetiva = (url or url_salva()).strip()
    if not url_efetiva:
        raise RuntimeError(
            f"URL não informada e nenhuma URL salva (cache ou {ENV_URL})."
        )

    url_exp = normalizar_url(url_efetiva)
    destino = destino or ARQUIVO_BAIXADO
    destino.parent.mkdir(parents=True, exist_ok=True)

    req = Request(url_exp, headers={"User-Agent": "gastometro/1.0"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310
        status = getattr(resp, "status", 200)
        if status != 200:
            raise RuntimeError(f"GET {url_exp} devolveu HTTP {status}.")
        conteudo = resp.read()

    if not conteudo.startswith(_XLSX_MAGIC):
        raise RuntimeError(
            "A URL não devolveu um arquivo XLSX. Confira se a planilha está "
            "compartilhada como 'Qualquer pessoa com o link pode ver' (no "
            "Google Sheets: Compartilhar → mudar acesso)."
        )
    destino.write_bytes(conteudo)
    return destino


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    url = args[0] if args else None

    if url:
        salvar_url(url)

    try:
        destino = baixar(url)
    except (ValueError, RuntimeError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    print(f"Planilha baixada em: {destino}")
    print(
        "Para importar agora: "
        f"python -m imports.importar_planilha_familiar {destino}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
