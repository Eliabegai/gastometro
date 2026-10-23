"""Cobertura de faturas: quais cartões × meses têm fatura e se fecham.

Para cada cartão, percorre os meses entre a primeira fatura e o mês
corrente e classifica:

- `ok`: fatura importada e a soma dos lançamentos bate com o total
  declarado (tolerância de centavos);
- `diferenca`: fatura importada, mas lançamentos ≠ total declarado
  (linha que o parser perdeu, duplicada ou fatura incompleta);
- `sem_fatura`: nenhum PDF importado para o mês (buraco no histórico).
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from analytics.fluxo import mes_corrente_iso, resumir_fluxo

STATUS_OK = "ok"
STATUS_DIFERENCA = "diferenca"
STATUS_SEM_FATURA = "sem_fatura"

COLUNAS = ["conta", "referencia_mes", "status", "declarado", "lancado", "diferenca"]


def _meses_entre(inicio: str, fim: str) -> list[str]:
    ai, mi = (int(p) for p in inicio.split("-", 1))
    af, mf = (int(p) for p in fim.split("-", 1))
    meses: list[str] = []
    ano, mes = ai, mi
    while (ano, mes) <= (af, mf):
        meses.append(f"{ano:04d}-{mes:02d}")
        mes += 1
        if mes > 12:
            ano, mes = ano + 1, 1
    return meses


def _mes_anterior(ref: str) -> str:
    ano, mes = (int(p) for p in ref.split("-", 1))
    mes -= 1
    if mes == 0:
        ano, mes = ano - 1, 12
    return f"{ano:04d}-{mes:02d}"


def matriz_cobertura(
    faturas: pd.DataFrame | None,
    lancamentos: pd.DataFrame | None,
    *,
    tolerancia: float = 0.05,
    hoje: date | None = None,
) -> pd.DataFrame:
    """Linha por (cartão, mês) com `status`, `declarado`, `lancado`, `diferenca`."""
    vazio = pd.DataFrame(columns=COLUNAS)
    if faturas is None or faturas.empty:
        return vazio
    obrigatorias = {"arquivo", "conta", "referencia_mes", "valor_total_declarado"}
    if not obrigatorias.issubset(faturas.columns):
        return vazio

    fat = faturas.copy()
    fat["referencia_mes"] = fat["referencia_mes"].fillna("").astype(str)
    fat = fat[fat["referencia_mes"] != ""]
    if fat.empty:
        return vazio

    lancado_por_arquivo: dict[str, float] = {}
    if (
        lancamentos is not None
        and not lancamentos.empty
        and {"arquivo", "tipo", "valor"}.issubset(lancamentos.columns)
    ):
        com_arquivo = lancamentos[lancamentos["arquivo"].fillna("").astype(str) != ""]
        for arquivo, grupo in com_arquivo.groupby("arquivo"):
            lancado_por_arquivo[str(arquivo)] = resumir_fluxo(grupo).despesas

    limite = mes_corrente_iso(hoje)
    linhas: list[dict[str, object]] = []
    for conta, grupo_conta in fat.groupby("conta"):
        primeiro = str(grupo_conta["referencia_mes"].min())
        ultimo = str(grupo_conta["referencia_mes"].max())
        # Cartão ainda em uso (última fatura no mês anterior ou depois):
        # cobra também os meses até o corrente. Cartão encerrado só tem
        # os buracos internos checados.
        if ultimo >= _mes_anterior(limite) and ultimo < limite:
            ultimo = limite
        for ref in _meses_entre(primeiro, ultimo):
            do_mes = grupo_conta[grupo_conta["referencia_mes"] == ref]
            if do_mes.empty:
                linhas.append(
                    {
                        "conta": conta,
                        "referencia_mes": ref,
                        "status": STATUS_SEM_FATURA,
                        "declarado": None,
                        "lancado": None,
                        "diferenca": None,
                    }
                )
                continue
            declarado = float(do_mes["valor_total_declarado"].fillna(0).sum())
            lancado = float(
                sum(lancado_por_arquivo.get(str(a), 0.0) for a in do_mes["arquivo"])
            )
            diferenca = round(lancado - declarado, 2)
            status = STATUS_OK if abs(diferenca) <= tolerancia else STATUS_DIFERENCA
            linhas.append(
                {
                    "conta": conta,
                    "referencia_mes": ref,
                    "status": status,
                    "declarado": declarado,
                    "lancado": lancado,
                    "diferenca": diferenca,
                }
            )
    return pd.DataFrame(linhas, columns=COLUNAS)
