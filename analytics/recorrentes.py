"""Detecção de gastos recorrentes — assinaturas, contas fixas e similares.

Heurística:
  1. Agrupa por descrição normalizada (tolerante a maiúsculas, acentos,
     códigos de terminal e variações de grafia).
  2. Considera apenas despesas com valor positivo.
  3. Exclui parcelamentos (compra única dividida em N faturas).
  4. Exige o gasto em N meses distintos (default 3; assinaturas
     categorizadas aceitam 2).
  5. Classifica cada padrão em um tipo legível (assinatura, conta fixa,
     financiamento, compra recorrente, etc.).
"""

from __future__ import annotations

import re
from typing import TypedDict

import pandas as pd

from categorias import _normalizar

_CATEGORIAS_ASSINATURA = frozenset({
    "Assinatura Digital",
    "Serviços / Assinaturas",
})

_CATEGORIAS_FINANCIAMENTO = frozenset({
    "Financiamento Carro",
    "Financiamento Casa",
})

_CATEGORIAS_EMPRESTIMO = frozenset({
    "Empréstimos",
})

_CATEGORIAS_COMPRA = frozenset({
    "Mercado",
    "Alimentação",
    "Vestuário",
    "Compra Digital",
    "Farmácia",
    "Lazer",
    "Casa e Construção",
    "Combustível",
    "Transporte",
    "Outros Gastos",
    "Manutenção Carro",
    "Carro",
})

_CATEGORIAS_EDUCACAO = frozenset({
    "Educação",
})

_CATEGORIAS_DOACAO = frozenset({
    "Dízimos",
})

_CATEGORIAS_FATURA_CARTAO = frozenset({
    "Cartão de Crédito",
})

_CATEGORIAS_CONTA_FIXA = frozenset({
    "Celular",
    "Seguro",
})

_PREFIXOS_CONTA_FIXA = (
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
    "tim ",
    "claro",
    "vivo",
    "unifique",
    "celesc",
    "copel",
    "sabesp",
    "net ",
)

_KEYWORDS_ASSINATURA = (
    "netflix",
    "spotify",
    "youtube",
    "prime video",
    "hbo",
    "disney",
    "discovery",
    "apple.com",
    "apple combill",
    "google play",
    "microsoft",
    "sky",
    "deezer",
    "paramount",
    "crunchyroll",
    "udemy",
    "alura",
    "descomplica",
    "icloud",
    "dropbox",
    "notion",
    "chatgpt",
    "openai",
    "github",
    "adobe",
    "canva",
)

_RE_SEPARADORES = re.compile(r"[./\\\-_*|+]+")
_RE_SUFIXO_NUM = re.compile(r"\s+\d{2,}$")
_RE_SUFIXO_PARCELA = re.compile(r"\s+\d{1,2}/\d{1,2}$")
_RE_SUFIXO_RETICENCIAS = re.compile(r"\.{2,}$")
_RE_PREFIXOS_COBRANCA = re.compile(
    r"^(dm|google|apple|paypal|mercadopago|mp|amazon|msft|microsoft|help)\s+"
)

_ROTULOS_SERVICO: dict[str, str] = {
    "spotify": "Spotify",
    "youtube": "YouTube Premium",
    "netflix": "Netflix",
    "prime_video": "Prime Video",
    "hbo": "HBO Max",
    "disney": "Disney+",
    "discovery": "Discovery+",
    "deezer": "Deezer",
    "paramount": "Paramount+",
    "crunchyroll": "Crunchyroll",
    "udemy": "Udemy",
    "alura": "Alura",
    "descomplica": "Descomplica",
    "icloud": "iCloud",
    "dropbox": "Dropbox",
    "notion": "Notion",
    "chatgpt": "ChatGPT",
    "openai": "OpenAI",
    "github": "GitHub",
    "adobe": "Adobe",
    "canva": "Canva",
    "apple.com": "Apple",
    "apple_combill": "Apple",
    "google_play": "Google Play",
    "microsoft": "Microsoft",
    "sky": "Sky",
}


