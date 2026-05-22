"""
Extrator de fatura em PDF -> Excel acumulativo.

Fluxo padrão:
  1. Coloque os PDFs em `entrada/` (criada automaticamente na 1ª execução).
  2. Rode `python extrator.py`.
  3. Resultado em `saida/gastometro.xlsx` (Excel único, acumulativo entre execuções).

Faturas com o mesmo nome de arquivo já registrado no Excel são ignoradas
(para re-processar uma fatura, abra o Excel e remova a linha dela na aba
"Informações" antes de rodar novamente).

Uso:
    python extrator.py                       # processa todos os PDFs de `entrada/`
    python extrator.py Fatura.pdf            # processa um PDF específico
    python extrator.py pasta/                # processa todos os PDFs de outra pasta
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from parsers import Fatura, extrair_fatura
from parsers.base import MES_POR_NUMERO


RAIZ = Path(__file__).parent
PASTA_ENTRADA = RAIZ / "entrada"
PASTA_SAIDA = RAIZ / "saida"
ARQUIVO_SAIDA = "gastometro.xlsx"

COLUNAS_INFO = [
    "Arquivo",
    "Banco",
    "Titular",
    "Referência",
    "Data de fechamento",
    "Data de vencimento",
    "Valor total (R$)",
    "Qtde. de transações",
]

COLUNAS_TRANSACOES = [
    "Arquivo",
    "Banco",
    "Titular",
    "Referência",
    "Data",
    "Descrição",
    "Parcela",
    "Cidade",
    "Valor (R$)",
    "Categoria",
]

MES_POR_NOME = {nome: num for num, nome in MES_POR_NUMERO.items()}

TOLERANCIA_TOTAL = 0.01


def _conciliar_total(fatura: Fatura) -> None:
    """Compara o total extraído do PDF com a soma das transações.

    - Se o parser não conseguiu extrair o total (`valor_total == 0`),
      preenche com a soma e avisa que estamos confiando só na soma.
    - Se há total extraído mas ele diverge da soma além de `TOLERANCIA_TOTAL`,
      imprime um aviso (provável lançamento não capturado pelo parser).
    - Caso contrário, fica em silêncio.
    """
    meta = fatura.metadata
    soma = sum(t.valor for t in fatura.transacoes)
    if meta.valor_total == 0:
        if fatura.transacoes:
            meta.valor_total = soma
            print(
                f"  AVISO: total da fatura não foi extraído do PDF; "
                f"usando soma das transações (R$ {soma:.2f})."
            )
        return
    diferenca = meta.valor_total - soma
    if abs(diferenca) > TOLERANCIA_TOTAL:
        sinal = "+" if diferenca > 0 else "-"
        print(
            f"  AVISO: total da fatura R$ {meta.valor_total:.2f} difere da soma "
            f"das transações R$ {soma:.2f} ({sinal}R$ {abs(diferenca):.2f}). "
            f"Pode haver lançamento não capturado pelo parser."
        )


def _fatura_para_dicts(fatura: Fatura, arquivo: str) -> tuple[dict, list[dict]]:
    meta = fatura.metadata
    info = {
        "Arquivo": arquivo,
        "Banco": meta.banco,
        "Titular": meta.titular,
        "Referência": meta.referencia_mes,
        "Data de fechamento": meta.data_fechamento,
        "Data de vencimento": meta.data_vencimento,
        "Valor total (R$)": meta.valor_total,
        "Qtde. de transações": len(fatura.transacoes),
    }
    linhas = [
        {
            "Arquivo": arquivo,
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
    return info, linhas


def _carregar_excel_existente(caminho: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Lê informações e transações de um Excel acumulativo existente.

    Retorna DataFrames vazios (com as colunas esperadas) se o arquivo
    ainda não existir ou se as abas estiverem incompatíveis.
    """
    df_info = pd.DataFrame(columns=COLUNAS_INFO)
    df_transacoes = pd.DataFrame(columns=COLUNAS_TRANSACOES)
    if not caminho.exists():
        return df_info, df_transacoes
    try:
        df_info_lido = pd.read_excel(caminho, sheet_name="Informações")
        if "Arquivo" in df_info_lido.columns:
            df_info = df_info_lido
    except Exception:
        pass
    try:
        df_t_lido = pd.read_excel(caminho, sheet_name="Transações")
        if "Arquivo" in df_t_lido.columns:
            df_transacoes = df_t_lido
    except Exception:
        pass
    return df_info, df_transacoes


