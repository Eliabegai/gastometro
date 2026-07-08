"""Testes da detecção de gastos recorrentes."""

from __future__ import annotations

import pandas as pd

from analytics.recorrentes import (
    chave_merchant,
    classificar_tipo_recorrente,
    construir_recorrentes_excel,
    detectar_recorrentes,
    marcar_recorrentes,
)


def _df_lancamentos(registros: list[dict]) -> pd.DataFrame:
    base = {
        "tipo": "despesa",
        "categoria": "Outros Gastos",
        "conta": "Nubank — Eliabe",
        "parcela": "",
    }
    return pd.DataFrame([{**base, **r} for r in registros])


def test_chave_merchant_normaliza_variantes():
    assert chave_merchant("NETFLIX.COM") == chave_merchant("netflix com")
    assert chave_merchant("SPOTIFY 12345") == chave_merchant("spotify")
    assert chave_merchant("DM*SpotifyV") == chave_merchant("DM *Spotify")
    assert chave_merchant("Google YouTubePremiu") == chave_merchant("Google Youtubepremium")


def test_unifica_assinatura_em_cartoes_diferentes():
    df = _df_lancamentos([
        {
            "descricao": "DM*SpotifyV",
            "valor": 21.90,
            "referencia_mes": "2025-01",
            "categoria": "Assinatura Digital",
            "conta": "Ailos — Eliabe Gai",
        },
        {
            "descricao": "DM *Spotify",
            "valor": 21.90,
            "referencia_mes": "2025-02",
            "categoria": "Assinatura Digital",
            "conta": "Nubank — Eliabe Gai",
        },
        {
            "descricao": "DM*SpotifyV",
            "valor": 27.90,
            "referencia_mes": "2025-03",
            "categoria": "Assinatura Digital",
            "conta": "Ailos — Eliabe Gai",
        },
    ])
    padroes = detectar_recorrentes(df, meses_min=3, meses_min_assinatura=2)
    assert len(padroes) == 1
    assert padroes.iloc[0]["descricao"] == "Spotify"
    assert padroes.iloc[0]["meses"] == 3
    assert "Ailos" in padroes.iloc[0]["contas"]
    assert "Nubank" in padroes.iloc[0]["contas"]
    assert padroes.iloc[0]["variacao_pct"] > 0


def test_unifica_youtube_em_cartoes_diferentes():
    df = _df_lancamentos([
        {
            "descricao": "Google YouTubePremiu",
            "valor": 24.90,
            "referencia_mes": "2025-01",
            "categoria": "Assinatura Digital",
            "conta": "Ailos — Eliabe Gai",
        },
        {
            "descricao": "Google Youtubepremium",
            "valor": 24.90,
            "referencia_mes": "2025-02",
            "categoria": "Assinatura Digital",
            "conta": "Nubank — Ana",
        },
        {
            "descricao": "Google YouTubePremiu",
            "valor": 24.90,
            "referencia_mes": "2025-03",
            "categoria": "Assinatura Digital",
            "conta": "Ailos — Eliabe Gai",
        },
    ])
    padroes = detectar_recorrentes(df, meses_min=3, meses_min_assinatura=2)
    assert len(padroes) == 1
    assert padroes.iloc[0]["descricao"] == "YouTube Premium"


def test_detecta_recorrente_em_tres_meses():
    df = _df_lancamentos([
        {"descricao": "NETFLIX.COM", "valor": 55.90, "referencia_mes": "2025-01"},
        {"descricao": "NETFLIX COM", "valor": 55.90, "referencia_mes": "2025-02"},
        {"descricao": "netflix.com", "valor": 55.90, "referencia_mes": "2025-03"},
        {"descricao": "UBER TRIP", "valor": 25.0, "referencia_mes": "2025-01"},
    ])
    padroes = detectar_recorrentes(df, meses_min=3)
    assert len(padroes) == 1
    assert padroes.iloc[0]["meses"] == 3
    assert padroes.iloc[0]["media_mensal"] == 55.90
    assert padroes.iloc[0]["tipo_recorrente"] == "assinatura"


def test_classifica_fatura_cartao():
    assert classificar_tipo_recorrente("Fatura Nubank (mensal)", "Cartão de Crédito") == "fatura_cartao"


def test_classifica_financiamento():
    assert classificar_tipo_recorrente("Financiamento Casa - Caixa", "Financiamento Casa") == "financiamento"


