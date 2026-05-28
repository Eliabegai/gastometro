"""Componente reutilizável: uploader de PDFs de fatura.

Usado pela página `Faturas` (no topo) e pela página dedicada
`Importar`. Mantém a UX e a lógica consistente entre os dois lugares.

Fluxo:
  1. `st.file_uploader` recebe N PDFs.
  2. Checkboxes:
     - **Arquivar PDF em `entrada/`** (default ligado): salva o
       arquivo original em disco pra audit trail / reprocessamento.
       Quando desligado, o PDF é processado a partir de um arquivo
       temporário e descartado.
     - **Regenerar `saida/gastometro.xlsx`** (default ligado):
       atualiza o Excel após processar (mesmo comportamento do CLI).
  3. Botão **Processar**:
     - Roda `parsers.extrair_fatura(pdf)` + `db.repository.upsert_fatura`
       em cada arquivo, igual o `extrator.processar` faz.
     - Mostra resultado em tabela (arquivo / status / fatura / qtde).
     - Limpa o cache do Streamlit pras outras páginas refletirem.

A lógica de PDF→banco é a mesma do CLI (`extrator.processar`) — aqui
ela é reescrita pra capturar resultados em listas em vez de imprimir,
o que dá um feedback decente na UI.
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from app.helpers import invalidar_cache
from db.backup import fazer_backup
from db.repository import upsert_fatura
from db.seed import seed_inicial
from export.excel import regenerar_planilha_do_banco
from parsers import extrair_fatura

RAIZ = Path(__file__).resolve().parents[2]
PASTA_ENTRADA = RAIZ / "entrada"
PASTA_SAIDA = RAIZ / "saida"
ARQUIVO_SAIDA = "gastometro.xlsx"


def _nome_unico(destino_dir: Path, nome_original: str) -> Path:
    """Devolve um caminho disponível em `destino_dir`. Se `nome_original`
    já existe, anexa timestamp pra preservar histórico de PDFs."""
    candidato = destino_dir / nome_original
    if not candidato.exists():
        return candidato
    stem = candidato.stem
    suffix = candidato.suffix
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    return destino_dir / f"{stem}__{carimbo}{suffix}"


def _processar_um_pdf(pdf_path: Path) -> dict[str, Any]:
    """Roda extrator + upsert em um PDF. Devolve dict com resumo."""
    resultado: dict[str, Any] = {
        "arquivo": pdf_path.name,
        "status": "",
        "banco": "",
        "titular": "",
        "referencia": "",
        "transacoes": 0,
        "novos": 0,
        "erro": "",
    }
    try:
        fatura = extrair_fatura(pdf_path)
    except Exception as exc:  # noqa: BLE001
        resultado["status"] = "erro"
        resultado["erro"] = str(exc)
        return resultado

    meta = fatura.metadata
    resultado["banco"] = meta.banco or ""
    resultado["titular"] = meta.titular or ""
    resultado["referencia"] = meta.referencia_mes or ""
    resultado["transacoes"] = len(fatura.transacoes)

    if not fatura.transacoes:
        resultado["status"] = "sem_transacoes"
        return resultado

    _fat_id, inseridos = upsert_fatura(fatura, arquivo=pdf_path.name)
    resultado["novos"] = inseridos
    resultado["status"] = "novo" if inseridos > 0 else "ja_no_banco"
    return resultado


def _processar_uploads(
    arquivos: list[Any],
    *,
    arquivar: bool,
    regerar_xlsx: bool,
) -> tuple[list[dict[str, Any]], str | None]:
    """Processa cada upload. Devolve `(resultados, caminho_excel)`."""
    seed_inicial()
    fazer_backup(motivo="pre_upload_streamlit")

    resultados: list[dict[str, Any]] = []

    for upload in arquivos:
        if arquivar:
            PASTA_ENTRADA.mkdir(parents=True, exist_ok=True)
            destino = _nome_unico(PASTA_ENTRADA, upload.name)
            destino.write_bytes(upload.getvalue())
            res = _processar_um_pdf(destino)
            res["destino"] = str(destino.relative_to(RAIZ))
        else:
            with tempfile.NamedTemporaryFile(
                suffix=".pdf", delete=False
            ) as tmp:
                tmp.write(upload.getvalue())
                tmp_path = Path(tmp.name)
            try:
                # Renomeia pra preservar o nome original — `upsert_fatura`
                # registra `arquivo=pdf.name` no banco e é usado pra
                # drill-down/dedup amigável.
                renomeado = tmp_path.with_name(upload.name)
                shutil.move(tmp_path, renomeado)
                res = _processar_um_pdf(renomeado)
                res["destino"] = "(temporário)"
            finally:
                try:
                    if renomeado.exists():
                        renomeado.unlink()
                except Exception:  # noqa: BLE001
                    pass
        resultados.append(res)

    caminho_excel: str | None = None
    if regerar_xlsx and any(r["novos"] > 0 for r in resultados):
        destino = PASTA_SAIDA / ARQUIVO_SAIDA
        PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
        regenerar_planilha_do_banco(destino)
        caminho_excel = str(destino.relative_to(RAIZ))

    return resultados, caminho_excel


def _renderizar_resultados(
    resultados: list[dict[str, Any]], caminho_excel: str | None
) -> None:
    """Exibe um resumo + tabela com 1 linha por PDF processado."""
    novos = sum(1 for r in resultados if r["status"] == "novo")
    ja_banco = sum(1 for r in resultados if r["status"] == "ja_no_banco")
    erros = sum(1 for r in resultados if r["status"] == "erro")
    sem_tx = sum(1 for r in resultados if r["status"] == "sem_transacoes")
    lancs_novos = sum(int(r.get("novos") or 0) for r in resultados)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Faturas novas", novos)
    c2.metric("Já no banco", ja_banco)
    c3.metric("Lançamentos novos", f"{lancs_novos:,}".replace(",", "."))
    c4.metric("Erros / sem dados", erros + sem_tx)

    if caminho_excel:
        st.success(f"Excel regenerado: `{caminho_excel}`")

    rotulo_status = {
        "novo": "novo",
        "ja_no_banco": "já no banco",
        "sem_transacoes": "sem transações",
        "erro": "erro",
    }

    linhas: list[dict[str, Any]] = []
    for r in resultados:
        linhas.append(
            {
                "Arquivo": r["arquivo"],
                "Status": rotulo_status.get(r["status"], r["status"]),
                "Banco": r["banco"],
                "Titular": r["titular"],
                "Referência": r["referencia"],
                "Transações": r["transacoes"],
                "Novos no banco": r["novos"],
                "Detalhes": r["erro"] or r.get("destino", ""),
            }
        )

    st.dataframe(linhas, use_container_width=True, hide_index=True)


def render_uploader(*, key_prefix: str = "uploader") -> None:
    """Renderiza o componente de upload + processamento."""
    arquivos = st.file_uploader(
        "Selecione um ou mais PDFs de fatura",
        type=["pdf"],
        accept_multiple_files=True,
        key=f"{key_prefix}_files",
    )

    col_a, col_b = st.columns(2)
    with col_a:
        arquivar = st.checkbox(
            "Arquivar PDF em `entrada/`",
            value=True,
            help=(
                "Salva o PDF original em `entrada/` (audit trail). "
                "Desmarque pra processar via arquivo temporário."
            ),
            key=f"{key_prefix}_arquivar",
        )
    with col_b:
        regerar_xlsx = st.checkbox(
            "Regenerar `saida/gastometro.xlsx`",
            value=True,
            help=(
                "Atualiza o Excel após processar. Mesmo comportamento "
                "do `gastometro` CLI."
            ),
            key=f"{key_prefix}_xlsx",
        )

    desabilitar = not arquivos
    if st.button(
        "📥 Processar PDFs",
        type="primary",
        disabled=desabilitar,
        key=f"{key_prefix}_btn",
    ):
        with st.spinner("Processando faturas…"):
            resultados, caminho_excel = _processar_uploads(
                list(arquivos),
                arquivar=arquivar,
                regerar_xlsx=regerar_xlsx,
            )
        invalidar_cache()
        _renderizar_resultados(resultados, caminho_excel)
        if any(r["status"] == "novo" for r in resultados):
            st.info("Recarregue as outras páginas (ou clique em **Rerun**) pra ver os dados atualizados.")
