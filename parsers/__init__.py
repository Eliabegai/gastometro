"""
Parsers de fatura por banco.

Para adicionar um novo banco:
    1. Crie um módulo em `parsers/seu_banco.py`.
    2. Implemente as funções `detectar(texto) -> bool` e
       `extrair(caminho_pdf) -> Fatura`.
    3. Registre o módulo em `PARSERS_DISPONIVEIS` abaixo.
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber

from .base import Fatura, FaturaMetadata, Transacao
from . import ailos, banco_brasil, nubank


PARSERS_DISPONIVEIS = (
    ailos,
    nubank,
    banco_brasil,
)


def detectar_banco(caminho_pdf: Path) -> str:
    """Retorna o nome do banco identificado, ou 'Desconhecido'."""
    texto = _ler_texto(caminho_pdf)
    parser = _escolher_parser(texto)
    return parser.NOME_BANCO if parser else "Desconhecido"


def extrair_fatura(caminho_pdf: Path) -> Fatura:
    """Detecta o banco e devolve a Fatura com metadados + transações."""
    texto = _ler_texto(caminho_pdf)
    parser = _escolher_parser(texto)
    if parser is None:
        raise ValueError(
            f"Não foi possível identificar o banco da fatura '{caminho_pdf.name}'. "
            "Bancos suportados hoje: Ailos, Nubank, Banco do Brasil."
        )
    return parser.extrair(caminho_pdf)


def _ler_texto(caminho_pdf: Path) -> str:
    with pdfplumber.open(caminho_pdf) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def _escolher_parser(texto: str):
    for modulo in PARSERS_DISPONIVEIS:
        if modulo.detectar(texto):
            return modulo
    return None


__all__ = [
    "Fatura",
    "FaturaMetadata",
    "Transacao",
    "detectar_banco",
    "extrair_fatura",
]
