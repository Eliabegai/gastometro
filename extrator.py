"""
Extrator de fatura em PDF — Fase 1+.

Fluxo:
  1. PDFs em `entrada/` (criada na 1ª execução).
  2. `python extrator.py` processa, grava no banco SQLite
     (`dados/gastometro.db`) e regera `saida/gastometro.xlsx`.
  3. O Excel passa a ser um **espelho** do banco — fonte da verdade é
     o `.db`. Edições pontuais (futuro): UI Streamlit (Fase 2).

Faturas já registradas (mesmo nome de arquivo) são ignoradas. Pra
reprocessar, apague a fatura via UI/SQL ou troque o nome do PDF.

Uso:
    python extrator.py                       # processa PDFs de entrada/
    python extrator.py Fatura.pdf            # processa um PDF
    python extrator.py pasta/                # processa PDFs de outra pasta
    python extrator.py --no-excel            # pula regeração do XLSX
    python extrator.py aprender              # lê coluna Categoria do
                                             # Excel e salva overrides no
                                             # banco (depois recategoriza)
    python extrator.py recategorizar         # re-aplica regras no banco
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from db.backup import fazer_backup
from db.repository import (
    listar_lancamentos_df,
    recategorizar_todos,
    salvar_override,
    upsert_fatura,
)
from db.seed import seed_inicial
from export.excel import regenerar_planilha_do_banco
from parsers import Fatura, extrair_fatura
from parsers.base import MES_POR_NUMERO

RAIZ = Path(__file__).parent
PASTA_ENTRADA = RAIZ / "entrada"
PASTA_SAIDA = RAIZ / "saida"
ARQUIVO_SAIDA = "gastometro.xlsx"

TOLERANCIA_TOTAL = 0.01

MES_POR_NOME = {nome: num for num, nome in MES_POR_NUMERO.items()}


def _conciliar_total(fatura: Fatura) -> None:
    """Compara o total extraído do PDF com a soma das transações.

    Mantida no extrator (não no parser) porque depende de regra de
    negócio: estornos podem explicar diferenças entre `valor_total`
    declarado pelo banco e a soma das linhas. Imprime aviso quando
    houver divergência suspeita; usa o total declarado se não estiver
    presente (cai pra soma e avisa).
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
    if abs(diferenca) <= TOLERANCIA_TOTAL:
        return

    soma_estornos = sum(t.valor for t in fatura.transacoes if t.valor < 0)
    sinal = "+" if diferenca > 0 else "-"
    cabecalho = (
        f"  AVISO: total da fatura R$ {meta.valor_total:.2f} difere da soma "
        f"das transações R$ {soma:.2f} ({sinal}R$ {abs(diferenca):.2f})."
    )
    if soma_estornos < 0 and abs(diferenca + soma_estornos) <= TOLERANCIA_TOTAL:
        print(
            f"{cabecalho} Diferença equivale aos estornos detectados "
            f"(R$ {soma_estornos:.2f}); o banco computa o total bruto."
        )
    else:
        print(f"{cabecalho} Pode haver lançamento não capturado pelo parser.")


def _descobrir_pdfs(alvo: Path | None) -> list[Path]:
    """Resolve a lista de PDFs a partir do argumento da CLI."""
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


def _chave_ordenacao_referencia(referencia: str) -> tuple[int, int]:
    """'Maio/2026' → (2026, 5). Aceita ISO ('2026-05') também."""
    if not referencia:
        return (0, 0)
    if "/" in referencia:
        try:
            nome_mes, ano = referencia.split("/")
            return (int(ano), MES_POR_NOME.get(nome_mes, 0))
        except (ValueError, AttributeError):
            return (0, 0)
    if "-" in referencia:
        try:
            ano, mes = referencia.split("-", 1)
            return (int(ano), int(mes))
        except (ValueError, AttributeError):
            return (0, 0)
    return (0, 0)


def _formatar_brl(valor: float) -> str:
    """`1.234,56` sem locale."""
    s = f"{abs(valor):,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {s}" if valor < 0 else f"R$ {s}"


def _ref_para_nome_br(referencia: str) -> str:
    """'2026-05' → 'Maio/2026'. Aceita já formatado (passa direto)."""
    if not referencia or "/" in referencia or "-" not in referencia:
        return referencia
    try:
        ano, mes = referencia.split("-", 1)
        nome = MES_POR_NUMERO.get(int(mes), mes)
        return f"{nome}/{ano}"
    except (ValueError, KeyError):
        return referencia


