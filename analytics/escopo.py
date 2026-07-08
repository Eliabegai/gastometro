"""Classificação de gastos: casal (conjunto) vs pessoal.

Prioridade:
  1. Override por categoria no banco (`escopo_categoria`)
  2. Grupos automáticos (casa fixa, financiamentos, dízimos)
  3. Categorias marcadas como conjuntas por default
  4. Lançamento sem pessoa → casal
  5. Demais despesas → pessoal (pessoa do lançamento)
"""

from __future__ import annotations

from datetime import date

import pandas as pd

ESCOPO_CASAL = "casal"
ESCOPO_PESSOAL = "pessoal"

_CATEGORIAS_CASAL_DEFAULT = frozenset({
    "Financiamento Carro",
    "Financiamento Casa",
    "Dízimos",
    "Cartão de Crédito",  # fatura agregada da planilha familiar
})

_PREFIXOS_CASA_FIXA = (
    "luz",
    "água",
    "agua",
    "internet",
    "gás",
    "gas",
    "condomínio",
    "condominio",
    "celular",
    "telefone",
)


def _normalizar_desc(serie: pd.Series) -> pd.Series:
    return serie.fillna("").astype(str).str.strip().str.lower()


def _eh_casa_fixa(descricao: str) -> bool:
    desc = descricao.strip().lower()
    return any(desc.startswith(p) for p in _PREFIXOS_CASA_FIXA)


def classificar_escopo_linha(
    *,
    categoria: str,
    descricao: str,
    pessoa: str,
    overrides_categoria: dict[str, str] | None = None,
) -> str:
    """Classifica um lançamento como `casal` ou `pessoal`."""
    cat = (categoria or "").strip()
    overrides = overrides_categoria or {}

    if cat in overrides:
        return overrides[cat]

    if cat in _CATEGORIAS_CASAL_DEFAULT:
        return ESCOPO_CASAL

    if _eh_casa_fixa(descricao):
        return ESCOPO_CASAL

    if not (pessoa or "").strip():
        return ESCOPO_CASAL

    return ESCOPO_PESSOAL


