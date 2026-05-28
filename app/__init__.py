"""Interface web Streamlit do gastometro (Fase 2+).

Entrypoint: `app/streamlit_app.py` (rodar via `streamlit run`).

Estrutura:
  - `streamlit_app.py`: navegacao + theme + roteamento das paginas.
  - `paginas/`: uma pagina por arquivo (Dashboard, Lancamentos,
    Faturas, Categorias).
  - `helpers.py`: utilidades compartilhadas (formatacao BRL,
    filtros, conversao referencia ISO→PT).
"""
