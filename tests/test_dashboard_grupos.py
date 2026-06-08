"""Testa o helper `_soma_grupo` do dashboard sem rodar o Streamlit.

Garante que a soma agrupada (Cartões / Financiamentos / Casa Fixa /
Empréstimos) bate com o esperado pra cada chave, e que o critério
não vaza (lançamento de receita ou conta não-cartão não entra em
Cartões).
"""

from __future__ import annotations

import pandas as pd


def _linha(
    *,
    valor: float,
    tipo: str = "despesa",
    categoria: str = "Outros Gastos",
    conta_tipo: str = "outro",
    descricao: str = "X",
) -> dict:
    return {
        "valor": valor,
        "tipo": tipo,
        "categoria": categoria,
        "conta_tipo": conta_tipo,
        "descricao": descricao,
    }


def test_soma_grupo_cartoes_inclui_pdf_e_planilha_cartao() -> None:
    from app.paginas.dashboard import _soma_grupo

    df = pd.DataFrame([
        _linha(valor=100, categoria="Mercado", conta_tipo="cartao_credito"),
        _linha(
            valor=200, categoria="Cartão de Crédito", conta_tipo="cartao_credito"
        ),
        _linha(valor=50, categoria="Luz", conta_tipo="outro"),
        _linha(valor=999, categoria="Salário", tipo="receita",
               conta_tipo="cartao_credito"),
    ])

    assert _soma_grupo(df, "cartoes") == 300.0


def test_soma_grupo_financiamentos_casa_fixa_emprestimos() -> None:
    from app.paginas.dashboard import _soma_grupo

    df = pd.DataFrame([
        _linha(valor=1200, categoria="Financiamento Casa",
               descricao="Financiamento Casa - Caixa"),
        _linha(valor=800, categoria="Financiamento Carro",
               descricao="Financiamento Carro - BV"),
        _linha(valor=170, categoria="Luz", descricao="Luz - Celesc"),
        _linha(valor=77, categoria="Água", descricao="Água - Samae"),
        _linha(valor=160, categoria="Internet",
               descricao="Internet - Unifique"),
        _linha(valor=500, categoria="Empréstimos",
               descricao="Empréstimo Avulso"),
        # Não deve entrar em nenhum grupo abaixo:
        _linha(valor=999, categoria="Mercado", conta_tipo="cartao_credito",
               descricao="MERCADO XYZ"),
    ])

    assert _soma_grupo(df, "financiamentos") == 2000.0
    assert _soma_grupo(df, "casa_fixa") == 407.0
    assert _soma_grupo(df, "emprestimos") == 500.0


def test_soma_grupo_chave_desconhecida_devolve_zero() -> None:
    from app.paginas.dashboard import _soma_grupo

    df = pd.DataFrame([
        _linha(valor=100, conta_tipo="cartao_credito"),
    ])
    assert _soma_grupo(df, "inexistente") == 0.0


def test_soma_grupo_df_vazio_devolve_zero() -> None:
    from app.paginas.dashboard import _soma_grupo

    assert _soma_grupo(pd.DataFrame(), "cartoes") == 0.0



def test_soma_grupo_casa_fixa_usa_descricao_quando_override_move_categoria() -> None:
    """Override do usuário move 'Luz - Celesc' pra 'Casa e Construção'.
    O KPI Casa Fixa precisa continuar somando — por isso filtra pela
    descrição (Luz/Água/Internet) e não só por categoria."""
    from app.paginas.dashboard import _soma_grupo

    df = pd.DataFrame([
        _linha(valor=170, categoria="Casa e Construção"),
        _linha(valor=77, categoria="Casa e Construção"),
        _linha(valor=160, categoria="Casa e Construção"),
        _linha(valor=10, categoria="Casa e Construção"),  # não casa
    ])
    df["descricao"] = [
        "Luz - Celesc",
        "Água - Samae",
        "Internet - Unifique",
        "Outro Reparo na Casa",
    ]

    assert _soma_grupo(df, "casa_fixa") == 407.0


def test_soma_grupo_emprestimos_usa_descricao_ou_categoria() -> None:
    """`Empréstimos` cobre tanto categoria explícita quanto descrição
    começando com Empréstimo (com ou sem acento)."""
    from app.paginas.dashboard import _soma_grupo

    df = pd.DataFrame([
        _linha(valor=500, categoria="Empréstimos"),
        _linha(valor=200, categoria="Outros Gastos"),
        _linha(valor=300, categoria="Outros Gastos"),
        _linha(valor=99, categoria="Mercado"),  # não casa
    ])
    df["descricao"] = [
        "Linha por categoria",
        "Empréstimo Nubank (parcela)",
        "Emprestimo Sicredi",
        "MERCADO XYZ",
    ]

    assert _soma_grupo(df, "emprestimos") == 1000.0
