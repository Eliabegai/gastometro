"""Entrypoint do app Streamlit do gastometro.

Rodar:
    streamlit run app/streamlit_app.py

Navegação via `st.navigation` (Streamlit 1.30+): cada página é um
`st.Page` separado em `app/paginas/`. A sidebar mostra o menu
automaticamente; títulos/ícones definidos abaixo.

O entrypoint também garante que o schema exista (idempotente) — o
usuário pode abrir o app sem ter rodado a CLI antes.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

RAIZ = Path(__file__).resolve().parent
PAGINAS = RAIZ / "paginas"


def _bootstrap_banco() -> None:
    """Garante migrations aplicadas + seed inicial. No-op em re-runs."""
    from db.seed import seed_inicial

    seed_inicial()


def main() -> None:
    st.set_page_config(
        page_title="Gastômetro",
        page_icon="💸",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    _bootstrap_banco()

    paginas = [
        st.Page(
            str(PAGINAS / "dashboard.py"),
            title="Dashboard",
            icon=":material/dashboard:",
            default=True,
        ),
        st.Page(
            str(PAGINAS / "lancamentos.py"),
            title="Lançamentos",
            icon=":material/list_alt:",
        ),
        st.Page(
            str(PAGINAS / "faturas.py"),
            title="Faturas",
            icon=":material/receipt_long:",
        ),
        st.Page(
            str(PAGINAS / "categorias.py"),
            title="Categorias",
            icon=":material/sell:",
        ),
        st.Page(
            str(PAGINAS / "importar.py"),
            title="Importar",
            icon=":material/upload_file:",
        ),
    ]

    nav = st.navigation(paginas, position="sidebar")
    nav.run()


if __name__ == "__main__":
    main()
