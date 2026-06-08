"""Estado persistente dos filtros da UI Streamlit.

Resolve duas dores:

1. **Cada página tinha keys próprias** (`dashboard_ano`, `categorias_ano`)
   então mudar o ano no Dashboard não refletia em Categorias. Aqui
   exponho chaves **globais** (`filtro_global_ano`, `filtro_global_mes`,
   `filtro_global_modo`) que Dashboard + Categorias + Lançamentos
   compartilham.

2. **Filtros eram perdidos ao recarregar (F5)**. Agora todos os filtros
   também viajam em `st.query_params` — `?ano=2024&mes=2024-05` —
   sobrevivem a reload e tornam o link compartilhável.

Convenção: a página chama `hidratar_session_state(...)` antes dos
widgets (lê URL → popula `session_state`) e
`persistir_em_url(...)` depois (espelha `session_state` → URL,
idempotente — não dispara rerun se nada mudou).

Listas (multiselect) usam separador `|`, e.g.
`?lanc_pessoas=Eliabe%20Gai|Ana%20Leticia`.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

import streamlit as st

# ───────────────────────────────────────────────────────────────────
# Filtros globais — Dashboard, Categorias e Lançamentos compartilham
# ───────────────────────────────────────────────────────────────────
CHAVE_ANO = "filtro_global_ano"
CHAVE_MES = "filtro_global_mes"
CHAVE_MODO = "filtro_global_modo"

MAPA_GLOBAIS: dict[str, str] = {
    CHAVE_ANO: "ano",
    CHAVE_MES: "mes",
    CHAVE_MODO: "modo",
}

TIPOS_GLOBAIS: dict[str, Literal["str", "int", "list"]] = {
    # Ano é armazenado como string no `session_state` porque o
    # `st.selectbox` lida com strings nas opções. A conversão pra
    # `int` é feita no consumer (`selecionar_ano`).
    CHAVE_ANO: "str",
    CHAVE_MES: "str",
    CHAVE_MODO: "str",
}

CHAVES_GLOBAIS = tuple(MAPA_GLOBAIS.keys())

# ───────────────────────────────────────────────────────────────────
# Filtros da página Lançamentos (sidebar) — por página
# ───────────────────────────────────────────────────────────────────
CHAVE_LANC_PESSOAS = "f_pessoas"
CHAVE_LANC_CONTAS = "f_contas"
CHAVE_LANC_CATS = "f_cats"
CHAVE_LANC_TIPOS = "f_tipos"
CHAVE_LANC_REFS = "f_refs"
CHAVE_LANC_TEXTO = "f_texto"
CHAVE_LANC_DATA = "f_data"

MAPA_LANCAMENTOS: dict[str, str] = {
    CHAVE_LANC_PESSOAS: "lanc_pessoas",
    CHAVE_LANC_CONTAS: "lanc_contas",
    CHAVE_LANC_CATS: "lanc_cats",
    CHAVE_LANC_TIPOS: "lanc_tipos",
    CHAVE_LANC_REFS: "lanc_refs",
    CHAVE_LANC_TEXTO: "lanc_texto",
}

TIPOS_LANCAMENTOS: dict[str, Literal["str", "int", "list"]] = {
    CHAVE_LANC_PESSOAS: "list",
    CHAVE_LANC_CONTAS: "list",
    CHAVE_LANC_CATS: "list",
    CHAVE_LANC_TIPOS: "list",
    CHAVE_LANC_REFS: "list",
    CHAVE_LANC_TEXTO: "str",
}

CHAVES_LANCAMENTOS = tuple(MAPA_LANCAMENTOS.keys()) + (CHAVE_LANC_DATA,)

# ───────────────────────────────────────────────────────────────────
# Serialização de listas em URL
# ───────────────────────────────────────────────────────────────────
SEP_MULTI = "|"


def serializar_lista(valores: Iterable[str]) -> str:
    """Junta lista de strings num único valor de URL: `['A', 'B'] → 'A|B'`."""
    return SEP_MULTI.join(v for v in valores if v)


def deserializar_lista(s: str | None) -> list[str]:
    """Quebra string de URL em lista (vazia se input vazio/None)."""
    if not s:
        return []
    return [item for item in s.split(SEP_MULTI) if item]


# ───────────────────────────────────────────────────────────────────
# Hidratação: URL → session_state
# ───────────────────────────────────────────────────────────────────
def hidratar_session_state(
    mapeamento: dict[str, str],
    tipos: dict[str, Literal["str", "int", "list"]] | None = None,
) -> None:
    """Lê `st.query_params` e popula `st.session_state` (uma vez por sessão).

    Skipa chaves que já estão em `session_state` — usuário pode ter mexido
    nos widgets nesta sessão; URL é só seed inicial. Pra forçar
    re-hidratação (ex.: após "Limpar filtros"), o caller deve `pop()`
    as chaves antes de chamar esta função.
    """
    tipos = tipos or {}
    qp = st.query_params
    for chave, param in mapeamento.items():
        if chave in st.session_state:
            continue
        if param not in qp:
            continue
        valor_bruto = qp[param]
        tipo = tipos.get(chave, "str")
        if tipo == "list":
            st.session_state[chave] = deserializar_lista(valor_bruto)
        elif tipo == "int":
            try:
                st.session_state[chave] = int(valor_bruto)
            except (ValueError, TypeError):
                continue
        else:
            st.session_state[chave] = valor_bruto


# ───────────────────────────────────────────────────────────────────
# Persistência: session_state → URL (idempotente)
# ───────────────────────────────────────────────────────────────────
def _valor_pra_url(
    valor: object, tipo: Literal["str", "int", "list"]
) -> str | None:
    """Converte um valor do `session_state` em string da URL (ou `None`
    pra remover o param)."""
    if valor is None or valor == "":
        return None
    if tipo == "list":
        if not valor:
            return None
        assert isinstance(valor, list | tuple)
        s = serializar_lista(str(v) for v in valor)
        return s or None
    return str(valor)


def persistir_em_url(
    mapeamento: dict[str, str],
    tipos: dict[str, Literal["str", "int", "list"]] | None = None,
) -> None:
    """Espelha `session_state` em `st.query_params`. Idempotente.

    Preserva params que **não** estão no `mapeamento` (de outras
    páginas/features) — só mexe nos que esse caller declara controlar.
    """
    tipos = tipos or {}
    atual: dict[str, str] = dict(st.query_params)
    novo = dict(atual)

    for chave, param in mapeamento.items():
        tipo = tipos.get(chave, "str")
        valor_url = _valor_pra_url(st.session_state.get(chave), tipo)
        if valor_url is None:
            novo.pop(param, None)
        else:
            novo[param] = valor_url

    if novo == atual:
        return

    # `clear()` + reatribuir é o jeito documentado de fazer set em
    # batch sem disparar reruns extras.
    st.query_params.clear()
    for k, v in novo.items():
        st.query_params[k] = v


# ───────────────────────────────────────────────────────────────────
# Reset: limpa chaves do session_state E params da URL
# ───────────────────────────────────────────────────────────────────
def resetar(
    chaves_session_state: Iterable[str],
    params_url: Iterable[str] = (),
) -> None:
    """Limpa estado das chaves (no próximo rerun, widgets renderizam
    com seus defaults). Também tira os params correspondentes da URL.
    """
    for k in chaves_session_state:
        st.session_state.pop(k, None)
    if params_url:
        atual = dict(st.query_params)
        mudou = False
        for p in params_url:
            if p in atual:
                atual.pop(p)
                mudou = True
        if mudou:
            st.query_params.clear()
            for k, v in atual.items():
                st.query_params[k] = v


# ───────────────────────────────────────────────────────────────────
# Atalhos: chamadas comuns ficam de 1 linha nas páginas
# ───────────────────────────────────────────────────────────────────
def hidratar_globais() -> None:
    """Hidrata ano/mês/modo a partir da URL (uma vez por sessão)."""
    hidratar_session_state(MAPA_GLOBAIS, TIPOS_GLOBAIS)


def persistir_globais() -> None:
    """Escreve ano/mês/modo do session_state na URL."""
    persistir_em_url(MAPA_GLOBAIS, TIPOS_GLOBAIS)


def hidratar_lancamentos() -> None:
    """Hidrata filtros de tabela de lançamentos a partir da URL."""
    hidratar_session_state(MAPA_LANCAMENTOS, TIPOS_LANCAMENTOS)


def persistir_lancamentos() -> None:
    """Escreve filtros de tabela de lançamentos na URL."""
    persistir_em_url(MAPA_LANCAMENTOS, TIPOS_LANCAMENTOS)


def botao_limpar_filtros(
    chaves: Iterable[str],
    params_url: Iterable[str],
    *,
    label: str = "🧹 Limpar filtros",
    key: str,
    rotulo_auxiliar: str | None = None,
    na_sidebar: bool = False,
) -> bool:
    """Renderiza botão de reset. Devolve `True` se o usuário clicou
    (caller pode disparar `st.rerun()` ou ações adicionais).

    Já cuida do reset do `session_state` e da URL — o caller só
    precisa decidir se quer rerun explícito (geralmente sim).

    `na_sidebar=True` usa `st.sidebar.button` em vez de `st.button`.
    """
    botao = st.sidebar.button if na_sidebar else st.button
    clicado = botao(label, key=key, help=rotulo_auxiliar)
    if clicado:
        resetar(chaves, params_url)
    return clicado
