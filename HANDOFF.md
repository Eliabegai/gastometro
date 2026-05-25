# Handoff — Projeto gastometro

> Documento de transferência para outro agente do Cursor continuar o trabalho.
> Leia este arquivo antes de tudo. Resumo do contexto, decisões técnicas
> e o que está pendente.

## 1. Contexto rápido

**Projeto**: extrator de faturas de cartão em PDF que categoriza os gastos
e exporta para Excel.

- **Diretório local**: `/Users/eliabenextil/Projects/gastometro`
- **Nome escolhido para o GitHub**: `gastometro`
- **Usuário sempre responde em português** (regra do projeto).
- **Linguagem**: Python 3.10+ (testado com 3.14.5).
- **Stack**: `pdfplumber` (extração PDF) + `pandas` + `openpyxl` (Excel).
- **Ambiente virtual já criado** em `.venv/` (rodar `source .venv/bin/activate`).

## 2. O que está pronto

### Arquitetura

```
gastometro/
├── extrator.py            # CLI + exportador Excel (orquestrador)
├── categorias.py          # regras de categorização (palavras-chave)
├── parsers/
│   ├── __init__.py        # auto-detecção do banco
│   ├── base.py            # dataclasses (Fatura, FaturaMetadata, Transacao) e utils compartilhadas
│   ├── ailos.py           # parser Ailos Mastercard (100% testado)
│   ├── nubank.py          # parser Nubank (100% testado)
│   └── banco_brasil.py    # parser BB Ourocard (estrutura inicial, NÃO testado com PDF real)
├── requirements.txt
├── README.md
├── HANDOFF.md             # este arquivo
└── .gitignore             # ignora *.pdf, *.xlsx, .venv, __pycache__
```

### Funcionalidades implementadas

1. **Auto-detecção de banco** via assinaturas no texto do PDF
   (`parsers/__init__.py::_escolher_parser`).
2. **Parsers por banco** — cada um expõe `detectar(texto) -> bool` e
   `extrair(caminho_pdf) -> Fatura`.
3. **Metadados da fatura**: banco, titular, referência (mês/ano),
   data de fechamento, data de vencimento, valor total, qtde. transações.
4. **Categorização configurável** via dicionário em `categorias.py`.
5. **Excel com 3 abas**:
   - `Informações` — cabeçalho da fatura.
   - `Transações` — Banco, Titular, Referência, Data, Descrição, Parcela, Cidade, Valor, Categoria.
   - `Resumo por Categoria` — soma por categoria + total geral.

### Validações reais (PDFs do usuário)

| PDF | Banco | Transações | Soma extraída | Total esperado | OK? |
|---|---|---|---|---|---|
| `Fatura_05_2026.pdf` | Ailos | 48 | R$ 4.422,81 | R$ 4.422,81 | ✓ |
| `Nubank_2026-05-13.pdf` | Nubank | 10 | R$ 932,54 | R$ 932,54 | ✓ |

## 3. Estado do git

```
branch: main
commit inicial: 38eef87 — feat: extrator de faturas em PDF com categorização e exportação Excel
remote: ainda não configurado
```

O usuário pediu para subir no GitHub com o nome **`gastometro`**.

**Pendente**: ele precisa criar o repo (manualmente em github.com/new ou
via `gh repo create gastometro --public --source=. --remote=origin --push`)
e depois rodar `git push -u origin main`. O `gh` CLI não está instalado
na máquina ainda — sugerir `brew install gh` se ele preferir o caminho CLI.

**IMPORTANTE**: o `.gitignore` ignora `*.pdf` e `*.xlsx` porque contêm
dados pessoais do usuário (faturas reais). Há uma exceção para a pasta
`exemplos/` (ainda não existe — usar se for criar PDFs sintéticos).

## 4. Decisões técnicas importantes

### Parser Ailos (`parsers/ailos.py`)

- **Layout do PDF**: duas colunas na página de lançamentos. Outras páginas
  têm layout único.
- **Estratégia**: para cada página, faz `crop()` em metade (esquerda/direita)
  e processa cada coluna individualmente.
- **Identificação de colunas**: usa as coordenadas X do cabeçalho
  `DATA / DESCRIÇÃO / CIDADE / VALOR` (função `_detectar_colunas`) e
  classifica cada palavra subsequente por proximidade X.