def _extrair_servico_canonico(desc: str) -> str | None:
    """Extrai slug de serviço conhecido pra unificar variantes de fatura."""
    compacto = desc.replace(" ", "")
    for kw in sorted(_KEYWORDS_ASSINATURA, key=len, reverse=True):
        kw_compacto = kw.replace(" ", "")
        if kw in desc or kw_compacto in compacto:
            return f"svc:{kw.replace(' ', '_').replace('.', '_')}"
    return None


def _descricao_exibicao(chave: str, descricao: str) -> str:
    if not chave.startswith("svc:"):
        return descricao
    slug = chave[4:].replace("_", " ")
    return _ROTULOS_SERVICO.get(chave[4:], _ROTULOS_SERVICO.get(slug, slug.title()))


class TipoRecorrente(TypedDict):
    id: str
    label: str
    emoji: str
    ordem: int


TIPOS_RECORRENTE: dict[str, TipoRecorrente] = {
    "assinatura": {"id": "assinatura", "label": "Assinatura", "emoji": "📱", "ordem": 1},
    "conta_fixa": {"id": "conta_fixa", "label": "Conta fixa", "emoji": "🏠", "ordem": 2},
    "financiamento": {"id": "financiamento", "label": "Financiamento", "emoji": "🏦", "ordem": 3},
    "emprestimo": {"id": "emprestimo", "label": "Empréstimo", "emoji": "💰", "ordem": 4},
    "fatura_cartao": {"id": "fatura_cartao", "label": "Fatura de cartão", "emoji": "🧾", "ordem": 5},
    "educacao": {"id": "educacao", "label": "Educação", "emoji": "🎓", "ordem": 6},
    "doacao": {"id": "doacao", "label": "Doação / Dízimo", "emoji": "⛪", "ordem": 7},
    "compra_recorrente": {
        "id": "compra_recorrente",
        "label": "Compra recorrente",
        "emoji": "🛒",
        "ordem": 8,
    },
    "outro": {"id": "outro", "label": "Outro recorrente", "emoji": "📅", "ordem": 9},
}


def rotulo_tipo_recorrente(tipo_id: str) -> str:
    """Rótulo com emoji pra exibição na UI."""
    info = TIPOS_RECORRENTE.get(tipo_id, TIPOS_RECORRENTE["outro"])
    return f"{info['emoji']} {info['label']}"


def listar_tipos_recorrente() -> list[TipoRecorrente]:
    """Tipos ordenados para filtros e abas."""
    return sorted(TIPOS_RECORRENTE.values(), key=lambda t: t["ordem"])


def classificar_tipo_recorrente(descricao: str, categoria: str) -> str:
    """Infere o tipo de um padrão recorrente a partir de descrição + categoria."""
    desc = _normalizar(descricao)
    cat = (categoria or "").strip()

    if cat in _CATEGORIAS_FATURA_CARTAO or (
        "fatura" in desc and ("mensal" in desc or "cartao" in desc or "cartão" in desc)
    ):
        return "fatura_cartao"

    if cat in _CATEGORIAS_FINANCIAMENTO or desc.startswith("financiamento"):
        return "financiamento"

    if cat in _CATEGORIAS_EMPRESTIMO or desc.startswith(("empréstimo", "emprestimo")):
        return "emprestimo"

    if cat in _CATEGORIAS_DOACAO or desc.startswith(("dízimo", "dizimo")):
        return "doacao"

    if cat in _CATEGORIAS_EDUCACAO or any(
        p in desc for p in ("faculdade", "escola", "universidade", "mensalidade", "uninter")
    ):
        return "educacao"

    if cat in _CATEGORIAS_ASSINATURA or any(kw in desc for kw in _KEYWORDS_ASSINATURA):
        return "assinatura"

    if cat in _CATEGORIAS_CONTA_FIXA or any(desc.startswith(p) for p in _PREFIXOS_CONTA_FIXA):
        return "conta_fixa"

    if cat in _CATEGORIAS_COMPRA:
        return "compra_recorrente"

    return "outro"


def chave_merchant(descricao: str) -> str:
    """Normaliza descrição para agrupar variantes do mesmo comerciante."""
    base = _normalizar(descricao)
    base = _RE_SEPARADORES.sub(" ", base)
    base = " ".join(base.split())
    base = _RE_SUFIXO_RETICENCIAS.sub("", base).strip()

    servico = _extrair_servico_canonico(base)
    if servico:
        return servico

    base = _RE_SUFIXO_PARCELA.sub("", base)
    base = _RE_SUFIXO_NUM.sub("", base)
    base = _RE_PREFIXOS_COBRANCA.sub("", base).strip()
    return base


