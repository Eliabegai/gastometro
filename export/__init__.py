"""Exportadores que regeram artefatos a partir do banco.

- `excel`: regera `saida/gastometro.xlsx` (mesmo schema/abas/gráficos
  do CLI atual), agora alimentado pelo banco. O Excel passa a ser
  uma view materializada do banco — read-only do ponto de vista da
  Fase 1+. Edições devem acontecer na UI Streamlit (Fase 2).
"""
