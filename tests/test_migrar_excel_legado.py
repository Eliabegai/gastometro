"""Testes do `imports.migrar_excel_legado`: end-to-end com Excel sintético."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def _criar_excel_legado(destino: Path) -> None:
    """Cria `gastometro.xlsx` com as abas Informações/Transações esperadas."""
    df_info = pd.DataFrame(
        [
            {
                "Arquivo": "F1.pdf",
                "Banco": "Demo",
                "Titular": "Joao",
                "Cartão": "Demo — Joao",
                "Referência": "Abril/2026",
                "Data de fechamento": "05/04/2026",
                "Data de vencimento": "12/04/2026",
                "Valor total (R$)": 250.0,
                "Qtde. de transações": 3,
            },
            {
                "Arquivo": "F2.pdf",
                "Banco": "Outro",
                "Titular": "Maria",
                "Cartão": "Outro — Maria",
                "Referência": "Maio/2026",
                "Data de fechamento": "05/05/2026",
                "Data de vencimento": "12/05/2026",
                "Valor total (R$)": 150.0,
                "Qtde. de transações": 2,
            },
        ]
    )

    df_tx = pd.DataFrame(
        [
            {
                "Arquivo": "F1.pdf",
                "Banco": "Demo",
                "Titular": "Joao",
                "Cartão": "Demo — Joao",
                "Referência": "Abril/2026",
                "Data": "01/04/2026",
                "Descrição": "MERCADO ABC",
                "Parcela": "",
                "Cidade": "SP",
                "Valor (R$)": 100.0,
                "Categoria": "Mercado",
            },
            {
                "Arquivo": "F1.pdf",
                "Banco": "Demo",
                "Titular": "Joao",
                "Cartão": "Demo — Joao",
                "Referência": "Abril/2026",
                "Data": "02/04/2026",
                "Descrição": "POSTO X",
                "Parcela": "",
                "Cidade": "SP",
                "Valor (R$)": 200.0,
                "Categoria": "Combustível",
            },
            {
                "Arquivo": "F1.pdf",
                "Banco": "Demo",
                "Titular": "Joao",
                "Cartão": "Demo — Joao",
                "Referência": "Abril/2026",
                "Data": "03/04/2026",
                "Descrição": "ESTORNO LOJA",
                "Parcela": "",
                "Cidade": "SP",
                "Valor (R$)": -50.0,
                "Categoria": "Outros Gastos",
            },
            {
                "Arquivo": "F2.pdf",
                "Banco": "Outro",
                "Titular": "Maria",
                "Cartão": "Outro — Maria",
                "Referência": "Maio/2026",
                "Data": "01/05/2026",
                "Descrição": "ALMOCO",
                "Parcela": "",
                "Cidade": "RJ",
                "Valor (R$)": 80.0,
                "Categoria": "Alimentação",
            },
            {
                "Arquivo": "F2.pdf",
                "Banco": "Outro",
                "Titular": "Maria",
                "Cartão": "Outro — Maria",
                "Referência": "Maio/2026",
                "Data": "02/05/2026",
                "Descrição": "TAXI",
                "Parcela": "",
                "Cidade": "RJ",
                "Valor (R$)": 70.0,
                "Categoria": "Transporte",
            },
        ]
    )

    with pd.ExcelWriter(destino, engine="openpyxl") as w:
        df_info.to_excel(w, sheet_name="Informações", index=False)
        df_tx.to_excel(w, sheet_name="Transações", index=False)


def test_migrar_preserva_totais(banco_temporario, tmp_path):
    """Totais por fatura e geral batem ±R$ 0,01 após migrar Excel sintético."""
    from db.repository import listar_faturas_df, listar_lancamentos_df
    from imports.migrar_excel_legado import migrar

    excel = tmp_path / "gastometro.xlsx"
    _criar_excel_legado(excel)

    resultado = migrar(excel)
    assert resultado["faturas"] == 2
    assert resultado["lancamentos"] == 5

    df_lanc = listar_lancamentos_df()
    df_fat = listar_faturas_df()

    assert len(df_fat) == 2
    assert len(df_lanc) == 5

    soma_banco = float(df_lanc["valor"].sum())
    soma_esperada = 100.0 + 200.0 - 50.0 + 80.0 + 70.0
    assert abs(soma_banco - soma_esperada) < 0.01


def test_migrar_idempotente(banco_temporario, tmp_path):
    """Re-rodar a migração não duplica nada."""
    from db.repository import listar_faturas_df, listar_lancamentos_df
    from imports.migrar_excel_legado import migrar

    excel = tmp_path / "gastometro.xlsx"
    _criar_excel_legado(excel)

    migrar(excel)
    resultado = migrar(excel)
    assert resultado["lancamentos"] == 0

    assert len(listar_faturas_df()) == 2
    assert len(listar_lancamentos_df()) == 5


def test_migrar_preserva_categoria_manual(banco_temporario, tmp_path):
    """Categoria gravada no Excel é mantida (em vez de re-categorizar)."""
    from db.repository import listar_lancamentos_df
    from imports.migrar_excel_legado import migrar

    excel = tmp_path / "gastometro.xlsx"
    _criar_excel_legado(excel)

    migrar(excel)
    df = listar_lancamentos_df()

    # "ESTORNO LOJA" no Excel sintético foi marcado manualmente como
    # "Outros Gastos" (o dicionário fixo poderia escolher algo diferente
    # para essa descrição em outro contexto). A migração deve respeitar.
    estorno = df[df["descricao"] == "ESTORNO LOJA"]
    assert estorno["categoria"].iloc[0] == "Outros Gastos"


def test_migrar_grava_fonte_excel_legado(banco_temporario, tmp_path):
    """Lançamentos migrados levam `fonte='excel_legado'` (rastreio de origem)."""
    from db.repository import listar_lancamentos_df
    from imports.migrar_excel_legado import migrar

    excel = tmp_path / "gastometro.xlsx"
    _criar_excel_legado(excel)
    migrar(excel)

    df = listar_lancamentos_df()
    assert (df["fonte"] == "excel_legado").all()
