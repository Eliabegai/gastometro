"""Páginas Streamlit do gastometro.

Cada arquivo é uma `st.Page` registrada em `app/streamlit_app.py`.
Páginas dependem só de `db.repository` (não do filesystem do Excel),
então funcionam mesmo se o XLSX legado não existir.
"""
