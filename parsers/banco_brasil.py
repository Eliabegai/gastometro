"""Parser de fatura Banco do Brasil (Ourocard).

Suporta o layout padrão das faturas Ourocard com linhas no formato:
    DD/MM   DESCRIÇÃO ...   VALOR R$

Caso o seu PDF tenha outro layout, envie um exemplo e adaptamos.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pdfplumber

from categorias import categorizar

from .base import (
    Fatura,
    FaturaMetadata,
    Transacao,
    detectar_titular,
    formatar_data,
    parse_valor_brl,
    referencia_pelo_vencimento,
)


NOME_BANCO = "Banco do Brasil"

RE_TRANSACAO = re.compile(
    r"""
    ^
    (?P<dia>\d{2})/(?P<mes>\d{2})
    \s+
    (?P<descricao>.+?)
    \s+
    (?P<valor>-?[\d.,]+)
    \s*$
    """,
    re.VERBOSE,
)


def detectar(texto: str) -> bool:
    """Reconhece se o PDF é uma fatura do Banco do Brasil."""
    indicadores = (
        "BANCO DO BRASIL",
        "OUROCARD",
        "Ourocard",
        "BB Cartões",
        "bb.com.br",
    )
    return any(ind in texto for ind in indicadores)


def extrair(caminho_pdf: Path) -> Fatura:
    """Lê o PDF da fatura do Banco do Brasil e devolve metadados + transações."""
    with pdfplumber.open(caminho_pdf) as pdf:
        texto_completo = "\n".join((p.extract_text() or "") for p in pdf.pages)

    metadata = _extrair_metadata(texto_completo)
    ano = _ano_do_vencimento(metadata.data_vencimento)
    transacoes = _extrair_transacoes(texto_completo, ano)

    return Fatura(metadata=metadata, transacoes=transacoes)


def _extrair_metadata(texto: str) -> FaturaMetadata:
    metadata = FaturaMetadata(banco=NOME_BANCO)

    m_venc = re.search(r"Vencimento[:\s]+(\d{2})/(\d{2})/(\d{4})", texto, re.IGNORECASE)
    if m_venc:
        metadata.data_vencimento = f"{m_venc.group(1)}/{m_venc.group(2)}/{m_venc.group(3)}"

    m_fech = re.search(r"Fechamento[:\s]+(\d{2})/(\d{2})/(\d{4})", texto, re.IGNORECASE)
    if m_fech:
        metadata.data_fechamento = f"{m_fech.group(1)}/{m_fech.group(2)}/{m_fech.group(3)}"

    m_total = re.search(r"Total\s+da\s+fatura[^\d-]*([\d.,]+)", texto, re.IGNORECASE)
    if not m_total:
        m_total = re.search(r"Valor\s+total[^\d-]*([\d.,]+)", texto, re.IGNORECASE)
    if m_total:
        valor = parse_valor_brl(m_total.group(1))
        if valor is not None:
            metadata.valor_total = valor

    metadata.titular = detectar_titular(texto)

    metadata.referencia_mes = referencia_pelo_vencimento(metadata.data_vencimento)
    return metadata


def _ano_do_vencimento(data_vencimento: str) -> int:
    m = re.match(r"\d{2}/\d{2}/(\d{4})", data_vencimento)
    if m:
        return int(m.group(1))
    return date.today().year


def _extrair_transacoes(texto: str, ano: int) -> list[Transacao]:
    transacoes: list[Transacao] = []
    em_lancamentos = False

    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        if re.search(r"LAN[ÇC]AMENTOS|Compras nacionais|Detalhamento da fatura", linha, re.IGNORECASE):
            em_lancamentos = True
            continue
        if re.search(r"Total\s+(da fatura|geral|nacional|internacional)", linha, re.IGNORECASE):
            em_lancamentos = False
            continue
        if not em_lancamentos:
            continue

        if any(termo in linha for termo in (
            "PAGAMENTO",
            "PAGTO",
            "ESTORNO",
            "SALDO ANTERIOR",
        )):
            continue

        m = RE_TRANSACAO.match(linha)
        if not m:
            continue

        descricao = m.group("descricao").strip()
        valor = parse_valor_brl(m.group("valor"))
        if valor is None or abs(valor) < 0.01:
            continue

        parcela = ""
        m_parc = re.search(r"\b(\d{1,2}/\d{1,2})\b", descricao)
        if m_parc and not re.fullmatch(r"\d{2}/\d{2}", descricao):
            parcela = m_parc.group(1)
            descricao = (descricao[: m_parc.start()] + descricao[m_parc.end():]).strip()

        data = formatar_data(m.group("dia"), m.group("mes"), ano)

        transacoes.append(
            Transacao(
                data=data,
                descricao=descricao,
                parcela=parcela,
                cidade="",
                valor=valor,
                categoria=categorizar(descricao),
            )
        )

    return transacoes
