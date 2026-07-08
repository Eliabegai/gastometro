"""Utilidades compartilhadas pelas páginas Streamlit.

- Formatação BR (moeda, datas, referência mes).
- Cache da consulta principal (lançamentos) usando `st.cache_data`
  com TTL curto (atualiza ao reimportar via CLI).
- Filtros canônicos aplicáveis a um DataFrame de lançamentos.
- Seletor de ano com default = ano corrente (evita exibir agregados
  do histórico inteiro, que distorcem KPIs).

Persistência de filtros: `selecionar_ano` e `selecionar_mes` usam
chaves canônicas em `app.estado` (`CHAVE_ANO`, `CHAVE_MES`) que
são compartilhadas entre páginas e sincronizadas com `st.query_params`
— ver `app/estado.py`.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from app.estado import CHAVE_ANO, CHAVE_LANC_DATA, CHAVE_MES, CHAVE_MODO
from db.repository import listar_faturas_df, listar_lancamentos_df
from parsers.base import MES_POR_NUMERO

MES_POR_NOME = {nome: num for num, nome in MES_POR_NUMERO.items()}

OPCAO_TODOS_ANOS = "Todos os anos"


def formatar_brl(valor: float | int) -> str:
    """`1.234,56` sem locale; preserva sinal."""
    s = f"{abs(valor):,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {s}" if valor < 0 else f"R$ {s}"


def formatar_brl_md(valor: float | int) -> str:
    """`formatar_brl` seguro para `st.markdown` / `st.caption` (escapa `$`)."""
    return formatar_brl(valor).replace("$", r"\$")


def ref_para_nome_br(iso: str | None) -> str:
    """'2026-05' → 'Maio/2026'. Aceita já formatado."""
    if not iso:
        return ""
    if "/" in iso:
        return iso
    if "-" not in iso:
        return iso
    try:
        ano, mes = iso.split("-", 1)
        nome = MES_POR_NUMERO.get(int(mes), mes)
        return f"{nome}/{ano}"
    except (ValueError, KeyError):
        return iso


def chave_ord_ref_iso(iso: str) -> tuple[int, int]:
    """Pra ordenar lista de referências `YYYY-MM` cronologicamente."""
    if not iso or "-" not in iso:
        return (0, 0)
    try:
        ano, mes = iso.split("-", 1)
        return (int(ano), int(mes))
    except ValueError:
        return (0, 0)


@st.cache_data(ttl=30, show_spinner="Lendo lançamentos do banco…")
def carregar_lancamentos(sinal_estorno_negativo: bool = True) -> pd.DataFrame:
    """Wrapper cacheado em torno de `listar_lancamentos_df`.

    TTL curto (30s) pra recarregar quase imediatamente quando o usuário
    rodar `gastometro` numa outra janela. Em telas críticas use
    `st.cache_data.clear()` ou recarregue a página.
    """
    return listar_lancamentos_df(sinal_estorno_negativo=sinal_estorno_negativo)


@st.cache_data(ttl=30, show_spinner="Lendo faturas do banco…")
def carregar_faturas() -> pd.DataFrame:
    return listar_faturas_df()


def aplicar_filtros(
    df: pd.DataFrame,
    *,
    pessoas: list[str] | None = None,
    contas: list[str] | None = None,
    categorias: list[str] | None = None,
    tipos: list[str] | None = None,
    referencias: list[str] | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    texto: str | None = None,
) -> pd.DataFrame:
    """Aplica filtros canônicos. Cada parâmetro é opcional/aditivo.

    `texto` é busca case-insensitive em `descricao` (substring).
    """
    if df is None or df.empty:
        return df
    sub = df
    if pessoas:
        sub = sub[sub["pessoa"].isin(pessoas)]
    if contas:
        sub = sub[sub["conta"].isin(contas)]
    if categorias:
        sub = sub[sub["categoria"].isin(categorias)]
    if tipos:
        sub = sub[sub["tipo"].isin(tipos)]
    if referencias:
        sub = sub[sub["referencia_mes"].isin(referencias)]
    if data_inicio is not None:
        sub = sub[sub["data"] >= data_inicio]
    if data_fim is not None:
        sub = sub[sub["data"] <= data_fim]
    if texto:
        mask = sub["descricao"].astype(str).str.contains(texto, case=False, na=False)
        if "grupo_recorrente" in sub.columns:
            mask = mask | sub["grupo_recorrente"].astype(str).str.contains(
                texto, case=False, na=False
            )
        sub = sub[mask]
    return sub


def anos_disponiveis(df: pd.DataFrame) -> list[int]:
    """Anos distintos presentes em `df['data']`, ordenados crescentemente."""
    if df is None or df.empty or "data" not in df.columns:
        return []
    datas = pd.to_datetime(df["data"], errors="coerce").dropna()
    if datas.empty:
        return []
    return sorted({int(d.year) for d in datas})


def ano_padrao(anos: list[int]) -> int | None:
    """Ano sugerido como filtro inicial.

    Regras:
      - Se o ano corrente está na lista → usa ele.
      - Senão, usa o maior ano presente (último com dados).
      - Se a lista está vazia → devolve `None`.
    """
    if not anos:
        return None
    atual = date.today().year
    return atual if atual in anos else anos[-1]


def selecionar_ano(
    df: pd.DataFrame,
    *,
    label: str = "Ano",
    key: str = CHAVE_ANO,
    permitir_todos: bool = True,
) -> int | None:
    """Renderiza selectbox de ano. Devolve o ano selecionado ou `None`
    (= ver todos os anos).

    Default `key=CHAVE_ANO` (chave global) faz com que mudanças aqui
    reflitam em todas as páginas. Se quiser um seletor local pra um
    contexto específico, passe `key="meu_widget"` explicitamente.

    Por padrão começa no ano corrente (ou no último ano com dados),
    evitando que KPIs e gráficos mostrem o acumulado do histórico
    inteiro logo de cara — o que torna comparações entre meses
    pouco úteis.

    Quando o `session_state[key]` (hidratado da URL) aponta pra um
    ano que **não existe mais no banco**, ignoramos silenciosamente
    e usamos o default — evita crash de `ValueError` no `.index()`.
    """
    anos = anos_disponiveis(df)
    if not anos:
        return None

    padrao = ano_padrao(anos)
    opcoes_label: list[str] = [str(a) for a in reversed(anos)]
    if permitir_todos:
        opcoes_label.append(OPCAO_TODOS_ANOS)

    # Se a key tem valor (hidratado da URL ou de session anterior) e ele
    # bate com uma opção atual, deixa o Streamlit usar — `index` será
    # ignorado. Se não bate, limpa pra cair no default.
    valor_atual = st.session_state.get(key)
    if valor_atual is not None:
        rotulo_atual = (
            OPCAO_TODOS_ANOS
            if valor_atual in (None, OPCAO_TODOS_ANOS)
            else str(valor_atual)
        )
        if rotulo_atual not in opcoes_label:
            st.session_state.pop(key, None)

    idx_default = (
        opcoes_label.index(str(padrao))
        if padrao is not None and str(padrao) in opcoes_label
        else 0
    )
    escolha = st.selectbox(label, opcoes_label, index=idx_default, key=key)
    if escolha == OPCAO_TODOS_ANOS:
        return None
    try:
        return int(escolha)
    except ValueError:
        return None


def filtrar_por_ano(df: pd.DataFrame, ano: int | None) -> pd.DataFrame:
    """Recorta `df` ao ano informado. `ano=None` → devolve `df` intocado."""
    if ano is None or df is None or df.empty or "data" not in df.columns:
        return df
    datas = pd.to_datetime(df["data"], errors="coerce")
    return df[datas.dt.year == ano]


# ───────────────────────────────────────────────────────────────────
# Período global (ano + mês + modo) — usado por TODAS as páginas
# ───────────────────────────────────────────────────────────────────
MODO_GLOBAL_ANUAL = "Ano inteiro"
MODO_GLOBAL_MENSAL = "Mensal"


def ano_global_atual() -> int | None:
    """Lê `session_state[CHAVE_ANO]` e devolve como int (ou `None` se
    'todos os anos' / inválido / não setado)."""
    valor = st.session_state.get(CHAVE_ANO)
    if not valor or valor == OPCAO_TODOS_ANOS:
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def mes_global_atual() -> str | None:
    """Lê `session_state[CHAVE_MES]` e devolve ISO (`2026-05`) ou `None`.

    Só é relevante quando o modo global é mensal — caller decide.
    """
    valor = st.session_state.get(CHAVE_MES)
    return valor if isinstance(valor, str) and valor else None


def modo_global_atual() -> str:
    """Lê `session_state[CHAVE_MODO]`. Default = anual."""
    valor = st.session_state.get(CHAVE_MODO)
    return valor if valor in (MODO_GLOBAL_ANUAL, MODO_GLOBAL_MENSAL) else MODO_GLOBAL_ANUAL


def filtrar_por_periodo_global(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica os filtros globais (ano + opcionalmente mês) ao DataFrame.

    Lê `CHAVE_ANO`, `CHAVE_MODO`, `CHAVE_MES` do `session_state`.
    Idempotente — se nenhuma chave está setada, devolve `df` intocado.

    Modo anual: filtra só pelo ano.
    Modo mensal: filtra ano + `referencia_mes == mes_global`.
    """
    if df is None or df.empty:
        return df

    ano = ano_global_atual()
    if ano is not None:
        df = filtrar_por_ano(df, ano)

    if modo_global_atual() == MODO_GLOBAL_MENSAL:
        mes = mes_global_atual()
        if mes and "referencia_mes" in df.columns:
            df = df[df["referencia_mes"] == mes]

    return df