def test_classifica_conta_fixa():
    assert classificar_tipo_recorrente("Internet - Unifique", "Casa e Construção") == "conta_fixa"


def test_classifica_compra_recorrente():
    assert classificar_tipo_recorrente("Havan", "Outros Gastos") == "compra_recorrente"


def test_exclui_parcelamento():
    df = _df_lancamentos([
        {"descricao": "LOJA XYZ", "valor": 100.0, "referencia_mes": "2025-01", "parcela": "01/06"},
        {"descricao": "LOJA XYZ", "valor": 100.0, "referencia_mes": "2025-02", "parcela": "02/06"},
        {"descricao": "LOJA XYZ", "valor": 100.0, "referencia_mes": "2025-03", "parcela": "03/06"},
    ])
    assert detectar_recorrentes(df).empty


def test_assinatura_aceita_dois_meses():
    df = _df_lancamentos([
        {"descricao": "SPOTIFY", "valor": 21.90, "referencia_mes": "2025-01", "categoria": "Assinatura Digital"},
        {"descricao": "SPOTIFY", "valor": 21.90, "referencia_mes": "2025-02", "categoria": "Assinatura Digital"},
    ])
    padroes = detectar_recorrentes(df, meses_min=3, meses_min_assinatura=2)
    assert len(padroes) == 1


def test_marcar_recorrentes_adiciona_colunas():
    df = _df_lancamentos([
        {"descricao": "NETFLIX.COM", "valor": 55.90, "referencia_mes": "2025-01"},
        {"descricao": "NETFLIX COM", "valor": 55.90, "referencia_mes": "2025-02"},
        {"descricao": "netflix.com", "valor": 55.90, "referencia_mes": "2025-03"},
        {"descricao": "UBER TRIP", "valor": 25.0, "referencia_mes": "2025-01"},
    ])
    marcado = marcar_recorrentes(df)
    assert marcado["eh_recorrente"].sum() == 3
    assert not marcado.loc[marcado["descricao"] == "UBER TRIP", "eh_recorrente"].iloc[0]


def test_discovery_unifica_e_lista_lancamentos():
    df = _df_lancamentos([
        {
            "descricao": "Discovery+ sem Anun...",
            "valor": 18.90,
            "referencia_mes": "2024-05",
            "categoria": "Assinatura Digital",
            "conta": "Nubank — Ana",
        },
        {
            "descricao": "Discovery+ sem Anun...",
            "valor": 18.90,
            "referencia_mes": "2024-07",
            "categoria": "Assinatura Digital",
            "conta": "Nubank — Ana",
        },
    ])
    padroes = detectar_recorrentes(df, meses_min=3, meses_min_assinatura=2)
    assert len(padroes) == 1
    assert padroes.iloc[0]["descricao"] == "Discovery+"
    assert padroes.iloc[0]["descricao_fatura"] == "Discovery+ sem Anun..."

    from analytics.recorrentes import listar_lancamentos_padrao

    lancs = listar_lancamentos_padrao(df, padroes.iloc[0]["chave"])
    assert len(lancs) == 2


def test_construir_recorrentes_excel_formato_legado():
    df = pd.DataFrame([
        {
            "Descrição": "NETFLIX.COM",
            "Valor (R$)": 55.90,
            "Referência": "2025-01",
            "Categoria": "Assinatura Digital",
            "Cartão": "Nubank",
            "Tipo": "despesa",
            "Parcela": "",
        },
        {
            "Descrição": "NETFLIX COM",
            "Valor (R$)": 55.90,
            "Referência": "2025-02",
            "Categoria": "Assinatura Digital",
            "Cartão": "Nubank",
            "Tipo": "despesa",
            "Parcela": "",
        },
        {
            "Descrição": "netflix.com",
            "Valor (R$)": 55.90,
            "Referência": "2025-03",
            "Categoria": "Assinatura Digital",
            "Cartão": "Nubank",
            "Tipo": "despesa",
            "Parcela": "",
        },
    ])
    out = construir_recorrentes_excel(df, meses_min=3)
    assert list(out.columns) == [
        "Tipo",
        "Descrição",
        "Categoria",
        "Cartão(ões)",
        "Meses",
        "Qtde. Transações",
        "Total (R$)",
        "Média Mensal (R$)",
    ]
    assert len(out) == 1
    assert "Assinatura" in out["Tipo"].iloc[0]