def _imprimir_top_outros_gastos(df: pd.DataFrame, top_n: int = 10) -> None:
    """Top descrições caídas em `Outros Gastos` (ajuda a refinar regras)."""
    if df is None or df.empty:
        return
    outros = df[(df["categoria"] == "Outros Gastos") & (df["valor"] > 0)]
    if outros.empty:
        return

    agregado = (
        outros.groupby("descricao")["valor"]
        .agg(soma="sum", n="count")
        .reset_index()
        .sort_values("soma", ascending=False)
        .head(top_n)
    )

    print(
        f"\nTop {len(agregado)} descrições em 'Outros Gastos' "
        f"(acumulado no banco):"
    )
    for _, linha in agregado.iterrows():
        print(
            f"  R$ {linha['soma']:9.2f}  ({int(linha['n']):2d}x)  "
            f"{linha['descricao']}"
        )
    print(
        "  Para categorizar: edite `categorias.py` (regra geral) ou rode "
        "`python extrator.py aprender` depois de ajustar a coluna "
        "`Categoria` no Excel (override individual)."
    )


def _imprimir_comparativo_mensal(df: pd.DataFrame) -> None:
    """Compara último mês com o anterior: total + categorias com maior delta."""
    if df is None or df.empty:
        return
    if "referencia_mes" not in df.columns or "categoria" not in df.columns:
        return

    refs = sorted(
        {str(r) for r in df["referencia_mes"].astype(str) if r and r != "nan"},
        key=_chave_ordenacao_referencia,
    )
    if len(refs) < 2:
        return

    ultimo, anterior = refs[-1], refs[-2]
    ultimo_label = _ref_para_nome_br(ultimo)
    anterior_label = _ref_para_nome_br(anterior)

    def soma_por_categoria(ref: str) -> dict[str, float]:
        sub = df[df["referencia_mes"] == ref]
        return (
            sub.groupby("categoria")["valor"]
            .sum()
            .to_dict()
        )

    cats_ult = soma_por_categoria(ultimo)
    cats_ant = soma_por_categoria(anterior)
    total_ult = float(sum(cats_ult.values()))
    total_ant = float(sum(cats_ant.values()))

    print(f"\nComparativo: {ultimo_label} vs {anterior_label}")
    if total_ant:
        var_pct = (total_ult - total_ant) / total_ant * 100.0
        sinal = "+" if var_pct >= 0 else ""
        diff = total_ult - total_ant
        sinal_abs = "+" if diff >= 0 else "-"
        print(
            f"  TOTAL                 {_formatar_brl(total_ult):>14}  "
            f"({sinal}{var_pct:.1f}% / {sinal_abs}{_formatar_brl(abs(diff))[3:]}"
            f" vs {_formatar_brl(total_ant)})"
        )
    else:
        print(
            f"  TOTAL                 {_formatar_brl(total_ult):>14}  "
            f"(mês anterior R$ 0,00)"
        )

    todas = set(cats_ult) | set(cats_ant)
    diffs: list[tuple[str, float, float, float]] = []
    for cat in todas:
        a = float(cats_ult.get(cat, 0.0))
        b = float(cats_ant.get(cat, 0.0))
        diffs.append((cat, a, b, a - b))
    diffs.sort(key=lambda t: abs(t[3]), reverse=True)

    for cat, atual, ant, diff in diffs[:8]:
        if abs(diff) < 0.01:
            continue
        sinal_abs = "+" if diff >= 0 else "-"
        valor_atual = _formatar_brl(atual)
        if ant == 0:
            print(
                f"  {cat:21}  {valor_atual:>14}  "
                f"(novo, {sinal_abs}{_formatar_brl(abs(diff))[3:]})"
            )
        else:
            var_pct = diff / ant * 100.0
            sinal = "+" if var_pct >= 0 else ""
            print(
                f"  {cat:21}  {valor_atual:>14}  "
                f"({sinal}{var_pct:.1f}% / {sinal_abs}{_formatar_brl(abs(diff))[3:]})"
            )


def processar(pdfs: Iterable[Path], *, regerar_excel: bool = True) -> int:
    """Processa PDFs: grava no banco e (opcionalmente) regera o Excel.

    Devolve o número de faturas novas adicionadas ao banco.
    """
    seed_inicial()
    fazer_backup(motivo="pre_extracao")

    novos_total = 0
    inseridas: list[str] = []
    ignoradas: list[str] = []
    pulados_sem_transacao: list[str] = []

    for pdf in pdfs:
        print(f"\nProcessando: {pdf.name}")
        try:
            fatura = extrair_fatura(pdf)
        except Exception as exc:  # noqa: BLE001
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
        _fat_id, inseridos = upsert_fatura(fatura, arquivo=pdf.name)
        if inseridos == 0:
            ignoradas.append(pdf.name)
            print("  Já estava no banco (idempotente, 0 lançamentos novos).")
            continue
        inseridas.append(pdf.name)
        novos_total += inseridos
        print(f"  → {inseridos} lançamentos gravados no banco.")

    print(
        f"\nBanco: {len(inseridas)} fatura(s) nova(s) "
        f"({novos_total} lançamentos)."
    )
    if ignoradas:
        print(f"  Já no banco (ignoradas): {len(ignoradas)}.")
    if pulados_sem_transacao:
        print(f"  Sem transações: {len(pulados_sem_transacao)}.")

    if regerar_excel:
        destino = PASTA_SAIDA / ARQUIVO_SAIDA
        PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
        fat, lanc = regenerar_planilha_do_banco(destino)
        print(
            f"\nExcel regenerado: {destino} "
            f"({fat} fatura(s), {lanc} lançamento(s))."
        )

    df = listar_lancamentos_df()
    _imprimir_top_outros_gastos(df)
    _imprimir_comparativo_mensal(df)

    return len(inseridas)