def rotulo_periodo_global() -> str:
    """Descrição PT-BR do recorte ativo. Usar em banners/captions.

    Exemplos:
      - "todo o histórico"   (sem ano)
      - "ano 2024"           (modo anual)
      - "Maio/2024"          (modo mensal)
    """
    ano = ano_global_atual()
    if ano is None:
        return "todo o histórico"
    if modo_global_atual() == MODO_GLOBAL_MENSAL:
        mes = mes_global_atual()
        if mes:
            return ref_para_nome_br(mes)
    return f"ano {ano}"


def periodo_global_ativo() -> bool:
    """`True` se ano OU mês estão setados nos globais. Usar pra decidir
    se mostra o banner / é seguro escrever 'sem filtro'."""
    return ano_global_atual() is not None or (
        modo_global_atual() == MODO_GLOBAL_MENSAL
        and mes_global_atual() is not None
    )


def referencias_no_recorte(df: pd.DataFrame) -> list[str]:
    """Lista ordenada de `referencia_mes` (ISO `YYYY-MM`) presentes em `df`."""
    return referencias_disponiveis(df)


def selecionar_mes(
    df: pd.DataFrame,
    *,
    label: str = "Mês",
    key: str = CHAVE_MES,
) -> str | None:
    """Selectbox de referência mensal (ISO `YYYY-MM`) com label PT-BR.

    A `key` (default `CHAVE_MES`) guarda o **ISO** (`2026-05`) pra ficar
    estável e legível na URL. Internamente o widget usa uma key auxiliar
    `<key>__widget` pra guardar o rótulo PT-BR (`Maio/2026`), porque
    Streamlit não permite mexer em `session_state[key]` depois do widget
    com a mesma key — o padrão "mirror" resolve isso elegantemente.

    Default = último mês com dados no recorte. Devolve a referência ISO
    selecionada ou `None` se o recorte está vazio.

    Se `session_state[key]` apontar pra uma ref que não existe no recorte
    atual (ex.: hidratou URL `?mes=2020-01` num banco que só vai até
    2022), ignora silenciosamente.
    """
    refs = referencias_no_recorte(df)
    if not refs:
        return None
    opcoes_iso = list(reversed(refs))
    label_to_iso = {ref_para_nome_br(r): r for r in opcoes_iso}
    iso_to_label = {iso: lbl for lbl, iso in label_to_iso.items()}
    rotulos = list(label_to_iso.keys())

    widget_key = f"{key}__widget"

    # Mirror ISO → label SOMENTE se o widget ainda não foi inicializado
    # nesta sessão. Caso contrário, sobrescreveríamos a escolha que o
    # usuário acabou de fazer no rerun anterior — bug clássico: ao
    # clicar num mês, o widget "voltava" pro último valor persistido.
    if widget_key not in st.session_state:
        iso_persistente = st.session_state.get(key)
        if iso_persistente and iso_persistente in iso_to_label:
            st.session_state[widget_key] = iso_to_label[iso_persistente]
        elif iso_persistente and iso_persistente not in iso_to_label:
            # ISO inválido pra este recorte → limpa pra cair no default.
            st.session_state.pop(key, None)

    escolha = st.selectbox(label, rotulos, index=0, key=widget_key)
    iso = label_to_iso.get(escolha)
    if iso:
        st.session_state[key] = iso
    return iso


