"""
Extrator de fatura em PDF -> Excel.

Detecta automaticamente o banco emissor (Ailos, Nubank ou Banco do Brasil)
e gera uma planilha com metadados (banco, titular, referência, fechamento,
vencimento), lançamentos categorizados e resumo por categoria.

Uso:
    python extrator.py                       # processa todos os PDFs da pasta atual
    python extrator.py Fatura_05_2026.pdf    # processa um PDF específico
    python extrator.py pasta/                # processa todos os PDFs de uma pasta
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from parsers import Fatura, extrair_fatura


def exportar_excel(fatura: Fatura, destino: Path) -> None:
    """Exporta a fatura para um arquivo Excel com 3 abas: Informações, Transações, Resumo."""
    if not fatura.transacoes:
        print(f"  Nenhuma transação encontrada em {destino.stem}.")
        return

    meta = fatura.metadata

    df_transacoes = pd.DataFrame(
        [
            {
                "Banco": meta.banco,
                "Titular": meta.titular,
                "Referência": meta.referencia_mes,
                "Data": t.data,
                "Descrição": t.descricao,
                "Parcela": t.parcela,
                "Cidade": t.cidade,
                "Valor (R$)": t.valor,
                "Categoria": t.categoria,
            }
            for t in fatura.transacoes
        ]
    )
    df_transacoes["_data_ord"] = pd.to_datetime(
        df_transacoes["Data"], format="%d/%m/%Y", errors="coerce"
    )
    df_transacoes = (
        df_transacoes.sort_values("_data_ord", kind="stable")
        .drop(columns="_data_ord")
        .reset_index(drop=True)
    )

    df_info = pd.DataFrame(
        [
            {"Campo": "Banco", "Valor": meta.banco},
            {"Campo": "Titular", "Valor": meta.titular},
            {"Campo": "Referência", "Valor": meta.referencia_mes},
            {"Campo": "Data de fechamento", "Valor": meta.data_fechamento},
            {"Campo": "Data de vencimento", "Valor": meta.data_vencimento},
            {"Campo": "Valor total da fatura (R$)", "Valor": meta.valor_total},
            {"Campo": "Qtde. de transações", "Valor": len(fatura.transacoes)},
        ]
    )

    resumo = (
        df_transacoes.groupby("Categoria", as_index=False)["Valor (R$)"]
        .sum()
        .sort_values("Valor (R$)", ascending=False)
        .reset_index(drop=True)
    )
    total_geral = pd.DataFrame(
        [{"Categoria": "TOTAL GERAL", "Valor (R$)": resumo["Valor (R$)"].sum()}]
    )
    resumo = pd.concat([resumo, total_geral], ignore_index=True)

    with pd.ExcelWriter(destino, engine="openpyxl") as writer:
        df_info.to_excel(writer, sheet_name="Informações", index=False)
        df_transacoes.to_excel(writer, sheet_name="Transações", index=False)
        resumo.to_excel(writer, sheet_name="Resumo por Categoria", index=False)

        _formatar_planilha(writer, "Informações", df_info)
        _formatar_planilha(writer, "Transações", df_transacoes)
        _formatar_planilha(writer, "Resumo por Categoria", resumo)

    print(f"  Excel gerado: {destino}")


def _formatar_planilha(writer, nome_aba: str, df: pd.DataFrame) -> None:
    aba = writer.sheets[nome_aba]

    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    for col_idx in range(1, len(df.columns) + 1):
        cell = aba.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    colunas_valor = [c for c in df.columns if "Valor" in c]
    for coluna_valor in colunas_valor:
        col_idx = df.columns.get_loc(coluna_valor) + 1
        for row in range(2, len(df) + 2):
            celula = aba.cell(row=row, column=col_idx)
            if isinstance(celula.value, (int, float)):
                celula.number_format = 'R$ #,##0.00'

    for col_idx, coluna in enumerate(df.columns, start=1):
        valores = [str(v) for v in df[coluna].astype(str).tolist()] + [str(coluna)]
        largura = min(max(len(v) for v in valores) + 2, 60)
        aba.column_dimensions[get_column_letter(col_idx)].width = largura

    aba.freeze_panes = "A2"


def _descobrir_pdfs(alvo: Path | None) -> list[Path]:
    base = alvo if alvo else Path.cwd()
    if base.is_file() and base.suffix.lower() == ".pdf":
        return [base]
    if base.is_dir():
        return sorted(base.glob("*.pdf"))
    print(f"Caminho inválido: {base}")
    return []


def processar(pdfs: Iterable[Path]) -> None:
    for pdf in pdfs:
        print(f"\nProcessando: {pdf.name}")
        try:
            fatura = extrair_fatura(pdf)
        except Exception as exc:
            print(f"  Erro ao ler {pdf.name}: {exc}")
            continue
        meta = fatura.metadata
        print(
            f"  Banco: {meta.banco} | Titular: {meta.titular or '—'} | "
            f"Referência: {meta.referencia_mes or '—'}"
        )
        print(
            f"  Fechamento: {meta.data_fechamento or '—'} | "
            f"Vencimento: {meta.data_vencimento or '—'}"
        )
        print(f"  {len(fatura.transacoes)} transações encontradas.")
        destino = pdf.with_suffix(".xlsx")
        exportar_excel(fatura, destino)


def main() -> None:
    alvo = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else None
    pdfs = _descobrir_pdfs(alvo)
    if not pdfs:
        print("Nenhum PDF encontrado. Aponte para um arquivo .pdf ou pasta com PDFs.")
        sys.exit(1)
    processar(pdfs)
    print("\nConcluído.")


if __name__ == "__main__":
    main()
