"""Testes do motor de diagnóstico (auditoria de fluxo + vazamentos)."""

from __future__ import annotations

from datetime import date

import pandas as pd

from analytics.diagnostico import (
    PAPEL_AUDITORIA,
    PAPEL_VAZAMENTO,
    Achado,
    diagnosticar,
    filtrar_papel,
    meses_com_despesa,
    plano_simples,
    score_tratamento,
    tem_papel,
)


def _df(registros: list[dict]) -> pd.DataFrame:
    base = {
        "tipo": "despesa",
        "categoria": "Outros Gastos",
        "conta": "Nubank — Eliabe",
        "parcela": "",
        "pessoa": "Eliabe",
    }
    linhas = []
    for r in registros:
        row = {**base, **r}
        if "data" not in row and "referencia_mes" in row:
            ano, mes = str(row["referencia_mes"]).split("-")
            row["data"] = date(int(ano), int(mes), 10)
        linhas.append(row)
    return pd.DataFrame(linhas)


def _por_id(diag, prefixo: str) -> list:
    return [a for a in diag.achados if a.id == prefixo or a.id.startswith(prefixo)]


def test_taxa_poupanca_alerta_abaixo_de_10_pct():
    df = _df(
        [
            {
                "tipo": "receita",
                "categoria": "Salário",
                "descricao": "Salário",
                "valor": 500,
                "referencia_mes": "2025-01",
            },
            {
                "tipo": "receita",
                "categoria": "Salário",
                "descricao": "Salário",
                "valor": 500,
                "referencia_mes": "2025-02",
            },
            {
                "descricao": "Mercado",
                "categoria": "Mercado",
                "valor": 475,
                "referencia_mes": "2025-01",
            },
            {
                "descricao": "Mercado",
                "categoria": "Mercado",
                "valor": 475,
                "referencia_mes": "2025-02",
            },
        ]
    )
    diag = diagnosticar(df)
    assert diag.kpis.taxa_poupanca is not None
    assert abs(diag.kpis.taxa_poupanca - 0.05) < 1e-9
    achados = _por_id(diag, "poupanca:alerta")
    assert len(achados) == 1
    assert achados[0].severidade == "alerta"
    assert tem_papel(achados[0], PAPEL_AUDITORIA)


def test_taxa_poupanca_info_entre_10_e_20_pct():
    df = _df(
        [
            {
                "tipo": "receita",
                "categoria": "Salário",
                "descricao": "Salário",
                "valor": 500,
                "referencia_mes": "2025-01",
            },
            {
                "tipo": "receita",
                "categoria": "Salário",
                "descricao": "Salário",
                "valor": 500,
                "referencia_mes": "2025-02",
            },
            {
                "descricao": "Mercado",
                "categoria": "Mercado",
                "valor": 425,
                "referencia_mes": "2025-01",
            },
            {
                "descricao": "Mercado",
                "categoria": "Mercado",
                "valor": 425,
                "referencia_mes": "2025-02",
            },
        ]
    )
    diag = diagnosticar(df)
    assert diag.kpis.taxa_poupanca is not None
    assert abs(diag.kpis.taxa_poupanca - 0.15) < 1e-9
    achados = _por_id(diag, "poupanca:info")
    assert len(achados) == 1
    assert achados[0].severidade == "info"


def test_taxa_poupanca_silencio_acima_de_20_pct():
    df = _df(
        [
            {
                "tipo": "receita",
                "categoria": "Salário",
                "descricao": "Salário",
                "valor": 500,
                "referencia_mes": "2025-01",
            },
            {
                "tipo": "receita",
                "categoria": "Salário",
                "descricao": "Salário",
                "valor": 500,
                "referencia_mes": "2025-02",
            },
            {
                "descricao": "Mercado",
                "categoria": "Mercado",
                "valor": 375,
                "referencia_mes": "2025-01",
            },
            {
                "descricao": "Mercado",
                "categoria": "Mercado",
                "valor": 375,
                "referencia_mes": "2025-02",
            },
        ]
    )
    diag = diagnosticar(df)
    assert diag.kpis.taxa_poupanca == 0.25
    assert _por_id(diag, "poupanca:") == []
    assert _por_id(diag, "saldo:negativo") == []


