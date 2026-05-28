"""Página Importar — upload de PDFs e sincronização da planilha familiar.

Dois blocos:
  - **PDFs de fatura**: reusa `_importar_pdfs.render_uploader`.
  - **Planilha familiar (Google Sheets)**: cola a URL pública uma vez e
    daí pra frente é um clique pra rebaixar e re-importar.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.helpers import invalidar_cache
from app.paginas._importar_pdfs import render_uploader
from imports.baixar_planilha_familiar import (
    baixar,
    salvar_url,
    url_salva,
)
from imports.importar_planilha_familiar import migrar


def _render_planilha_familiar() -> None:
    st.subheader("📊 Planilha familiar (Google Sheets)")
    st.caption(
        "Cole a URL da planilha (no Google Sheets: **Compartilhar → "
        "Qualquer pessoa com o link pode ver**) e clique em "
        "**Atualizar do Google Sheets**. Da próxima vez, a URL fica "
        "salva e basta o clique no botão."
    )

    valor_inicial = url_salva()
    url_input = st.text_input(
        "URL da planilha",
        value=valor_inicial,
        placeholder="https://docs.google.com/spreadsheets/d/.../edit",
        key="planilha_url",
        help=(
            "Aceita tanto a URL de edição (`.../edit#gid=...`) quanto "
            "a URL de export (`.../export?format=xlsx`)."
        ),
    )

    col_a, col_b = st.columns(2)
    with col_a:
        regerar_xlsx = st.checkbox(
            "Regenerar `saida/gastometro.xlsx` após importar",
            value=False,
            key="planilha_regerar_xlsx",
        )
    with col_b:
        rodar_import = st.checkbox(
            "Importar para o banco após baixar",
            value=True,
            key="planilha_rodar_import",
            help=(
                "Se desligado, só baixa o arquivo XLSX em `dados/` (útil "
                "pra inspecionar antes de importar)."
            ),
        )

    if st.button(
        "🔄 Atualizar do Google Sheets",
        type="primary",
        disabled=not url_input.strip(),
        key="btn_baixar_planilha",
    ):
        with st.spinner("Baixando planilha do Google Sheets…"):
            try:
                salvar_url(url_input)
                destino: Path = baixar(url_input)
            except (RuntimeError, ValueError) as exc:
                st.error(f"Falha ao baixar: {exc}")
                return
        # Mostra caminho relativo se possível (mais legível na UI).
        try:
            caminho_amigavel = str(destino.relative_to(Path.cwd()))
        except ValueError:
            caminho_amigavel = str(destino)
        st.success(f"Planilha salva em `{caminho_amigavel}`")

        if not rodar_import:
            st.info(
                "Download concluído. Marque **Importar para o banco** "
                "ou rode `python -m imports.importar_planilha_familiar` "
                "quando quiser carregar os dados."
            )
            return

        with st.spinner("Importando linhas no banco…"):
            try:
                resultado = migrar(destino)
            except (FileNotFoundError, ValueError) as exc:
                st.error(f"Falha ao importar: {exc}")
                return

        invalidar_cache()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Linhas processadas", resultado.linhas_processadas)
        c2.metric("Lançamentos novos", resultado.inseridos)
        c3.metric("Duplicados (skip)", resultado.duplicados)
        c4.metric(
            "Ignoradas / desconhecidas",
            resultado.linhas_ignoradas + len(resultado.linhas_desconhecidas),
        )

        if resultado.pulados_cartao_pdf:
            st.caption(
                f"💡 {resultado.pulados_cartao_pdf} célula(s) de cartão "
                "pulada(s) porque já existe a fatura PDF correspondente."
            )

        if resultado.linhas_desconhecidas:
            with st.expander("Linhas com nome desconhecido (não importadas)"):
                st.write(sorted(set(resultado.linhas_desconhecidas)))

        if regerar_xlsx and resultado.inseridos > 0:
            from export.excel import regenerar_planilha_do_banco

            destino_xlsx = Path("saida") / "gastometro.xlsx"
            destino_xlsx.parent.mkdir(parents=True, exist_ok=True)
            regenerar_planilha_do_banco(destino_xlsx)
            st.success(f"Excel regenerado: `{destino_xlsx}`")


def render() -> None:
    st.title("📥 Importar")
    st.caption(
        "Duas fontes de dados: PDFs de fatura (extraídos por parser) e a "
        "planilha familiar do Google Sheets (categorias x meses)."
    )

    st.subheader("📄 PDFs de fatura")
    render_uploader(key_prefix="pagina_importar_pdfs")

    st.divider()
    _render_planilha_familiar()


render()
