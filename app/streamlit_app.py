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

import sys
from pathlib import Path

# Streamlit só adiciona `app/` ao sys.path — imports `from app.*` e
# `from db.*` precisam da raiz do projeto (Docker usa PYTHONPATH=/app).
_RAIZ_PROJETO = Path(__file__).resolve().parents[1]
if str(_RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_PROJETO))

from dotenv import load_dotenv

load_dotenv(_RAIZ_PROJETO / ".env", override=False)

import streamlit as st

from app.auth import exigir_acesso, renderizar_barra_usuario

RAIZ = Path(__file__).resolve().parent
PAGINAS = RAIZ / "paginas"


def _bootstrap_banco() -> None:
    """Garante migrations aplicadas + seed inicial. No-op em re-runs."""
    if st.session_state.get("_gastometro_bootstrap_ok"):
        return
    from db.seed import seed_inicial

    seed_inicial()
    st.session_state["_gastometro_bootstrap_ok"] = True


def main() -> None:
    st.set_page_config(
        page_title="Gastômetro",
        page_icon="💸",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    exigir_acesso()
    _bootstrap_banco()
    renderizar_barra_usuario()

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
            str(PAGINAS / "recorrentes.py"),
            title="Recorrentes",
            icon=":material/autorenew:",
        ),
        st.Page(
            str(PAGINAS / "orcamento.py"),
            title="Orçamento",
            icon=":material/savings:",
        ),
        st.Page(
            str(PAGINAS / "casal.py"),
            title="Casal",
            icon=":material/favorite:",
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
