"""Pipelines de importação para o banco do gastometro.

- `migrar_excel_legado`: lê `saida/gastometro.xlsx` (formato atual da
  ferramenta CLI) e popula o banco, preservando categorias manuais.
  Roda 1 vez no upgrade pra Fase 1.
- (Fase 3) `importar_planilha_familiar`: lê `despesas_Eliabe_Ana.xlsx`
  (aba `Total`) e popula histórico anterior + receitas.
"""
