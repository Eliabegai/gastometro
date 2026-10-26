"""Visão resumida (celular): menos blocos, métricas em 2 colunas.

O Streamlit não informa o tamanho da tela ao servidor, então a escolha é
um toggle. O estado vai para a URL (`?resumo=1`), então dá para salvar o
link com a visão resumida como atalho na tela inicial do celular.
"""

from __future__ import annotations

import streamlit as st

CHAVE_RESUMO = "visao_resumida"
PARAM_RESUMO = "resumo"


def alternar_resumo() -> bool:
    """Renderiza o toggle e devolve `True` se a visão resumida está ligada."""
    if CHAVE_RESUMO not in st.session_state:
        st.session_state[CHAVE_RESUMO] = st.query_params.get(PARAM_RESUMO) == "1"
    ligado = st.toggle(
        "Visão resumida (celular)",
        key=CHAVE_RESUMO,
        help="Mostra só o essencial, em colunas menores. "
        "O link guarda a escolha (?resumo=1).",
    )
    atual = st.query_params.get(PARAM_RESUMO)
    if ligado and atual != "1":
        st.query_params[PARAM_RESUMO] = "1"
    elif not ligado and atual is not None:
        del st.query_params[PARAM_RESUMO]
    return bool(ligado)


def colunas(n: int, resumido: bool) -> list:
    """`n` colunas lado a lado, ou em linhas de 2 na visão resumida."""
    if not resumido:
        return list(st.columns(n))
    saida: list = []
    restante = n
    while restante > 0:
        por_linha = min(2, restante)
        saida.extend(st.columns(por_linha))
        restante -= por_linha
    return saida