def _resolver_colunas(df: pd.DataFrame) -> dict[str, str]:
    """Mapeia nomes canônicos → colunas reais do DataFrame."""
    if "descricao" in df.columns:
        return {
            "descricao": "descricao",
            "valor": "valor",
            "referencia": "referencia_mes",
            "categoria": "categoria",
            "conta": "conta",
            "tipo": "tipo",
            "parcela": "parcela",
        }
    return {
        "descricao": "Descrição",
        "valor": "Valor (R$)",
        "referencia": "Referência",
        "categoria": "Categoria",
        "conta": "Cartão",
        "tipo": "Tipo",
        "parcela": "Parcela",
    }


def _preparar_gastos(df: pd.DataFrame, cols: dict[str, str]) -> pd.DataFrame:
    """Filtra despesas positivas sem parcelamento e adiciona `_chave`."""
    if df.empty:
        return df

    sub = df.copy()
    if cols["tipo"] in sub.columns:
        sub = sub[sub[cols["tipo"]] == "despesa"]
    sub = sub[sub[cols["valor"]] > 0]

    if cols["parcela"] in sub.columns:
        sub = sub[sub[cols["parcela"]].astype(str).str.strip() == ""]

    sub["_chave"] = sub[cols["descricao"]].astype(str).map(chave_merchant)
    return sub[sub["_chave"] != ""]


def detectar_recorrentes(
    df: pd.DataFrame,
    *,
    meses_min: int = 3,
    meses_min_assinatura: int = 2,
) -> pd.DataFrame:
    """Agrupa padrões de gasto que se repetem em vários meses.

    Retorna DataFrame com colunas:
      chave, descricao, categoria, contas, meses, qtde, total,
      media_mensal, valor_min, valor_max, variacao_pct, assinatura
    """
    cols = _resolver_colunas(df)
    gastos = _preparar_gastos(df, cols)
    if gastos.empty:
        return pd.DataFrame()

    agg = (
        gastos.groupby("_chave", as_index=False)
        .agg(
            descricao=(cols["descricao"], lambda s: s.mode().iat[0] if not s.mode().empty else s.iloc[0]),
            categoria=(cols["categoria"], lambda s: s.mode().iat[0] if not s.mode().empty else ""),
            contas=(cols["conta"], lambda s: ", ".join(sorted({str(v) for v in s if str(v).strip()}))),
            meses=(cols["referencia"], "nunique"),
            qtde=(cols["valor"], "count"),
            total=(cols["valor"], "sum"),
            valor_min=(cols["valor"], "min"),
            valor_max=(cols["valor"], "max"),
        )
    )
    agg["media_mensal"] = agg["total"] / agg["meses"]

    def _variacao(row: pd.Series) -> float:
        if row["valor_min"] <= 0:
            return 0.0
        return round((row["valor_max"] - row["valor_min"]) / row["valor_min"] * 100, 1)

    agg["variacao_pct"] = agg.apply(_variacao, axis=1)
    agg["descricao_fatura"] = agg["descricao"]
    agg["descricao"] = agg.apply(
        lambda row: _descricao_exibicao(row["_chave"], row["descricao"]),
        axis=1,
    )
    agg["tipo_recorrente"] = agg.apply(
        lambda row: classificar_tipo_recorrente(row["descricao"], row["categoria"]),
        axis=1,
    )
    agg["assinatura"] = agg["tipo_recorrente"] == "assinatura"

    limites = agg["tipo_recorrente"].map(
        lambda t: meses_min_assinatura if t == "assinatura" else meses_min
    )
    agg = agg[agg["meses"] >= limites].copy()
    if agg.empty:
        return pd.DataFrame()

    return agg.rename(columns={"_chave": "chave"}).sort_values(
        ["total", "meses"], ascending=[False, False]
    ).reset_index(drop=True)