def aprender(caminho_excel: Path | None = None) -> None:
    """Lê coluna `Categoria` do Excel e grava overrides no banco.

    Use depois de editar manualmente a coluna `Categoria` no Excel
    (cenário típico: você abriu o XLSX, corrigiu 5 linhas em
    `Outros Gastos`, salvou). Esta função detecta as descrições cuja
    categoria editada difere do que o dicionário fixo retornaria e
    grava cada uma como override no banco. Em seguida, roda
    recategorização pra propagar pros lançamentos do histórico.
    """
    from categorias import categorizar_pelo_dicionario

    seed_inicial()
    caminho = caminho_excel or (PASTA_SAIDA / ARQUIVO_SAIDA)
    if not caminho.exists():
        print(f"Excel não encontrado: {caminho}")
        sys.exit(1)

    df = pd.read_excel(caminho, sheet_name="Transações")
    if df.empty or "Descrição" not in df.columns or "Categoria" not in df.columns:
        print(f"Aba 'Transações' vazia ou sem colunas esperadas em {caminho}.")
        sys.exit(1)

    fazer_backup(motivo="pre_aprender")

    salvos = 0
    for _, linha in df.iterrows():
        descricao = str(linha.get("Descrição", "")).strip()
        categoria = str(linha.get("Categoria", "")).strip()
        if not descricao or not categoria:
            continue
        if categorizar_pelo_dicionario(descricao) == categoria:
            continue
        salvar_override(descricao, categoria)
        salvos += 1

    print(f"Aprendizado: {salvos} override(s) salvos no banco (lidos de {caminho.name}).")

    resultado = recategorizar_todos()
    print(
        f"Re-categorização aplicada no histórico: "
        f"{resultado['mudados']} de {resultado['total']} lançamentos atualizados."
    )

    destino = PASTA_SAIDA / ARQUIVO_SAIDA
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    fat, lanc = regenerar_planilha_do_banco(destino)
    print(f"Excel regenerado: {destino} ({fat} fatura(s), {lanc} lançamento(s)).")


def recategorizar(_caminho_legado: Path | None = None) -> None:
    """Re-aplica regras (overrides + dicionário) em todos os lançamentos.

    Útil quando você editou `categorias.py` (regra geral) e quer
    propagar pra todo o histórico do banco. Após atualizar, regera
    o Excel pra refletir.
    """
    seed_inicial()
    fazer_backup(motivo="pre_recategorizar")

    resultado = recategorizar_todos()
    print(
        f"Re-categorização: {resultado['mudados']} de {resultado['total']} "
        f"lançamentos atualizados."
    )

    destino = PASTA_SAIDA / ARQUIVO_SAIDA
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    fat, lanc = regenerar_planilha_do_banco(destino)
    print(f"Excel regenerado: {destino} ({fat} fatura(s), {lanc} lançamento(s)).")

    df = listar_lancamentos_df()
    _imprimir_top_outros_gastos(df)
    _imprimir_comparativo_mensal(df)


def _construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gastometro",
        description="Extrai faturas PDF para banco SQLite + Excel acumulativo.",
    )
    p.add_argument(
        "alvo",
        nargs="?",
        default=None,
        help=(
            "PDF, pasta de PDFs, ou comando ('aprender', 'recategorizar'). "
            f"Sem argumento, processa todos os PDFs em '{PASTA_ENTRADA.name}/'."
        ),
    )
    p.add_argument(
        "extra",
        nargs="?",
        default=None,
        help="Caminho opcional do Excel para 'aprender'/'recategorizar'.",
    )
    p.add_argument(
        "--no-excel",
        action="store_true",
        help="Pula regeração do XLSX (útil em CI ou loops rápidos).",
    )
    return p


def main() -> None:
    parser = _construir_parser()
    args = parser.parse_args()

    if args.alvo in {"aprender", "recategorizar"}:
        caminho = (
            Path(args.extra).expanduser().resolve()
            if args.extra
            else None
        )
        if args.alvo == "aprender":
            aprender(caminho)
        else:
            recategorizar(caminho)
        print("\nConcluído.")
        return

    alvo = Path(args.alvo).expanduser().resolve() if args.alvo else None
    pdfs = _descobrir_pdfs(alvo)
    if not pdfs:
        sys.exit(1)
    processar(pdfs, regerar_excel=not args.no_excel)
    print("\nConcluído.")


if __name__ == "__main__":
    main()