def _ordenar_transacoes(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["_data_ord"] = pd.to_datetime(df["Data"], format="%d/%m/%Y", errors="coerce")
    df = df.sort_values(["_data_ord", "Arquivo"], kind="stable").reset_index(drop=True)
    return df.drop(columns="_data_ord")


def _construir_resumo_geral(df_transacoes: pd.DataFrame) -> pd.DataFrame:
    if df_transacoes.empty:
        return pd.DataFrame(columns=["Categoria", "Valor (R$)"])
    resumo = (
        df_transacoes.groupby("Categoria", as_index=False)["Valor (R$)"]
        .sum()
        .sort_values("Valor (R$)", ascending=False)
        .reset_index(drop=True)
    )
    total = pd.DataFrame(
        [{"Categoria": "TOTAL GERAL", "Valor (R$)": resumo["Valor (R$)"].sum()}]
    )
    return pd.concat([resumo, total], ignore_index=True)


def _chave_ordenacao_referencia(referencia: str) -> tuple[int, int]:
    """Converte 'Maio/2026' em (2026, 5) para ordenar cronologicamente."""
    try:
        nome_mes, ano = referencia.split("/")
        return (int(ano), MES_POR_NOME.get(nome_mes, 0))
    except (ValueError, AttributeError):
        return (0, 0)


def _construir_resumo_mensal(df_transacoes: pd.DataFrame) -> pd.DataFrame:
    if df_transacoes.empty or "Referência" not in df_transacoes.columns:
        return pd.DataFrame()
    pivot = pd.pivot_table(
        df_transacoes,
        index="Referência",
        columns="Categoria",
        values="Valor (R$)",
        aggfunc="sum",
        fill_value=0.0,
    )
    referencias_ordenadas = sorted(pivot.index, key=_chave_ordenacao_referencia)
    pivot = pivot.loc[referencias_ordenadas]
    pivot["Total"] = pivot.sum(axis=1)
    pivot.loc["TOTAL"] = pivot.sum(axis=0)
    return pivot.reset_index()


def salvar_excel_acumulativo(
    df_info: pd.DataFrame, df_transacoes: pd.DataFrame, destino: Path
) -> None:
    df_transacoes = _ordenar_transacoes(df_transacoes)
    df_info = df_info.reindex(columns=COLUNAS_INFO)
    df_resumo = _construir_resumo_geral(df_transacoes)
    df_mensal = _construir_resumo_mensal(df_transacoes)

    destino.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(destino, engine="openpyxl") as writer:
        df_info.to_excel(writer, sheet_name="Informações", index=False)
        df_transacoes.to_excel(writer, sheet_name="Transações", index=False)
        df_resumo.to_excel(writer, sheet_name="Resumo por Categoria", index=False)
        if not df_mensal.empty:
            df_mensal.to_excel(writer, sheet_name="Resumo Mensal", index=False)

        _formatar_planilha(writer, "Informações", df_info)
        _formatar_planilha(writer, "Transações", df_transacoes)
        _formatar_planilha(writer, "Resumo por Categoria", df_resumo)
        if not df_mensal.empty:
            _formatar_planilha(writer, "Resumo Mensal", df_mensal)


def _formatar_planilha(writer, nome_aba: str, df: pd.DataFrame) -> None:
    aba = writer.sheets[nome_aba]

    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    for col_idx in range(1, len(df.columns) + 1):
        cell = aba.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    if nome_aba == "Resumo Mensal":
        colunas_valor_idx = range(2, len(df.columns) + 1)
    else:
        colunas_valor_idx = [
            df.columns.get_loc(c) + 1
            for c in df.columns
            if "Valor" in c or c == "Total"
        ]
    for col_idx in colunas_valor_idx:
        for row in range(2, len(df) + 2):
            celula = aba.cell(row=row, column=col_idx)
            if isinstance(celula.value, (int, float)):
                celula.number_format = "R$ #,##0.00"

    for col_idx, coluna in enumerate(df.columns, start=1):
        valores = [str(v) for v in df[coluna].astype(str).tolist()] + [str(coluna)]
        largura = min(max(len(v) for v in valores) + 2, 60)
        aba.column_dimensions[get_column_letter(col_idx)].width = largura

    aba.freeze_panes = "A2"


def _descobrir_pdfs(alvo: Path | None) -> list[Path]:
    if alvo is None:
        PASTA_ENTRADA.mkdir(parents=True, exist_ok=True)
        PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
        pdfs = sorted(PASTA_ENTRADA.glob("*.pdf"))
        if not pdfs:
            print(f"Nenhum PDF encontrado em '{PASTA_ENTRADA.name}/'.")
            print(
                f"Coloque os PDFs em '{PASTA_ENTRADA.name}/' e rode novamente, "
                f"ou passe um caminho como argumento."
            )
        return pdfs
    if alvo.is_file() and alvo.suffix.lower() == ".pdf":
        return [alvo]
    if alvo.is_dir():
        return sorted(alvo.glob("*.pdf"))
    print(f"Caminho inválido: {alvo}")
    return []


def processar(pdfs: Iterable[Path], destino: Path) -> None:
    df_info_existente, df_transacoes_existente = _carregar_excel_existente(destino)
    arquivos_no_excel = set(df_info_existente["Arquivo"].astype(str).tolist())

    novos_info: list[dict] = []
    novas_transacoes: list[dict] = []
    ignorados: list[str] = []
    pulados_sem_transacao: list[str] = []

    for pdf in pdfs:
        if pdf.name in arquivos_no_excel:
            ignorados.append(pdf.name)
            print(f"\nIgnorado (já no Excel): {pdf.name}")
            continue

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

        if not fatura.transacoes:
            pulados_sem_transacao.append(pdf.name)
            continue

        _conciliar_total(fatura)
        info, linhas = _fatura_para_dicts(fatura, pdf.name)
        novos_info.append(info)
        novas_transacoes.extend(linhas)

    if not novos_info:
        print("\nNenhuma fatura nova para adicionar ao Excel.")
        if ignorados:
            print(f"  Ignoradas (já no Excel): {len(ignorados)}")
        if pulados_sem_transacao:
            print(f"  Sem transações: {len(pulados_sem_transacao)}")
        return

    df_info_final = pd.concat(
        [df_info_existente, pd.DataFrame(novos_info)], ignore_index=True
    )
    df_transacoes_final = pd.concat(
        [df_transacoes_existente, pd.DataFrame(novas_transacoes)], ignore_index=True
    )
    salvar_excel_acumulativo(df_info_final, df_transacoes_final, destino)

    print(f"\nExcel acumulativo atualizado: {destino}")
    print(
        f"  Total no arquivo: {len(df_info_final)} faturas, "
        f"{len(df_transacoes_final)} transações."
    )
    print(f"  Faturas adicionadas nesta execução: {len(novos_info)}.")
    if ignorados:
        print(f"  Ignoradas (já no Excel): {len(ignorados)}.")


def main() -> None:
    alvo = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else None
    pdfs = _descobrir_pdfs(alvo)
    if not pdfs:
        sys.exit(1)
    destino = PASTA_SAIDA / ARQUIVO_SAIDA
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    processar(pdfs, destino)
    print("\nConcluído.")


if __name__ == "__main__":
    main()