def marcar_recorrentes(
    df: pd.DataFrame,
    *,
    meses_min: int = 3,
    meses_min_assinatura: int = 2,
) -> pd.DataFrame:
    """Adiciona `eh_recorrente`, `grupo_recorrente` e `tipo_recorrente`."""
    if df.empty:
        out = df.copy()
        out["eh_recorrente"] = False
        out["grupo_recorrente"] = ""
        out["tipo_recorrente"] = ""
        return out

    cols = _resolver_colunas(df)
    padroes = detectar_recorrentes(
        df, meses_min=meses_min, meses_min_assinatura=meses_min_assinatura
    )
    out = df.copy()
    out["eh_recorrente"] = False
    out["grupo_recorrente"] = ""
    out["tipo_recorrente"] = ""

    if padroes.empty:
        return out

    chave_para_desc = dict(zip(padroes["chave"], padroes["descricao"], strict=False))
    chave_para_tipo = dict(zip(padroes["chave"], padroes["tipo_recorrente"], strict=False))
    chaves_recorrentes = set(chave_para_desc)

    out["_chave"] = out[cols["descricao"]].astype(str).map(chave_merchant)
    mascara = out["_chave"].isin(chaves_recorrentes)

    if cols["tipo"] in out.columns:
        mascara &= out[cols["tipo"]] == "despesa"
    mascara &= out[cols["valor"]] > 0
    if cols["parcela"] in out.columns:
        mascara &= out[cols["parcela"]].astype(str).str.strip() == ""

    out.loc[mascara, "eh_recorrente"] = True
    out.loc[mascara, "grupo_recorrente"] = out.loc[mascara, "_chave"].map(chave_para_desc)
    out.loc[mascara, "tipo_recorrente"] = out.loc[mascara, "_chave"].map(chave_para_tipo)
    return out.drop(columns=["_chave"])


def construir_recorrentes_excel(
    df_transacoes: pd.DataFrame,
    meses_min: int = 3,
) -> pd.DataFrame:
    """Formato da aba Recorrentes do Excel (compat com export legado)."""
    padroes = detectar_recorrentes(df_transacoes, meses_min=meses_min)
    if padroes.empty:
        return pd.DataFrame()

    visivel = padroes.copy()
    visivel["Tipo"] = visivel["tipo_recorrente"].map(rotulo_tipo_recorrente)
    return visivel.rename(
        columns={
            "descricao": "Descrição",
            "categoria": "Categoria",
            "contas": "Cartão(ões)",
            "meses": "Meses",
            "qtde": "Qtde. Transações",
            "total": "Total (R$)",
            "media_mensal": "Média Mensal (R$)",
        }
    )[
        [
            "Tipo",
            "Descrição",
            "Categoria",
            "Cartão(ões)",
            "Meses",
            "Qtde. Transações",
            "Total (R$)",
            "Média Mensal (R$)",
        ]
    ]


def historico_mensal_padrao(
    df: pd.DataFrame,
    chave: str,
) -> pd.DataFrame:
    """Série mensal de um padrão recorrente (pra drill-down na UI)."""
    cols = _resolver_colunas(df)
    gastos = _preparar_gastos(df, cols)
    if gastos.empty:
        return pd.DataFrame()

    sub = gastos[gastos["_chave"] == chave]
    if sub.empty:
        return pd.DataFrame()

    serie = (
        sub.groupby(cols["referencia"], as_index=False)[cols["valor"]]
        .sum()
        .rename(columns={cols["referencia"]: "referencia_mes", cols["valor"]: "valor"})
        .sort_values("referencia_mes")
    )
    return serie.reset_index(drop=True)


def listar_lancamentos_padrao(
    df: pd.DataFrame,
    chave: str,
) -> pd.DataFrame:
    """Lançamentos individuais que compõem um padrão recorrente."""
    cols = _resolver_colunas(df)
    gastos = _preparar_gastos(df, cols)
    if gastos.empty:
        return pd.DataFrame()

    sub = gastos[gastos["_chave"] == chave].copy()
    if sub.empty:
        return pd.DataFrame()

    resultado = sub.drop(columns=["_chave"], errors="ignore")
    ordem = [
        "data",
        cols["referencia"],
        cols["descricao"],
        cols["valor"],
        cols["categoria"],
        cols["conta"],
    ]
    ordem = [c for c in ordem if c in resultado.columns]
    return resultado[ordem].sort_values(cols["referencia"], ascending=True).reset_index(drop=True)