- **Filtra antes do cabeçalho**: lançamentos administrativos (anuidade,
  pagamento, etc.) aparecem antes do cabeçalho `DATA DESCRIÇÃO` em uma
  parte da página 3 — eles são descartados via `top_cabecalho` (linhas
  acima do cabeçalho são ignoradas).
- **Descrições multi-linha**: usa `desc_pendente` e `cidade_pendente` como
  buffer; quando aparecem fragmentos curtos (`len <= 2`) sozinhos APÓS uma
  transação, anexa à anterior em vez da próxima.

### Parser Nubank (`parsers/nubank.py`)

- **Layout**: única coluna. Regex `DD MMM •••• XXXX Descrição R$ XX,XX`.
- **Valor total**: prioriza `no valor de R$ X` (frase do topo da fatura).
  Cuidado: `Total a pagar` aparece várias vezes no PDF (em propostas de
  parcelamento) e pode pegar valor errado se usado primeiro.
- **Parcela**: extrai de `- Parcela X/Y` ao final da descrição.
- **Filtra**: linhas com "Pagamento em", "Saldo restante", etc.

### Parser Banco do Brasil (`parsers/banco_brasil.py`)

- **NÃO testado com PDF real** — estrutura inicial baseada no layout
  padrão Ourocard.
- Regex: `DD/MM DESCRIÇÃO VALOR`.
- Quando o usuário enviar um PDF do BB, **provavelmente vai precisar
  ajustar**: o início do bloco de lançamentos (atualmente procura
  `LANÇAMENTOS|Compras nacionais|Detalhamento da fatura`) e o fim
  (`Total da fatura|geral|nacional|internacional`).

### Categorias (`categorias.py`)

- Dicionário `CATEGORIAS` mapeia categoria → lista de palavras-chave
  (case-insensitive, `in` simples).
- **Ordem importa**: a primeira categoria que casar vence. Por isso
  `Combustível` vem antes de `Mercado` (alguns postos têm "shell" no
  nome que poderia confundir).
- **Default**: `"Outros Gastos"`.
- **Categorias hoje**: Combustível, Mercado, Alimentação, Farmácia, Saúde,
  Lazer, Assinatura Digital, Compra Digital, Vestuário, Transporte,
  Casa e Construção, Educação, Serviços/Assinaturas.
- O usuário editou este arquivo manualmente em algum momento — pode
  voltar a editar. Não reformatar o arquivo agressivamente sem necessidade.

### Detecção de titular (`parsers/base.py::detectar_titular`)

- Procura a linha em maiúsculas (2–6 palavras) que se repete mais vezes
  no PDF, ignorando palavras administrativas (lista `PALAVRAS_NAO_TITULAR`).
- Cuidado ao adicionar bancos novos: pode precisar incluir mais palavras
  na blocklist.

## 5. Como rodar e testar

```bash
cd /Users/eliabenextil/Projects/gastometro
source .venv/bin/activate
python extrator.py                          # todos os PDFs da pasta
python extrator.py Fatura_05_2026.pdf       # um PDF específico
python extrator.py /caminho/para/pasta/     # todos os PDFs da pasta
python extrator.py aprender                 # transforma edições manuais da coluna
                                            # Categoria do Excel em overrides no JSON
python extrator.py recategorizar            # re-aplica categorias atuais em TODO o
                                            # Excel (sem reler PDFs) e reconstrói as
                                            # abas analíticas — preserva filtros
```

**Fluxo seguro quando você editou `categorias.py` ou
`categorias_usuario.json` e quer propagar para o Excel inteiro:**

```bash
python extrator.py aprender         # captura edições manuais do Excel no JSON
python extrator.py recategorizar    # propaga dicionário + JSON para todas as linhas
```

Sem o `recategorizar`, as linhas antigas no Excel mantêm a categoria
gravada na execução em que a fatura foi adicionada — apenas faturas
novas usam o dicionário atual. Apagar o `saida/gastometro.xlsx` e
rodar `python extrator.py` também recategoriza tudo, mas reprocessa
todos os PDFs (mais lento).

Para depurar o que o pdfplumber está extraindo:

