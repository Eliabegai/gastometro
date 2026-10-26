"""Preferências simples do usuário, num JSON ao lado do banco.

Guarda só o que não justifica uma tabela nova (hoje: teto mensal do
cartão). Leitura e escrita são tolerantes a falhas: sem arquivo ou com
arquivo inválido, devolve o padrão.
"""

from __future__ import annotations

import json
from pathlib import Path

from db.engine import _dir_dados  # noqa: PLC2701

_ARQUIVO = "preferencias.json"
_CHAVE_TETO_CARTAO = "teto_cartao"


def _caminho() -> Path:
    return _dir_dados() / _ARQUIVO


def _ler() -> dict[str, object]:
    try:
        dados = json.loads(_caminho().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def teto_cartao() -> float | None:
    """Teto mensal do cartão (R$), ou `None` se não definido."""
    valor = _ler().get(_CHAVE_TETO_CARTAO)
    if isinstance(valor, int | float) and valor > 0:
        return float(valor)
    return None


def salvar_teto_cartao(valor: float | None) -> None:
    """Grava (ou remove, com `None`/0) o teto mensal do cartão."""
    dados = _ler()
    if valor and valor > 0:
        dados[_CHAVE_TETO_CARTAO] = round(float(valor), 2)
    else:
        dados.pop(_CHAVE_TETO_CARTAO, None)
    caminho = _caminho()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