def marcar_escopo(
    df: pd.DataFrame,
    *,
    overrides_categoria: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Adiciona colunas `escopo` e `escopo_rotulo` ao DataFrame de lançamentos."""
    if df.empty:
        out = df.copy()
        out["escopo"] = ""
        out["escopo_pessoa"] = ""
        return out

    out = df.copy()
    out["escopo"] = out.apply(
        lambda row: classificar_escopo_linha(
            categoria=str(row.get("categoria", "")),
            descricao=str(row.get("descricao", "")),
            pessoa=str(row.get("pessoa", "")),
            overrides_categoria=overrides_categoria,
        ),
        axis=1,
    )
    out["escopo_pessoa"] = out.apply(
        lambda row: (
            str(row.get("pessoa", "")).strip()
            if row["escopo"] == ESCOPO_PESSOAL
            else ""
        ),
        axis=1,
    )
    return out


def resumo_escopo_despesas(df: pd.DataFrame) -> dict[str, float]:
    """Soma despesas por escopo (`casal`, `pessoal` e total)."""
    if df.empty:
        return {"casal": 0.0, "pessoal": 0.0, "total": 0.0}

    sub = df[df["tipo"] == "despesa"].copy()
    if sub.empty:
        return {"casal": 0.0, "pessoal": 0.0, "total": 0.0}

    if "escopo" not in sub.columns:
        sub = marcar_escopo(sub)

    casal = float(sub.loc[sub["escopo"] == ESCOPO_CASAL, "valor"].sum())
    pessoal = float(sub.loc[sub["escopo"] == ESCOPO_PESSOAL, "valor"].sum())
    return {"casal": casal, "pessoal": pessoal, "total": casal + pessoal}


def resumo_por_pessoa(df: pd.DataFrame) -> pd.DataFrame:
    """Gastos pessoais agregados por pessoa."""
    if df.empty:
        return pd.DataFrame(columns=["pessoa", "total"])

    sub = df[df["tipo"] == "despesa"].copy()
    if "escopo" not in sub.columns:
        sub = marcar_escopo(sub)
    sub = sub[sub["escopo"] == ESCOPO_PESSOAL]
    if sub.empty:
        return pd.DataFrame(columns=["pessoa", "total"])

    agg = (
        sub.groupby("pessoa", as_index=False)["valor"]
        .sum()
        .rename(columns={"valor": "total"})
        .sort_values("total", ascending=False)
    )
    return agg


def resumo_escopo_categoria(
    df: pd.DataFrame,
    categoria: str,
    *,
    overrides_categoria: dict[str, str] | None = None,
) -> dict[str, float | int]:
    """Soma e quantidade casal/pessoal para uma categoria no recorte."""
    vazio = {"casal": 0.0, "pessoal": 0.0, "qtde_casal": 0, "qtde_pessoal": 0}
    if df.empty or not categoria:
        return vazio

    sub = df[(df["tipo"] == "despesa") & (df["categoria"] == categoria)]
    if sub.empty:
        return vazio

    marcado = marcar_escopo(sub, overrides_categoria=overrides_categoria)
    casal = marcado[marcado["escopo"] == ESCOPO_CASAL]
    pessoal = marcado[marcado["escopo"] == ESCOPO_PESSOAL]
    return {
        "casal": float(casal["valor"].sum()),
        "pessoal": float(pessoal["valor"].sum()),
        "qtde_casal": int(len(casal)),
        "qtde_pessoal": int(len(pessoal)),
    }


def referencia_mes_anterior(iso: str) -> str | None:
    """'2026-05' → '2026-04'; janeiro volta para dezembro do ano anterior."""
    if not iso or "-" not in iso:
        return None
    try:
        ano, mes = (int(p) for p in iso.split("-", 1))
    except ValueError:
        return None
    if mes <= 1:
        return f"{ano - 1}-12"
    return f"{ano}-{mes - 1:02d}"


def _ord_ref(iso: str) -> tuple[int, int]:
    if not iso or "-" not in iso:
        return (0, 0)
    try:
        ano, mes = iso.split("-", 1)
        return (int(ano), int(mes))
    except ValueError:
        return (0, 0)


def historico_escopo_mensal(
    df: pd.DataFrame,
    *,
    overrides_categoria: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Uma linha por mês com totais casal, pessoal e total de despesas."""
    cols = ["referencia_mes", "casal", "pessoal", "total"]
    if df.empty:
        return pd.DataFrame(columns=cols)

    marcado = marcar_escopo(df, overrides_categoria=overrides_categoria)
    despesas = marcado[marcado["tipo"] == "despesa"]
    if despesas.empty:
        return pd.DataFrame(columns=cols)

    linhas: list[dict[str, float | str]] = []
    for ref, grp in despesas.groupby("referencia_mes"):
        casal = float(grp.loc[grp["escopo"] == ESCOPO_CASAL, "valor"].sum())
        pessoal = float(grp.loc[grp["escopo"] == ESCOPO_PESSOAL, "valor"].sum())
        linhas.append(
            {
                "referencia_mes": str(ref),
                "casal": casal,
                "pessoal": pessoal,
                "total": casal + pessoal,
            }
        )
    out = pd.DataFrame(linhas)
    return out.sort_values("referencia_mes", key=lambda s: s.map(_ord_ref))


def resumo_por_categoria_escopo(
    df: pd.DataFrame,
    escopo: str,
    *,
    overrides_categoria: dict[str, str] | None = None,
    top_n: int = 10,
) -> pd.DataFrame:
    """Top categorias de despesa dentro de um escopo (`casal` ou `pessoal`)."""
    if df.empty:
        return pd.DataFrame(columns=["categoria", "total", "qtde"])

    marcado = marcar_escopo(df, overrides_categoria=overrides_categoria)
    sub = marcado[(marcado["tipo"] == "despesa") & (marcado["escopo"] == escopo)]
    if sub.empty:
        return pd.DataFrame(columns=["categoria", "total", "qtde"])

    agg = (
        sub.groupby("categoria")["valor"]
        .agg(total="sum", qtde="count")
        .reset_index()
        .sort_values("total", ascending=False)
        .head(top_n)
    )
    return agg


def comparativo_pessoas(
    df: pd.DataFrame,
    *,
    overrides_categoria: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Gastos pessoais por titular com participação no total pessoal."""
    por_pessoa = resumo_por_pessoa(
        marcar_escopo(df, overrides_categoria=overrides_categoria)
    )
    if por_pessoa.empty:
        return por_pessoa.assign(participacao_pct=0.0)

    total = float(por_pessoa["total"].sum())
    out = por_pessoa.copy()
    out["participacao_pct"] = (
        (out["total"] / total * 100.0).round(1) if total > 0 else 0.0
    )
    return out


def projetar_despesa_mes(
    df_mes: pd.DataFrame,
    *,
    referencia_mes: str,
    hoje: date | None = None,
) -> float | None:
    """Projeta despesa total do mês pelo ritmo até hoje. None se não aplicável."""
    if df_mes.empty or not referencia_mes or "-" not in referencia_mes:
        return None

    hoje = hoje or date.today()
    try:
        ano, mes = (int(p) for p in referencia_mes.split("-", 1))
    except ValueError:
        return None

    if hoje.year != ano or hoje.month != mes:
        return None

    import calendar

    dias_no_mes = calendar.monthrange(ano, mes)[1]
    dia_atual = min(hoje.day, dias_no_mes)
    if dia_atual <= 0:
        return None

    despesas = df_mes[df_mes["tipo"] == "despesa"]
    gasto = float(despesas["valor"].sum())
    if gasto <= 0:
        return 0.0

    return round(gasto / dia_atual * dias_no_mes, 2)