```python
import pdfplumber
with pdfplumber.open("arquivo.pdf") as pdf:
    for i, p in enumerate(pdf.pages):
        print(f"=== PÁGINA {i+1} ===")
        print(p.extract_text())
```

Para inspecionar o Excel gerado:

```python
import pandas as pd
print(pd.read_excel("Fatura.xlsx", sheet_name="Informações").to_string(index=False))
print(pd.read_excel("Fatura.xlsx", sheet_name="Transações").to_string(index=False))
print(pd.read_excel("Fatura.xlsx", sheet_name="Resumo por Categoria").to_string(index=False))
```

## 6. Próximos passos sugeridos

> **O backlog vivo está em `MELHORIAS.md`** — consulte esse arquivo para
> a lista completa, com prioridade (P0–P3), esforço (XS–L) e status
> (`[ ]`/`[~]`/`[x]`) de cada item. Use-o como fonte da verdade ao
> decidir o que fazer em seguida e marque os itens à medida que forem
> concluídos.

Resumo das frentes mapeadas (detalhes em `MELHORIAS.md`):

1. **Robustez / bugs** — `parse_valor_brl` com múltiplos pontos,
   inferência de ano em parcelas antigas, aviso quando soma diverge do
   total, limpeza de dados pessoais no código.
2. **Categorização** — duplicatas no dicionário, falsos positivos por
   substring, aprendizado a partir do usuário, visibilidade do "Outros
   Gastos".
3. **Testes automatizados** — pytest, cobertura mínima para
   `parse_valor_brl`, `categorizar`, parsers.
4. **Arquitetura** — desacoplar parser/categorização, mover utilidades
   compartilhadas para `parsers/base.py`, refatorar `_montar_transacoes`
   do Ailos.
5. **Features de valor** — consolidação multi-fatura, gráficos no
   Excel, Streamlit, novos bancos (Itaú, Bradesco, Inter, C6),
   detecção de duplicatas, comparativo mensal.
6. **Tooling / DX** — `ruff` + `mypy`, GitHub Actions, `pre-commit`,
   `logging` no lugar de `print`, pacote instalável com `argparse`.
7. **Segurança** — checar histórico do git por PDFs commitados, hook
   `pre-commit` para bloquear `*.pdf`/`*.xlsx`.
8. **Documentação** — typo `gastrometro/` no README, LICENSE,
   CHANGELOG, tutorial "como adicionar um banco", GIF do Excel gerado.

## 6.1. O que foi feito nesta sessão (22/05/2026)

- Mapeamento completo dos pontos de melhoria a partir da leitura do
  código e do HANDOFF anterior.
- Criado `MELHORIAS.md` como backlog vivo (checklist com prioridade,
  esforço e status). Atualizar conforme avanço.

## 6.2. O que foi feito em 23/05/2026 — Relatórios por cartão

Pedido do usuário: "valor separado de cada cartão mensal e por
categorias, filtros para ajudar na análise, outras sugestões de
relatório bastante usadas". Implementado e validado contra o Excel
real (33 faturas, 916 transações, R$ 76.772,55).

- **Conceito de "cartão"** = `Banco — Titular`. Distingue cartões com
  o mesmo banco mas titulares diferentes (Nubank do Eliabe vs Nubank
  da Ana) e cartões do mesmo titular em bancos diferentes (Ailos vs
  Nubank do Eliabe). Helper: `extrator._identificador_cartao`.
- **Coluna `Cartão`** adicionada às abas `Informações` e `Transações`.
  Retrocompatibilidade automática: Excel antigo sem essa coluna é
  migrado na próxima execução (sem reprocessar PDFs).
- **5 novas abas no Excel** (em `extrator.salvar_excel_acumulativo`):
  - `Resumo por Cartão` (uma linha por cartão com totais e médias).
  - `Cartão x Mês` (pivot referência × cartão).
  - `Cartão x Categoria` (pivot categoria × cartão).
  - `Top Comerciantes` (top 30 descrições por valor acumulado).
  - `Recorrentes` (descrições que aparecem em 3+ meses).
- **Filtros nativos** (`auto_filter`) aplicados em `Informações`,
  `Transações`, `Top Comerciantes` e `Recorrentes`. Usuário usa a
  setinha do Excel para filtrar por cartão, categoria, mês, etc.,
  sem configurar nada.