def test_saldo_negativo_e_critico():
    df = _df(
        [
            {
                "tipo": "receita",
                "categoria": "Salário",
                "descricao": "Salário",
                "valor": 400,
                "referencia_mes": "2025-01",
            },
            {
                "tipo": "receita",
                "categoria": "Salário",
                "descricao": "Salário",
                "valor": 400,
                "referencia_mes": "2025-02",
            },
            {
                "descricao": "Mercado",
                "categoria": "Mercado",
                "valor": 500,
                "referencia_mes": "2025-01",
            },
            {
                "descricao": "Mercado",
                "categoria": "Mercado",
                "valor": 500,
                "referencia_mes": "2025-02",
            },
        ]
    )
    diag = diagnosticar(df)
    achados = _por_id(diag, "saldo:negativo")
    assert len(achados) == 1
    assert achados[0].severidade == "critico"
    assert _por_id(diag, "poupanca:") == []


def test_sem_receita_emite_info():
    df = _df(
        [
            {
                "descricao": "Mercado",
                "categoria": "Mercado",
                "valor": 100,
                "referencia_mes": "2025-01",
            },
            {
                "descricao": "Mercado",
                "categoria": "Mercado",
                "valor": 100,
                "referencia_mes": "2025-02",
            },
        ]
    )
    diag = diagnosticar(df)
    achados = _por_id(diag, "poupanca:sem-receita")
    assert len(achados) == 1
    assert achados[0].severidade == "info"
    assert diag.kpis.taxa_poupanca is None


def test_assinatura_vira_vazamento_com_custo_anual():
    df = _df(
        [
            {
                "descricao": "NETFLIX.COM",
                "categoria": "Assinatura Digital",
                "valor": 21.90,
                "referencia_mes": "2025-01",
            },
            {
                "descricao": "NETFLIX.COM",
                "categoria": "Assinatura Digital",
                "valor": 21.90,
                "referencia_mes": "2025-02",
            },
        ]
    )
    diag = diagnosticar(df)
    vazamentos = filtrar_papel(diag.achados, PAPEL_VAZAMENTO)
    assinaturas = [
        a for a in vazamentos if a.id.startswith("assinatura:") and "duplicada" not in a.id
    ]
    assert len(assinaturas) == 1
    a = assinaturas[0]
    assert abs(a.custo_mensal - 21.90) < 1e-9
    assert abs(a.custo_anual - 21.90 * 12) < 1e-9
    assert a.impacto_estilo == "baixo"
    assert "cancelar" in a.tratamento.lower() or "avaliar" in a.tratamento.lower()


def test_assinatura_duplicada_de_streaming():
    df = _df(
        [
            {
                "descricao": "NETFLIX.COM",
                "categoria": "Assinatura Digital",
                "valor": 39.90,
                "referencia_mes": "2025-01",
            },
            {
                "descricao": "NETFLIX.COM",
                "categoria": "Assinatura Digital",
                "valor": 39.90,
                "referencia_mes": "2025-02",
            },
            {
                "descricao": "Disney Plus",
                "categoria": "Assinatura Digital",
                "valor": 27.90,
                "referencia_mes": "2025-01",
            },
            {
                "descricao": "Disney Plus",
                "categoria": "Assinatura Digital",
                "valor": 27.90,
                "referencia_mes": "2025-02",
            },
        ]
    )
    diag = diagnosticar(df)
    dups = _por_id(diag, "assinatura-duplicada:streaming")
    assert len(dups) == 1
    assert dups[0].severidade == "alerta"
    assert abs(dups[0].economia_mensal_estimada - 27.90) < 1e-9
    assert "Netflix" in dups[0].detalhe or "Disney" in dups[0].detalhe


def test_impulso_acima_da_mediana():
    registros = []
    for mes, valor in [
        ("2025-01", 40.0),
        ("2025-02", 40.0),
        ("2025-03", 40.0),
        ("2025-04", 40.0),
        ("2025-05", 40.0),
        ("2025-06", 250.0),
    ]:
        registros.append(
            {
                "descricao": "Cinema extra" if valor > 100 else f"Lanche {mes}",
                "categoria": "Lazer",
                "valor": valor,
                "referencia_mes": mes,
            }
        )
    diag = diagnosticar(_df(registros))
    impulsos = [a for a in diag.achados if a.id.startswith("impulso:")]
    assert len(impulsos) == 1
    assert "Cinema extra" in impulsos[0].titulo
    assert impulsos[0].economia_mensal_estimada == 250.0


