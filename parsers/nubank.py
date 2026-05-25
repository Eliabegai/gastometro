"""Parser de fatura Nubank."""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from categorias import categorizar

from .base import (
    MESES_PT,
    Fatura,
    FaturaMetadata,
    Transacao,
    detectar_titular,
    formatar_data,
    inferir_ano_transacao,
    parse_valor_brl,
    referencia_pelo_vencimento,
)

NOME_BANCO = "Nubank"

RE_TRANSACAO = re.compile(
    r"""
    ^
    (?P<dia>\d{2})\s+
    (?P<mes>[A-Z]{3})\s+
    (?:••••\s*\d{4}\s+)?
    (?P<descricao>.+?)
    \s+
    (?:(?P<sinal>[-\u2212])\s*)?
    (?:R\$\s*)?
    (?P<valor>\d[\d.,]*)
    \s*$
    """,
    re.VERBOSE,
)

RE_PARCELA = re.compile(
    r"-\s*(?:Parcela\s+)?(\d{1,2}/\d{1,2})",
    re.IGNORECASE,
)


def detectar(texto: str) -> bool:
    """Reconhece se o PDF é uma fatura Nubank."""
    indicadores = (
        "Nu Pagamentos",
        "Nubank",
        "TRANSAÇÕES DE",
        "fatura de",
    )
    hits = sum(1 for ind in indicadores if ind in texto)
    return hits >= 2 or "Nu Pagamentos" in texto


def extrair(caminho_pdf: Path) -> Fatura:
    """Lê o PDF da fatura Nubank e devolve metadados + transações."""
    with pdfplumber.open(caminho_pdf) as pdf:
        texto_completo = "\n".join((p.extract_text() or "") for p in pdf.pages)

    metadata = _extrair_metadata(texto_completo)
    transacoes = _extrair_transacoes(texto_completo, metadata.data_vencimento)

    return Fatura(metadata=metadata, transacoes=transacoes)


def _extrair_metadata(texto: str) -> FaturaMetadata:
    metadata = FaturaMetadata(banco=NOME_BANCO)

    m_venc = re.search(r"vencimento[:\s]+(\d{1,2})\s+([A-Z]{3})\s+(\d{4})", texto, re.IGNORECASE)
    if not m_venc:
        m_venc = re.search(r"FATURA\s+(\d{1,2})\s+([A-Z]{3})\s+(\d{4})", texto)
    if m_venc:
        metadata.data_vencimento = formatar_data(
            m_venc.group(1), m_venc.group(2), int(m_venc.group(3))
        )

    m_fech = re.search(r"Fechamento da próxima fatura\s+(\d{1,2})\s+([A-Z]{3})\s+(\d{4})", texto)
    if m_fech:
        dia, mes, ano = m_fech.group(1), m_fech.group(2), int(m_fech.group(3))
        mes_num = MESES_PT.get(mes.upper())
        if mes_num:
            mes_anterior = mes_num - 1 if mes_num > 1 else 12
            ano_fech = ano if mes_num > 1 else ano - 1
            metadata.data_fechamento = formatar_data(dia, mes_anterior, ano_fech)
    if not metadata.data_fechamento:
        m_emit = re.search(r"EMISSÃO E ENVIO\s+(\d{1,2})\s+([A-Z]{3})\s+(\d{4})", texto)
        if m_emit:
            metadata.data_fechamento = formatar_data(
                m_emit.group(1), m_emit.group(2), int(m_emit.group(3))
            )

    m_total = re.search(r"Total de compras[^\n]*?R\$\s*([\d.,]+)", texto)
    if not m_total:
        m_total = re.search(r"no valor de\s*R\$\s*([\d.,]+)", texto)
    if not m_total:
        m_total = re.search(
            r"RESUMO DA FATURA[\s\S]*?Total a pagar\s+R\$\s*([\d.,]+)",
            texto,
        )
    if m_total:
        valor = parse_valor_brl(m_total.group(1))
        if valor is not None:
            metadata.valor_total = valor

    metadata.titular = detectar_titular(texto)
    if not metadata.titular:
        m_titular = re.search(r"Olá,\s*([^.\n]+?)[.\n]", texto)
        if m_titular:
            metadata.titular = m_titular.group(1).strip().title()

    metadata.referencia_mes = referencia_pelo_vencimento(metadata.data_vencimento)
    return metadata


LINHAS_DESCARTAR = (
    "TRANSAÇÕES DE",
    "Saldo restante",
    "Pagamento em",
    "Fatura anterior",
    "Pagamento recebido",
)


def _extrair_transacoes(texto: str, data_vencimento: str) -> list[Transacao]:
    """Varre o bloco `TRANSAÇÕES DE ...` e devolve a lista de transações.

    Suporta dois formatos:
      - Atual (a partir de meados/2024): `DD MMM •••• NNNN Descrição R$ X,XX`
      - Antigo (até meados/2024): `DD MMM Descrição [- X/Y] X,XX` (sem `R$`)

    Estornos individuais (`Estorno de "X"`) são marcados como valor
    negativo, refletindo o crédito recebido pelo titular.
    """
    inicio = re.search(r"TRANSAÇÕES DE.*", texto)
    if not inicio:
        return []
    bloco = texto[inicio.start():]
    bloco = re.split(
        r"Pagamentos e Financiamentos|Em cumprimento à regulação",
        bloco,
        maxsplit=1,
    )[0]

    transacoes: list[Transacao] = []
    for linha in bloco.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        if any(termo in linha for termo in LINHAS_DESCARTAR):
            continue

        m = RE_TRANSACAO.match(linha)
        if not m:
            continue
        mes_str = m.group("mes").upper()
        mes_num = MESES_PT.get(mes_str)
        if mes_num is None:
            continue

        descricao = m.group("descricao").strip()
        valor = parse_valor_brl(m.group("valor"))
        if valor is None or valor == 0:
            continue
        if m.group("sinal"):
            valor = -abs(valor)

        if descricao.upper().startswith("ESTORNO"):
            valor = -abs(valor)

        parcela = ""
        m_parc = RE_PARCELA.search(descricao)
        if m_parc:
            parcela = m_parc.group(1)
            descricao = (descricao[: m_parc.start()] + descricao[m_parc.end():]).strip()
            descricao = descricao.rstrip("-").strip()

        ano = inferir_ano_transacao(mes_num, data_vencimento, parcela)
        data = formatar_data(m.group("dia"), mes_str, ano)

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
