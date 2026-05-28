"""Testes do `export.excel`: regerar planilha do banco preserva totais."""

from __future__ import annotations

import pandas as pd

from parsers.base import Fatura, FaturaMetadata, Transacao


def _fatura(banco: str, titular: str, arquivo: str) -> Fatura:
    return Fatura(
        metadata=FaturaMetadata(
            banco=banco,
            titular=titular,
            referencia_mes="Maio/2026",
            data_fechamento="05/05/2026",
            data_vencimento="12/05/2026",
            valor_total=300.0,
        ),
        transacoes=[
            Transacao(data="01/05/2026", descricao="POSTO SHELL", parcela="",
                      cidade="SP", valor=200.0),
            Transacao(data="02/05/2026", descricao="UBER TRIP", parcela="",
                      cidade="SP", valor=100.0),
        ],
    )


def test_regenera_planilha_com_3_abas_basicas(banco_temporario, tmp_path):
    """Excel regenerado tem Informações, Transações e Resumo por Categoria."""
    from db.repository import upsert_fatura
    from export.excel import regenerar_planilha_do_banco

    upsert_fatura(_fatura("Demo", "Joao", "F1.pdf"), arquivo="F1.pdf")

    destino = tmp_path / "saida.xlsx"
    fat, lanc = regenerar_planilha_do_banco(destino)

    assert fat == 1
    assert lanc == 2
    assert destino.exists()

    sheets = pd.ExcelFile(destino).sheet_names
    assert "Informações" in sheets
    assert "Transações" in sheets
    assert "Resumo por Categoria" in sheets


def test_excel_regenerado_preserva_totais(banco_temporario, tmp_path):
    """Soma de Transações == soma original; TOTAL GERAL bate."""
    from db.repository import upsert_fatura
    from export.excel import regenerar_planilha_do_banco

    upsert_fatura(_fatura("Demo", "Joao", "F1.pdf"), arquivo="F1.pdf")
    upsert_fatura(_fatura("Demo2", "Maria", "F2.pdf"), arquivo="F2.pdf")

    destino = tmp_path / "saida.xlsx"
    regenerar_planilha_do_banco(destino)

    df = pd.read_excel(destino, sheet_name="Transações")
    assert abs(df["Valor (R$)"].sum() - 600.0) < 0.01

    resumo = pd.read_excel(destino, sheet_name="Resumo por Categoria")
    total = resumo[resumo["Categoria"] == "TOTAL GERAL"]["Valor (R$)"].iloc[0]
    assert abs(total - 600.0) < 0.01


def test_regerar_duas_vezes_da_mesma_coisa(banco_temporario, tmp_path):
    """Regenerar 2x não muda o resultado (banco é determinístico)."""
    from db.repository import upsert_fatura
    from export.excel import regenerar_planilha_do_banco

    upsert_fatura(_fatura("Demo", "Joao", "F1.pdf"), arquivo="F1.pdf")

    a = tmp_path / "a.xlsx"
    b = tmp_path / "b.xlsx"
    regenerar_planilha_do_banco(a)
    regenerar_planilha_do_banco(b)

    df_a = pd.read_excel(a, sheet_name="Transações")
    df_b = pd.read_excel(b, sheet_name="Transações")
    pd.testing.assert_frame_equal(df_a, df_b)


def test_referencia_iso_volta_pt_br_no_excel(banco_temporario, tmp_path):
    """`2026-05` no banco vira `Maio/2026` no Excel (compat com formato CLI)."""
    from db.repository import upsert_fatura
    from export.excel import regenerar_planilha_do_banco

    upsert_fatura(_fatura("Demo", "Joao", "F1.pdf"), arquivo="F1.pdf")

    destino = tmp_path / "saida.xlsx"
    regenerar_planilha_do_banco(destino)

    df = pd.read_excel(destino, sheet_name="Informações")
    assert df["Referência"].iloc[0] == "Maio/2026"


def test_cartao_combina_banco_e_titular(banco_temporario, tmp_path):
    """`Cartão` na aba Informações é `'Banco — Titular'`."""
    from db.repository import upsert_fatura
    from export.excel import regenerar_planilha_do_banco

    upsert_fatura(
        _fatura("Nubank", "Eliabe", "F1.pdf"), arquivo="F1.pdf"
    )

    destino = tmp_path / "saida.xlsx"
    regenerar_planilha_do_banco(destino)

    df = pd.read_excel(destino, sheet_name="Informações")
    assert df["Cartão"].iloc[0] == "Nubank — Eliabe"
    assert df["Banco"].iloc[0] == "Nubank"
    assert df["Titular"].iloc[0] == "Eliabe"


def test_banco_vazio_gera_xlsx_minimo(banco_temporario, tmp_path):
    """Sem nenhuma fatura, ainda gera arquivo com abas vazias."""
    from export.excel import regenerar_planilha_do_banco

    destino = tmp_path / "saida.xlsx"
    fat, lanc = regenerar_planilha_do_banco(destino)
    assert fat == 0
    assert lanc == 0
    assert destino.exists()
    df = pd.read_excel(destino, sheet_name="Informações")
    assert df.empty