def test_categoria_essencial_nao_sugere_cortar():
    registros = [
        {
            "descricao": "Consulta extra",
            "categoria": "Educação",
            "valor": 400.0,
            "referencia_mes": "2025-06",
        },
    ]
    for mes in ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05"]:
        registros.append(
            {
                "descricao": f"Mensalidade {mes}",
                "categoria": "Educação",
                "valor": 50.0,
                "referencia_mes": mes,
            }
        )
    diag = diagnosticar(_df(registros))
    tickets = [a for a in diag.achados if a.id.startswith("ticket:")]
    assert tickets, "ticket atípico de Educação deveria aparecer"
    for a in tickets:
        assert "não sugerimos cortar" in a.tratamento.lower()
        assert a.economia_mensal_estimada == 0.0
        assert "cortar" not in a.tratamento.lower().replace("não sugerimos cortar", "")


def test_ranking_prioriza_impacto_baixo():
    baixo = Achado(
        id="a-baixo",
        papeis=(PAPEL_VAZAMENTO,),
        severidade="info",
        titulo="Assinatura barata",
        detalhe="",
        custo_mensal=100,
        custo_anual=1200,
        impacto_estilo="baixo",
        tratamento="cancelar",
        economia_mensal_estimada=100,
    )
    alto = Achado(
        id="a-alto",
        papeis=(PAPEL_AUDITORIA,),
        severidade="alerta",
        titulo="Mercado",
        detalhe="",
        custo_mensal=100,
        custo_anual=1200,
        impacto_estilo="alto",
        tratamento="reduzir",
        economia_mensal_estimada=100,
    )
    assert score_tratamento(baixo) > score_tratamento(alto)
    plano = plano_simples([alto, baixo], n=5)
    assert plano[0].id == "a-baixo"
    assert plano[1].id == "a-alto"


def test_meses_com_despesa_e_plano_top_5():
    df = _df(
        [
            {"descricao": "A", "valor": 10, "referencia_mes": "2025-01"},
            {"descricao": "B", "valor": 10, "referencia_mes": "2025-02"},
        ]
    )
    assert meses_com_despesa(df) == 2
    assert meses_com_despesa(_df([])) == 0

    achados = [
        Achado(
            id=f"x{i}",
            papeis=(PAPEL_VAZAMENTO,),
            severidade="info",
            titulo=str(i),
            detalhe="",
            custo_mensal=float(i),
            custo_anual=float(i) * 12,
            impacto_estilo="baixo",
            tratamento="t",
            economia_mensal_estimada=float(i),
        )
        for i in range(8)
    ]
    plano = plano_simples(achados, n=5)
    assert [a.id for a in plano] == ["x7", "x6", "x5", "x4", "x3"]


def test_teto_estourado_vira_achado_de_auditoria():
    df = _df(
        [
            {
                "tipo": "receita",
                "categoria": "Salário",
                "descricao": "Salário",
                "valor": 2000,
                "referencia_mes": "2025-01",
            },
            {
                "tipo": "receita",
                "categoria": "Salário",
                "descricao": "Salário",
                "valor": 2000,
                "referencia_mes": "2025-02",
            },
            {
                "descricao": "Mercado",
                "categoria": "Mercado",
                "valor": 100,
                "referencia_mes": "2025-01",
            },
            {
                "descricao": "Mercado",
                "categoria": "Mercado",
                "valor": 100,
                "referencia_mes": "2025-02",
            },
        ]
    )
    progressos = pd.DataFrame(
        [
            {
                "rotulo": "Casal — Mercado",
                "gasto": 120.0,
                "limite": 100.0,
                "pct": 120.0,
                "status": "estourado",
                "escopo": "casal",
            }
        ]
    )
    diag = diagnosticar(df, progressos=progressos)
    tetos = _por_id(diag, "teto:")
    assert len(tetos) == 1
    assert tetos[0].severidade == "critico"
    assert tetos[0].economia_mensal_estimada == 20.0
    assert tem_papel(tetos[0], PAPEL_AUDITORIA)


def test_farmacia_nao_gera_ticket_atipico():
    registros = [
        {
            "descricao": "Remédio caro",
            "categoria": "Farmácia",
            "valor": 500.0,
            "referencia_mes": "2025-06",
        },
    ]
    for mes in ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05"]:
        registros.append(
            {
                "descricao": f"Farmácia {mes}",
                "categoria": "Farmácia",
                "valor": 40.0,
                "referencia_mes": mes,
            }
        )
    diag = diagnosticar(_df(registros))
    tickets = [a for a in diag.achados if a.id.startswith("ticket:") or a.id.startswith("impulso:")]
    assert tickets == []
