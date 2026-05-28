"""Migra `saida/gastometro.xlsx` (formato CLI atual) para o banco.

Estratégia:
  1. Lê as abas `Informações` e `Transações` do Excel acumulativo.
  2. Para cada arquivo (fatura), monta um `FaturaParser` *equivalente*
     com a categoria já decidida (preservando correções manuais que o
     usuário fez direto no Excel).
  3. Chama `upsert_fatura(..., respeitar_categoria_existente=True,
     fonte='excel_legado')`. Idempotente — re-rodar não duplica.
  4. (Opcional) Importa `categorias_usuario.json` pra tabela
     `override_categoria`, sumindo com o arquivo no fluxo Fase 1+.
  5. Valida totais: compara soma do Excel x soma do banco, qtde por
     fatura, qtde de cartões/pessoas.

Saída: relatório por stdout.

Uso:
    python -m imports.migrar_excel_legado [caminho_excel]

Quando `caminho_excel` é omitido, usa `saida/gastometro.xlsx`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from db.backup import fazer_backup
from db.repository import upsert_fatura
from db.seed import seed_inicial
from parsers.base import Fatura as FaturaParser
from parsers.base import FaturaMetadata, Transacao

RAIZ = Path(__file__).resolve().parent.parent
EXCEL_PADRAO = RAIZ / "saida" / "gastometro.xlsx"
OVERRIDES_JSON = RAIZ / "categorias_usuario.json"


def _ler_excel(caminho: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not caminho.exists():
        print(f"Excel não encontrado: {caminho}", file=sys.stderr)
        sys.exit(1)
    df_info = pd.read_excel(caminho, sheet_name="Informações")
    df_tx = pd.read_excel(caminho, sheet_name="Transações")
    return df_info, df_tx


def _coluna(df: pd.DataFrame, *nomes: str) -> str:
    """Retorna o primeiro nome existente; útil pra schema com colunas opcionais."""
    for n in nomes:
        if n in df.columns:
            return n
    raise KeyError(f"Nenhuma das colunas {nomes} presente em {list(df.columns)}")


def _linha_info_para_metadata(linha: dict[str, Any]) -> FaturaMetadata:
    """Converte 1 linha da aba `Informações` em `FaturaMetadata`."""
    def _str(valor: Any) -> str:
        return "" if pd.isna(valor) else str(valor)

    def _data_str(valor: Any) -> str:
        """Datas no Excel vêm como Timestamp; converte pra `DD/MM/AAAA`."""
        if pd.isna(valor):
            return ""
        if isinstance(valor, pd.Timestamp):
            return valor.strftime("%d/%m/%Y")
        return str(valor)

    valor_total_raw = linha.get("Valor total (R$)")
    valor_total = (
        float(valor_total_raw)
        if valor_total_raw is not None and not pd.isna(valor_total_raw)
        else 0.0
    )

    return FaturaMetadata(
        banco=_str(linha.get("Banco")),
        titular=_str(linha.get("Titular")),
        referencia_mes=_str(linha.get("Referência")),
        data_fechamento=_data_str(linha.get("Data de fechamento")),
        data_vencimento=_data_str(linha.get("Data de vencimento")),
        valor_total=valor_total,
    )


def _linha_tx_para_transacao(linha: dict[str, Any]) -> Transacao | None:
    """1 linha da aba `Transações` → `Transacao`. Retorna `None` se inválida."""
    def _str(valor: Any) -> str:
        return "" if pd.isna(valor) else str(valor)

    def _data_str(valor: Any) -> str:
        if pd.isna(valor):
            return ""
        if isinstance(valor, pd.Timestamp):
            return valor.strftime("%d/%m/%Y")
        return str(valor)

    valor = linha.get("Valor (R$)")
    if valor is None or pd.isna(valor):
        return None

    return Transacao(
        data=_data_str(linha.get("Data")),
        descricao=_str(linha.get("Descrição")),
        parcela=_str(linha.get("Parcela")),
        cidade=_str(linha.get("Cidade")),
        valor=float(valor),
        categoria=_str(linha.get("Categoria")),
    )


def _agrupar_por_arquivo(df_tx: pd.DataFrame) -> dict[str, list[Transacao]]:
    """Agrupa transações por nome do arquivo (PDF de origem)."""
    grupos: dict[str, list[Transacao]] = {}
    for _, linha in df_tx.iterrows():
        arquivo = "" if pd.isna(linha.get("Arquivo")) else str(linha["Arquivo"])
        if not arquivo:
            continue
        tx = _linha_tx_para_transacao(dict(linha))
        if tx is None:
            continue
        grupos.setdefault(arquivo, []).append(tx)
    return grupos


def migrar(caminho_excel: Path = EXCEL_PADRAO) -> dict[str, int]:
    """Roda a migração completa. Devolve contagens (`faturas`, `lancamentos`).

    Idempotente: rodar duas vezes não duplica nada.
    """
    seed_inicial()
    backup = fazer_backup(motivo="pre_migracao_excel_legado")
    if backup:
        print(f"Backup pré-migração: {backup.name}")

    df_info, df_tx = _ler_excel(caminho_excel)
    print(
        f"Excel lido: {len(df_info)} faturas, {len(df_tx)} transações."
    )

    grupos = _agrupar_por_arquivo(df_tx)

    total_faturas = 0
    total_lancs = 0
    pulados: list[str] = []
    info_arquivos = {
        str(linha["Arquivo"]): linha for _, linha in df_info.iterrows()
    }

    for arquivo, transacoes in grupos.items():
        info = info_arquivos.get(arquivo)
        if info is None:
            pulados.append(arquivo)
            continue
        meta = _linha_info_para_metadata(dict(info))
        fatura = FaturaParser(metadata=meta, transacoes=transacoes)
        fat_id, inseridos = upsert_fatura(
            fatura,
            arquivo=arquivo,
            respeitar_categoria_existente=True,
            fonte="excel_legado",
        )
        total_faturas += 1
        total_lancs += inseridos
        print(
            f"  {arquivo}: fatura_id={fat_id}, novos={inseridos}/{len(transacoes)}"
        )

    if pulados:
        print(
            f"\nAVISO: {len(pulados)} arquivo(s) tinham transações mas faltavam "
            f"em 'Informações': {pulados[:5]}{'...' if len(pulados) > 5 else ''}"
        )

    overrides = _importar_overrides_legado()
    if overrides:
        print(f"\nOverrides do JSON migrados: {overrides}")

    print(
        f"\nMigração concluída: {total_faturas} fatura(s) processadas, "
        f"{total_lancs} lançamentos novos no banco."
    )

    _validar_totais(df_info, df_tx)

    return {"faturas": total_faturas, "lancamentos": total_lancs}


def _importar_overrides_legado() -> int:
    """Migra `categorias_usuario.json` (se existir) pra tabela override."""
    if not OVERRIDES_JSON.exists():
        return 0
    from db.repository import importar_categorias_usuario_json

    return importar_categorias_usuario_json(OVERRIDES_JSON)


def _validar_totais(df_info: pd.DataFrame, df_tx: pd.DataFrame) -> None:
    """Compara totais do Excel x totais no banco, por fatura.

    Espera que os totais batam dentro de `0.01`. Lista divergências
    pra revisão manual.
    """
    from db.repository import listar_faturas_df, listar_lancamentos_df

    df_banco_lanc = listar_lancamentos_df(sinal_estorno_negativo=True)
    df_banco_fat = listar_faturas_df()

    soma_excel = float(df_tx["Valor (R$)"].sum())
    soma_banco = float(df_banco_lanc["valor"].sum()) if not df_banco_lanc.empty else 0.0

    print("\n=== Validação ===")
    print(f"  Faturas Excel: {len(df_info)} | Banco: {len(df_banco_fat)}")
    print(f"  Transações Excel: {len(df_tx)} | Banco: {len(df_banco_lanc)}")
    print(
        f"  Soma valores Excel: R$ {soma_excel:.2f} | Banco: R$ {soma_banco:.2f} "
        f"| Δ: R$ {soma_excel - soma_banco:.2f}"
    )

    divergencias: list[str] = []
    soma_por_arquivo_excel = (
        df_tx.groupby("Arquivo")["Valor (R$)"].sum().to_dict()
    )
    soma_por_arquivo_banco = (
        df_banco_lanc.groupby("arquivo")["valor"].sum().to_dict()
        if not df_banco_lanc.empty
        else {}
    )
    for arquivo, soma_e in soma_por_arquivo_excel.items():
        soma_b = soma_por_arquivo_banco.get(arquivo, 0.0)
        if abs(soma_e - soma_b) > 0.01:
            divergencias.append(
                f"    {arquivo}: Excel R$ {soma_e:.2f} vs Banco R$ {soma_b:.2f}"
            )

    if divergencias:
        print(f"  Divergências por fatura ({len(divergencias)}):")
        for d in divergencias[:10]:
            print(d)
        if len(divergencias) > 10:
            print(f"    ... mais {len(divergencias) - 10}")
    else:
        print("  Sem divergências por fatura (todos os totais batem ±R$ 0,01).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migra o Excel acumulativo do gastometro pro banco SQLite."
    )
    parser.add_argument(
        "excel",
        nargs="?",
        default=str(EXCEL_PADRAO),
        help=f"caminho do .xlsx (default: {EXCEL_PADRAO})",
    )
    args = parser.parse_args()
    caminho = Path(args.excel).expanduser().resolve()
    migrar(caminho)


if __name__ == "__main__":
    main()