- **Formatação R$** expandida para colunas `Total`, `Médio`, `Média`
  (antes só `Valor`/`Total`).

Detalhes em `MELHORIAS.md` (item 5.11 + Concluídas/23/05/2026).
Próximas frentes correlatas mapeadas: 5.12 (`Maiores Gastos`),
5.13 (`Estornos`), 5.14 (variação % mensal), 5.15 (gráficos por
cartão).

## 6.3. O que foi feito em 25/05/2026 — Fundação de testes (Bloco A)

- **3.1** — Setup do `pytest` com pasta `tests/`, `conftest.py` que
  insere a raiz no `sys.path` e isola cada teste do
  `categorias_usuario.json` real (fixture autouse + cache-clear).
  Novo `requirements-dev.txt` (`-r requirements.txt` + `pytest>=8`).
- **3.2** — `tests/test_parse_valor_brl.py` (27 testes): formato BR,
  formato americano (Ailos), `R$`, negativos com `\u2212`, trailing
  punctuation (`4,422.81.`), entradas inválidas, zero.
- **3.3** — `tests/test_categorias.py` (68 testes): smoke positivo
  para **todas** as 15 categorias do dicionário, boundary semântico
  (`raia` vs `RAIANE`, `big` vs `BIGODE`), prefix match (`*`),
  regras negativas (`!mercado pago`), normalização (acentos/caixa),
  overrides do usuário com precedência, JSON corrompido,
  `categorizar_pelo_dicionario` ignorando overrides, e
  `salvar_categorias_usuario` (persistência + cache-clear).
- **3.4** — `tests/test_inferencia.py` (14 testes):
  `referencia_pelo_vencimento`, `ano_do_vencimento` e cobertura
  ampla de `inferir_ano_transacao` com e sem recuo por parcela
  (regressão `MAPFRE 14 JAN 16/18` em fatura de maio/2026 → 2025).
- **7.2** — Auditoria do histórico git: `git log --all -- '*.pdf'
  '*.xlsx'` e varredura de `.csv`/`.xls` em todo o histórico → 0
  binários sensíveis em qualquer branch. `.gitignore` já protege.

Suite roda em ~0.2s: **109 passed**. Comando padrão:

```bash
python -m pytest -q
```

## 7. Gotchas / armadilhas conhecidas

- **Cidade pode vir truncada**: o PDF da Ailos corta cidades longas
  (ex: "JARAGUA DO SUL" vira "JARAGUA DO"). Não é bug nosso, é como o PDF
  exporta. Decidi manter como informativo sem tentar reconstruir.
- **`extract_text()` pode juntar linhas inesperadamente** em PDFs com
  layout complexo — sempre que adicionar novo banco, inspecionar o
  output bruto antes de escrever regex.
- **Vírgula vs ponto decimal**: o Ailos usa ponto (`R$ 1.234.56`) e o
  Nubank usa vírgula (`R$ 1.234,56`). A função `parse_valor_brl` em
  `parsers/base.py` trata os dois.
- **Datas sem ano**: faturas mostram só `DD MMM` ou `DD/MM`. O ano é
  inferido pelo `data_vencimento` extraído da fatura. Cuidado com
  transações de meses anteriores (ex: parcela de janeiro numa fatura de
  maio) — atualmente assumimos o mesmo ano do vencimento, o que pode
  estar errado para parcelamentos longos. Tem o `MAPFRE SEGUROS` de
  14 JAN na fatura Ailos como caso de teste.

## 8. Regras do usuário

- **Sempre responder em português**.
- **Não fazer commits sem pedido explícito** (já fiz o primeiro porque
  foi pedido).
- **Não usar emojis** salvo se o usuário pedir.

## 9. Última interação

Push para o GitHub já realizado (`origin/main`). O usuário pediu para
consolidar as sugestões de melhoria em um arquivo de acompanhamento
(`MELHORIAS.md`) e seguir aplicando as melhorias uma a uma, dando
commit a cada item concluído.

Próxima ação esperada do agente: pegar o próximo item `[ ]` em
`MELHORIAS.md` (priorizando P0/P1 com baixo esforço) e implementar.