def referencias_disponiveis(df: pd.DataFrame) -> list[str]:
    """Lista única ordenada de `referencia_mes` (ISO `YYYY-MM`)."""
    if df is None or df.empty:
        return []
    refs = {str(r) for r in df["referencia_mes"].astype(str) if r and r != "nan"}
    return sorted(refs, key=chave_ord_ref_iso)


def _filtrar_opcoes_validas(
    chave: str, opcoes_validas: list[str]
) -> None:
    """Saneia `session_state[chave]` (lista) removendo valores que não estão
    em `opcoes_validas`. Útil pra filtros hidratados da URL com valores
    obsoletos (ex.: categoria foi renomeada no banco)."""
    atual = st.session_state.get(chave)
    if not atual:
        return
    if not isinstance(atual, list | tuple):
        return
    saneado = [v for v in atual if v in opcoes_validas]
    if saneado != list(atual):
        st.session_state[chave] = saneado


def sidebar_filtros_lancamentos(df: pd.DataFrame) -> dict[str, Any]:
    """Renderiza filtros padrão na sidebar e devolve dict pra `aplicar_filtros`.

    Inclui `key`s distintas por widget pra Streamlit preservar estado
    entre re-runs. As keys (`f_pessoas`, `f_contas`, …) estão mapeadas
    em `app.estado.MAPA_LANCAMENTOS` pra sincronizar com `st.query_params`.

    Antes do widget multi-select renderizar, saneamos os valores
    persistidos: se a URL trouxe uma categoria que não existe mais
    no banco, simplesmente removemos do filtro (sem warning).
    """
    st.sidebar.subheader("Filtros")

    pessoas_opts = sorted({p for p in df.get("pessoa", []) if p})
    contas_opts = sorted({c for c in df.get("conta", []) if c})
    categorias_opts = sorted({c for c in df.get("categoria", []) if c})
    tipos_opts = sorted({t for t in df.get("tipo", []) if t})
    # Referência mês: ordem **decrescente** (mais recente primeiro) pra
    # o usuário achar o mês atual sem rolar uma lista enorme de meses
    # antigos da planilha histórica.
    refs_opts = list(reversed(referencias_disponiveis(df)))
    refs_label = [ref_para_nome_br(r) for r in refs_opts]
    refs_label_to_iso = dict(zip(refs_label, refs_opts, strict=False))
    refs_iso_to_label = {iso: lbl for lbl, iso in refs_label_to_iso.items()}

    # As keys `f_refs` armazenam ISO (estável na URL). Convertemos
    # pra label PT-BR via key auxiliar `f_refs__widget` (mesmo padrão
    # do `selecionar_mes`).
    #
    # Mirror ISO → label SOMENTE na primeira renderização do widget
    # nesta sessão. Reaplicar a cada rerun sobrescreveria a seleção
    # que o usuário acabou de mudar.
    refs_widget_key = "f_refs__widget"
    if refs_widget_key not in st.session_state:
        refs_iso_persistido = st.session_state.get("f_refs") or []
        if isinstance(refs_iso_persistido, list | tuple):
            st.session_state[refs_widget_key] = [
                refs_iso_to_label[i]
                for i in refs_iso_persistido
                if i in refs_iso_to_label
            ]

    # Sanear listas hidratadas da URL antes de renderizar os widgets.
    _filtrar_opcoes_validas("f_pessoas", pessoas_opts)
    _filtrar_opcoes_validas("f_contas", contas_opts)
    _filtrar_opcoes_validas("f_cats", categorias_opts)
    _filtrar_opcoes_validas("f_tipos", tipos_opts)

    pessoas = st.sidebar.multiselect(
        "Pessoa", pessoas_opts, default=[], key="f_pessoas"
    )
    contas = st.sidebar.multiselect(
        "Conta / Cartão", contas_opts, default=[], key="f_contas"
    )
    categorias = st.sidebar.multiselect(
        "Categoria", categorias_opts, default=[], key="f_cats"
    )
    tipos = st.sidebar.multiselect(
        "Tipo", tipos_opts, default=[], key="f_tipos"
    )

    refs_sel_label = st.sidebar.multiselect(
        "Referência (mês)", refs_label, default=[], key=refs_widget_key
    )
    refs = [refs_label_to_iso[r] for r in refs_sel_label if r in refs_label_to_iso]
    # Espelha label → ISO no key persistente.
    st.session_state["f_refs"] = refs

    texto = st.sidebar.text_input(
        "Buscar descrição contém…", value="", key="f_texto"
    ).strip()

    data_inicio: date | None = None
    data_fim: date | None = None
    if not df.empty and "data" in df.columns:
        datas = pd.to_datetime(df["data"], errors="coerce").dropna()
        if not datas.empty:
            min_d = datas.min().date()
            max_d = datas.max().date()
            anos = anos_disponiveis(df)
            ano = ano_padrao(anos)
            # Default = ano corrente (clamp em min/max disponível) pra
            # não abrir mostrando o histórico inteiro.
            if ano is not None:
                inicio_default = max(date(ano, 1, 1), min_d)
                fim_default = min(date(ano, 12, 31), max_d)
            else:
                inicio_default, fim_default = min_d, max_d
            faixa = st.sidebar.date_input(
                "Período (data da transação)",
                value=(inicio_default, fim_default),
                min_value=min_d,
                max_value=max_d,
                key=CHAVE_LANC_DATA,
            )
            if isinstance(faixa, tuple) and len(faixa) == 2:
                data_inicio, data_fim = faixa

    return {
        "pessoas": pessoas,
        "contas": contas,
        "categorias": categorias,
        "tipos": tipos,
        "referencias": refs,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "texto": texto or None,
    }


def invalidar_cache() -> None:
    """Esvazia cache do `st.cache_data` — usar após mutações no banco."""
    carregar_lancamentos.clear()
    carregar_faturas.clear()
