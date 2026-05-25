# Melhorias — Projeto gastometro

> Backlog vivo de melhorias do projeto. Atualizar conforme itens são
> concluídos ou novos são propostos.
>
> **Como usar**: marque `[x]` quando concluir, mova para a seção
> "Concluídas" no fim do arquivo, registre a data e o commit relacionado.

## Legenda

- **Prioridade**: P0 (crítico) / P1 (alto) / P2 (médio) / P3 (baixo)
- **Esforço**: XS (<30 min) / S (~1h) / M (meio dia) / L (1 dia+)
- **Status**: `[ ]` pendente / `[~]` em andamento / `[x]` concluído

---

## 1. Robustez e correção de bugs

- [ ] **1.1 — Testes e robustez de `parse_valor_brl`** — P2 / S
  - Verificado em 22/05/2026 que o caso `"1.234.56"` (ponto como milhar e
    decimal) descrito originalmente no HANDOFF **não ocorre** nas faturas
    Ailos reais; o que aparece é o formato americano `"1,234.56"` (já
    suportado). O bug do trailing `.` foi corrigido junto com o item 1.3
    (`rstrip(".,")` na função).
  - Pendente: bateria de testes unitários cobrindo
    `"1.234,56"`, `"1,234.56"`, `"1234,56"`, `"4,422.81."`,
    `"-R$ 50,00"`, `"R$ 0,00"`, `"\u22125,00"`, vazios e `None`.

- [x] **1.2 — Inferência de ano errada em parcelas antigas** — P1 / S
  - Concluído em 22/05/2026 (ver "Concluídas").

- [x] **1.3 — Avisar quando soma diverge do total da fatura** — P1 / XS
  - Concluído em 22/05/2026 (ver "Concluídas").

- [x] **1.4 — Remover dados pessoais de `PALAVRAS_NAO_TITULAR`** — P0 / XS
  - Concluído em 22/05/2026 (ver "Concluídas").

- [x] **1.5 — `import pandas` dentro de função (3 lugares)** — P3 / XS
  - Concluído em 22/05/2026 (ver "Concluídas").

- [ ] **1.6 — PDF lido duas vezes (detecção + extração)** — P2 / S
  - `parsers/__init__.py::detectar_banco` + `extrair_fatura` chamam `_ler_texto` independentemente.
  - Refatorar para abrir o PDF uma vez e reaproveitar o texto.

- [x] **1.7 — Capturar anuidade e preservar sinal de estornos (Ailos)** — P1 / S
  - **Anuidade**: aparece na seção `MOVIMENTAÇÕES DA CONTA` acima do
    cabeçalho da tabela principal, em layout próprio (3 linhas:
    descrição / data+valor / `(NNNN) X/Y`). Hoje o parser descarta
    tudo acima do cabeçalho. Resultado: o `valor_total` declarado
    pela fatura diverge da soma das transações (caso visto:
    `Fatura_02_2026.pdf` com diferença de R$ 11,67).
  - **Estornos**: o pdfplumber separa `"-R$"` e o número em dois
    tokens distintos; `_parse_valor_tokens` pega o numérico primeiro
    e perde o sinal, registrando o estorno como valor positivo
    (caso visto: `Fatura_04_2026.pdf`, MERCADOLIVRE*TOTALMO 2026-03-04,
    `-R$ 39,99` registrado como `+R$ 39,99` → soma 4.270,35 vs total
    4.190,37 = +R$ 79,98).
  - Lançamentos administrativos a manter como descartados: `SALDO
    ANTERIOR`, `PAGTO DEB EM CONTA`, `PAGAMENTO RECEBIDO/EFETUADO`,
    `TOTAL DE`, `TOTAL R$`.
  - Lançamentos a aceitar como transações reais: `ANUIDADE
    MASTERCARD`, `DESC ANUIDADE` (desconto/isenção, valor negativo
    ou zero), estornos comuns na tabela principal.

- [x] **1.8 — Divergências em algumas faturas Nubank** — P1 / M
  - Resolvidas todas as divergências de cálculo (de 7 → 0); restam
    apenas 3 avisos informativos sobre **estornos**, conforme detalhe
    na seção "Concluídas" abaixo.

- [x] **1.9 — Parcela do Ailos vazando para a coluna Cidade** — P1 / XS
  - Concluído em 22/05/2026 (ver "Concluídas").

- [ ] **1.10 — Cidade truncada em algumas linhas Ailos (`DO JARAGUA DO`)** — P2 / S
  - Quando a descrição é longa, o Ailos quebra o lançamento em **duas
    linhas visuais** com `top` ~4pt de diferença (ex.: linha 1
    "00401 SH JARAGUA DO" + linha 2 "11 NOV JARAGUA DO SU R$ 93.23").
    `_agrupar_palavras_em_linhas` usa tolerância 3pt e separa as
    duas → metade do nome da loja vai para `desc` e a outra metade
    fica como "cidade" (`DO JARAGUA DO`).
  - Subir a tolerância para ~5pt ou implementar um pós-merge das
    linhas adjacentes do mesmo lançamento.

## 2. Categorização (`categorias.py`)

- [ ] **2.1 — Duplicatas e conflitos no dicionário** — P2 / XS
  - `apple.com/bill` e `google play` estão em "Assinatura Digital" **e** "Compra Digital" (a segunda nunca pega).
  - `"mercado pago"` aparece duas vezes na mesma categoria.
  - Consolidar e decidir critério.

- [x] **2.2 — Casamento por substring gera falsos positivos** — P1 / M
  - Concluído em 22/05/2026 (ver "Concluídas").

- [x] **2.3 — Aprendizado a partir do usuário** — P2 / M
  - Concluído em 22/05/2026 (ver "Concluídas").

- [x] **2.4 — Visibilidade do "Outros Gastos"** — P2 / S
  - Concluído em 22/05/2026 (ver "Concluídas").

- [x] **2.5 — Recategorizar Excel sem reler PDFs** — P1 / S
  - Concluído em 25/05/2026 (ver "Concluídas").

## 3. Testes automatizados

- [x] **3.1 — Setup do pytest** — P1 / XS
  - Concluído em 25/05/2026 (ver "Concluídas").

- [x] **3.2 — Testes de `parse_valor_brl`** — P1 / S
  - Concluído em 25/05/2026 (ver "Concluídas").

- [x] **3.3 — Testes de `categorizar`** — P1 / S
  - Concluído em 25/05/2026 (ver "Concluídas").

- [x] **3.4 — Testes de `referencia_pelo_vencimento` e ano por parcela** — P1 / XS
  - Concluído em 25/05/2026 (ver "Concluídas").

- [ ] **3.5 — Smoke tests dos parsers com fixtures de texto** — P2 / M
  - Salvar o texto bruto extraído de cada PDF de teste em `tests/fixtures/*.txt` e validar contagem/total.

- [ ] **3.6 — Anonimizar 1 PDF de exemplo em `exemplos/`** — P3 / M
  - Trocar nome do titular por "FULANO TESTE" e mascarar finais de cartão.

## 4. Arquitetura

- [ ] **4.1 — Desacoplar parser de categorização** — P2 / S
  - Parsers devolvem `Transacao` com `categoria=""`; o `extrator.py` aplica `categorizar()` num passo separado.
  - Remove import `from categorias import categorizar` dos 3 parsers.
  - Permite reprocessar Excel sem reabrir PDF.

- [x] **4.2 — Mover `_ano_do_vencimento` para `parsers/base.py`** — P3 / XS
  - Concluído em 22/05/2026 (ver "Concluídas").

- [ ] **4.3 — Definir Protocol/ABC para parser** — P3 / S
  - Contrato `detectar() -> bool`, `extrair(pdf) -> Fatura`, `NOME_BANCO: str`.

- [ ] **4.4 — Refatorar `_montar_transacoes` do Ailos** — P2 / M
  - 85 linhas com várias mutações de estado (`desc_pendente`, `cidade_pendente`).
  - Quebrar em funções menores ou pequena máquina de estados.

## 5. Features

- [x] **5.1 — Consolidação multi-fatura** — P1 / M
  - Concluído em 25/05/2026 (ver "Concluídas").

- [x] **5.2 — Gráficos no Excel** — P2 / S
  - Concluído em 25/05/2026 (ver "Concluídas").

- [x] **5.11 — Relatórios por cartão + abas analíticas + filtros nativos** — P1 / M
  - Concluído em 23/05/2026 (ver "Concluídas").

- [x] **5.12 — Aba `Maiores Gastos` (top transações individuais)** — P2 / XS
  - Concluído em 25/05/2026 (ver "Concluídas").

- [x] **5.13 — Aba `Estornos` dedicada** — P3 / XS
  - Concluído em 25/05/2026 (ver "Concluídas").

- [x] **5.14 — Variação % vs mês anterior no Resumo Mensal** — P2 / S
  - Concluído em 25/05/2026 (ver "Concluídas").

- [x] **5.15 — Tendência por cartão (gráfico de linha)** — P3 / S
  - Concluído em 25/05/2026 (ver "Concluídas").

- [ ] **5.3 — Interface Streamlit** — P2 / M
  - Drag-and-drop de PDF, baixar Excel.

- [ ] **5.4 — Suporte a outros bancos populares** — P2 / L
  - Itaú, Bradesco, Inter, C6. Um arquivo por banco em `parsers/`.

- [ ] **5.5 — Detecção de duplicatas entre faturas** — P2 / S
  - Útil ao consolidar; pega cobrança em duplicidade.

- [x] **5.6 — Comparativo mensal automático** — P2 / S
  - Concluído em 25/05/2026 (ver "Concluídas").

- [ ] **5.7 — Exportar JSON/CSV além de Excel** — P3 / XS

- [ ] **5.8 — Modo "diff" (apenas lançamentos novos)** — P3 / M

- [ ] **5.9 — Alertas configuráveis (`config.yaml`)** — P3 / M

- [x] **5.10 — Excel único acumulativo + pastas `entrada/`/`saida/`** — P1 / S
  - Concluído em 22/05/2026 (ver "Concluídas").

## 6. Tooling / DX

- [x] **6.1 — `pyproject.toml` + `ruff` + `mypy`** — P2 / S
  - Concluído em 25/05/2026 (ver "Concluídas").

- [ ] **6.2 — GitHub Actions: `pytest` + `ruff` em cada push** — P2 / S

- [ ] **6.3 — `pre-commit` bloqueando PDFs/XLSX por engano** — P3 / S

- [ ] **6.4 — Substituir `print` por `logging`** — P3 / S
  - Permite `--quiet`, `--debug` e log em arquivo.

- [ ] **6.5 — Pacote instalável (`pip install -e .`) com entrypoint `gastometro`** — P2 / S

- [ ] **6.6 — `argparse` no lugar de `sys.argv[1]`** — P2 / XS
  - Flags: `--output`, `--quiet`, `--banco=ailos`, `--no-categorize`.

## 7. Segurança e privacidade

- [x] **7.1 — Limpar dados pessoais do código** — P0 / XS
  - Duplicado do 1.4. Concluído em 22/05/2026.

- [x] **7.2 — Verificar histórico do git por PDFs commitados** — P1 / XS
  - Concluído em 25/05/2026 (ver "Concluídas").

- [ ] **7.3 — `pre-commit` hook bloqueando dados sensíveis** — P2 / S
  - Mesma ideia do 6.3.

## 8. Documentação

- [ ] **8.1 — Corrigir typo `gastrometro/` no README** — P3 / XS
  - Linha 81 do `README.md`.

- [ ] **8.2 — Adicionar LICENSE (MIT)** — P3 / XS

- [ ] **8.3 — Criar CHANGELOG.md** — P3 / XS

- [ ] **8.4 — Tutorial "adicionar um banco" com exemplo concreto** — P3 / S

- [ ] **8.5 — Screenshot/GIF do Excel gerado no README** — P3 / S

---

## Concluídas

### 25/05/2026 (Tooling — 6.1)

- **6.1 — `pyproject.toml` + `ruff` + `mypy`**
  - Criado `pyproject.toml` com:
    - Metadados (`name`, `version`, `description`, `requires-python
      = ">=3.10"`, `license = MIT`).
    - `dependencies` espelhando `requirements.txt`.
    - `optional-dependencies.dev = [pytest>=8.0, ruff>=0.6,
      mypy>=1.10]`.
    - `project.scripts.gastometro = "extrator:main"` (entry point
      após `pip install -e ".[dev]"`).
    - `[tool.setuptools]` apontando os módulos top-level
      (`extrator`, `categorias`) e o pacote `parsers`.
  - **Ruff**: `target-version = "py310"`, `line-length = 100`,
    rules `["E", "F", "I", "B", "UP", "W", "SIM"]`, ignores
    `["E501", "B008"]`. Per-file: `tests/*` libera `E501` e
    `__init__.py` libera `F401`.
  - **Mypy**: `python_version = "3.10"`, permissivo no início
    (`ignore_missing_imports`, `check_untyped_defs`,
    `no_implicit_optional`, `warn_unused_ignores`); `tests.*`
    isenta `disallow_untyped_defs`.
  - **Pytest**: `[tool.pytest.ini_options]` define `testpaths
    = ["tests"]` e `addopts = "-q"`.
  - **Fixes do ruff** (12 → 0): `I001` (imports), `UP035`
    (`collections.abc.Iterable`), `B905` (`zip(..., strict=False)`
    em `_garantir_coluna_cartao`), `E741` (renomear variável `l`
    → `bucket` em `parsers/ailos.py::_classificar_palavras_em_colunas`).
  - **Fixes do mypy** (4 → 0): `parse_valor_brl(texto: str | None)`
    (já tratava None, agora o tipo bate); `Ailos._Linha.tem_data`
    devolve `bool(...)` (`re.match` é `Match | None`, fazia
    `bool | None`); `linha` reaproveitado com dois tipos
    diferentes em `_extrair_movimentacoes_conta` → renomeado o
    `for` interno para `texto_linha`.
  - `requirements-dev.txt` ganhou `ruff>=0.6` e `mypy>=1.10`.
  - **Resultado**: `ruff check .` → "All checks passed"; `mypy .`
    → "Success: no issues found in 12 source files"; `pytest`
    → 109 passed.

### 25/05/2026 (Bloco C — Estornos, Comparativo e tendência por cartão)

- **5.13 — Aba `Estornos`**
  - Nova função `_construir_estornos(df)` em `extrator.py` que
    filtra `Valor (R$) < 0` e ordena pelas referências mais
    recentes, desempate pelo |valor| (estornos grandes primeiro).
    Colunas: `Data, Referência, Descrição, Categoria, Cartão,
    Cidade, Valor (R$), Arquivo`.
  - Aba registrada em `ABAS_COM_FILTRO` (filtro nativo do Excel).
  - **Validação real**: 14 estornos no Excel — `DESC ANUIDADE POR
    USO` (Ailos, vários meses), `MERCADOLIVRE*TOTALMO -R$ 39,99`
    em Abril/2026 (regressão do item 1.7), `Estorno de "Localiza
    Rac"` -R$ 162,22 em Maio/2024 (regressão do item 1.8 Nubank
    antigo). Todos com sinal **negativo** preservado.

- **5.1 — Aba `Comparativo` (Categoria × último vs penúltimo mês)**
  - Nova função `_construir_comparativo(df)` produz a versão
    tabular do `_imprimir_comparativo_mensal` que vai pro terminal.
    Colunas: `Categoria, <Penúltimo Mês> (R$), <Último Mês> (R$),
    Δ Absoluto (R$), Δ %`. Headers das colunas de valor são
    **dinâmicos** (incluem o nome do mês: `Abril/2026 (R$)` /
    `Maio/2026 (R$)`).
  - Ordenada por `|Δ Absoluto|` decrescente — primeiro o que mais
    mexeu na fatura, mesmo que em percentual seja pequeno. Inclui
    linha `TOTAL` no fim.
  - Categorias que não existiam no mês anterior recebem `Δ %`
    nulo (não dá pra dividir por zero); o terminal já marca esses
    casos como `(novo)`.
  - **Fechamento do item 5.1**: o objetivo original era um "Excel
    mestre com aba Consolidado + Comparativo (categoria × mês)".
    O `Consolidado` já existia (aba `Transações` agrega todas as
    faturas desde o item 5.10) e o pivot `categoria × mês` está
    no `Resumo Mensal` (com `Variação %` desde o Bloco B). A aba
    `Comparativo` agora fecha o item ao mostrar a versão
    categórica do último vs penúltimo mês.
  - **Validação real**: top linhas batem com o terminal:
    `Alimentação +267.9%`, `Mercado -33.1%`, `Combustível +46.4%`,
    `TOTAL +9.5%`.

- **5.15 — Gráfico `Tendência por Cartão` (LineChart)**
  - Nova função `_adicionar_grafico_tendencia_cartoes` desenha um
    `LineChart` na aba `Cartão x Mês`, abaixo dos dados. Cada
    cartão (colunas entre `Referência` e `Total`) vira uma série
    no tempo; X = referências (sem a linha `TOTAL`); dimensões
    24 × 12 cm.
  - Helper protege contra dados insuficientes (< 2 meses ou tabela
    sem colunas de cartão entre `Referência` e `Total`).
  - **Validação real**: `wb['Cartão x Mês']._charts` → 1
    `LineChart` com título "Tendência por Cartão".

- **Formatação `_formatar_planilha`** ganhou `R$` como gatilho de
  formato R$ (necessário para a aba `Comparativo` com colunas tipo
  `Maio/2026 (R$)` e `Δ Absoluto (R$)`).

- **Idempotência mantida**: 2× `recategorizar` → 0 mudanças, abas
  e gráficos recriados sem drift.

### 25/05/2026 (Bloco B — features visíveis no Excel + terminal)

- **5.12 — Aba `Maiores Gastos`**
  - Nova função `_construir_top_transacoes(df, top_n=20)` em
    `extrator.py`. Retorna as 20 transações individuais de maior
    valor (apenas gastos, ignora estornos), com colunas
    `Data, Referência, Descrição, Categoria, Cartão, Parcela,
    Cidade, Valor (R$)`. Aba inclui filtros nativos e formatação R$.
  - Diferente de `Top Comerciantes` (agrupado por descrição): aqui
    cada linha é uma compra única — útil para revisar parcelas
    altas, hotéis, eletrodomésticos, etc.
  - **Validação**: no Excel real (943 transações) a aba traz top:
    `Truts Mercado R$ 808,85`, `KOMPRAO ATACADISTA R$ 755,21`,
    `KOMPRAO KOCH R$ 724,61`.

- **5.14 — Coluna `Variação %` no Resumo Mensal**
  - Adicionada após `Total` no pivot de `_construir_resumo_mensal`.
    Calculada como `(total_mes - total_mes_anterior) /
    total_mes_anterior * 100` em pontos percentuais.
  - Em branco no 1º mês (sem anterior) e na linha `TOTAL` (somar
    variações é sem sentido). A linha `TOTAL` agora é recalculada
    a partir de `pivot.drop(columns=["Variação %"]).sum(axis=0)`
    para não somar a coluna percentual.
  - Formato custom em `_formatar_planilha`:
    `'+0.0"%";-0.0"%";0.0"%"'` (mostra sinal para positivos e
    negativos). Toda coluna cujo header contenha `%` agora pula o
    formato R$ e usa o formato percentual.
  - **Validação** no Excel real: Maio/2026 = R$ 5.355,35 (+9.5%
    vs Abril/2026), Abril = +20.2% vs Março, etc. Bate com o
    comparativo do terminal.

- **5.2 — Gráficos no Excel**
  - `PieChart` em `Resumo por Categoria` (título "Distribuição por
    Categoria", posicionado em D2): rótulos = categorias, dados =
    coluna `Valor (R$)`, **excluindo** a linha `TOTAL GERAL`.
  - `BarChart` em `Resumo Mensal` (título "Total Mensal", posicionado
    embaixo dos dados): eixo X = meses (excluindo linha `TOTAL`),
    eixo Y = coluna `Total`. Dimensões: 22 × 10 cm.
  - Implementado com `openpyxl.chart.{PieChart, BarChart, Reference}`.
    Os gráficos referenciam células diretamente, então acompanham
    edições futuras (filtro, ordenação) automaticamente.
  - Helpers protegem contra dados insuficientes (`< 2` meses ou
    `< 3` categorias).
  - **Validação**: `wb['Resumo por Categoria']._charts` = 1
    `PieChart`; `wb['Resumo Mensal']._charts` = 1 `BarChart`.

- **5.6 — Comparativo mensal automático no terminal**
  - Nova função `_imprimir_comparativo_mensal(df)` chamada após
    `_imprimir_top_outros_gastos` em todos os fluxos (`processar`,
    `recategorizar_excel`, migração de Excel antigo).
  - Compara o último mês com o anterior:
    - Linha `TOTAL`: variação % e absoluta vs mês anterior.
    - Top 8 categorias por |Δ|: variação % e absoluta. Quando a
      categoria não existia no mês anterior, mostra `(novo,
      +R$ X,YY)`.
  - Helper `_formatar_brl(valor)` formata em moeda BR sem depender
    de `locale` (`1.234,56` em vez de `1,234.56`).
  - **Validação real**: comparativo Maio/2026 vs Abril/2026 →
    `TOTAL R$ 5.355,35 (+9.5% / +462,78)`, com destaque para
    `Alimentação +267.9%`, `Mercado -33.1%`, `Combustível +46.4%`.

- **Idempotência**: rodei `recategorizar` 2× sobre o mesmo Excel →
  0 mudanças na 2ª execução, charts e variação recriados sem drift.

### 25/05/2026 (Bloco A — fundação de testes)

- **3.1 — Setup do pytest**
  - Criada pasta `tests/` com `__init__.py` e `conftest.py`. O conftest
    insere a raiz no `sys.path` (sem precisar instalar o pacote) e um
    fixture `autouse` aponta `categorias.CATEGORIAS_USUARIO_ARQUIVO`
    para um JSON temporário em cada teste — isola o suite do
    `categorias_usuario.json` real do usuário e zera os caches
    `lru_cache` de `_regras_compiladas`/`_carregar_categorias_usuario`
    antes e depois.
  - Novo `requirements-dev.txt` com `-r requirements.txt` + `pytest>=8`.
  - Executar: `python -m pytest -q` na raiz do projeto.

- **3.2 — Testes de `parse_valor_brl`** (`tests/test_parse_valor_brl.py`)
  - 6 classes cobrindo formato BR (`1.234,56`), formato americano usado
    na Ailos (`1,234.56`, `4,422.81`), símbolo `R$` (com/sem espaço),
    negativos (`-R$ 50,00`, unicode `\u2212`), trailing punctuation
    (`4,422.81.`, `1.234,56,`, `99,00,.,`), entradas inválidas
    (`None`, vazia, só símbolo, só pontuação) e o zero (BR + US).
  - 27 testes no total — protegem contra regressão do bug de trailing
    period que foi corrigido junto com o item 1.3.

- **3.3 — Testes de `categorizar`** (`tests/test_categorias.py`)
  - **Smoke positivo**: 38 cenários parametrizados cobrindo ≥2
    descrições por categoria (Combustível, Mercado, Alimentação,
    Farmácia, Saúde, Lazer, Assinatura Digital, Compra Digital,
    Vestuário, Manutenção Carro, Transporte, Casa e Construção,
    Educação, Seguro, Serviços / Assinaturas).
  - **Boundary semântico**: `RAIANE OFICINA` não vira Farmácia,
    `BIGODE LANCHES` cai em Alimentação (não em Mercado por causa do
    `big`), `EOMERCADO XPTO` não casa `mercado` por substring.
  - **Prefix match `*`**: `POSTOZ19`, `SHELLBO`, `LANCHONETE` (todos
    para a categoria certa).
  - **Regras negativas `!`**: `MERCADO PAGO BR` → Compra Digital
    (não Mercado), `MERCADO LIVRE COMPRA` idem, e `SUPERMERCADO
    ANGELONI` continua Mercado.
  - **Fallback**: descrição vazia, `None`, texto sem keyword caem em
    "Outros Gastos".
  - **Normalização**: acentos, caixa baixa e espaços extras.
  - **Overrides do usuário**: precedem o dicionário; chave do JSON é
    normalizada; `categorizar_pelo_dicionario` ignora overrides; JSON
    corrompido não quebra.
  - **`salvar_categorias_usuario`**: persiste, normaliza chaves,
    descarta valores vazios/branco e invalida o `lru_cache` (a
    próxima chamada de `categorizar` enxerga a mudança).
  - 68 testes no total.

- **3.4 — Testes de inferência de ano** (`tests/test_inferencia.py`)
  - `referencia_pelo_vencimento` (Janeiro/2026, Dezembro/2025,
    Maio/2026, formato inválido, string vazia).
  - `ano_do_vencimento` (ano explícito, ano passado, fallback para o
    ano atual em formato inválido).
  - `inferir_ano_transacao` **sem recuo** (caso Nubank): dezembro em
    fatura de janeiro/2026 → 2025; novembro em fatura de janeiro →
    2025; mesmo mês do vencimento → mesmo ano; parcela é ignorada
    quando o recuo está desligado.
  - `inferir_ano_transacao` **com recuo por parcela** (caso Ailos):
    parcela `16/18` em fatura de maio/2026 com mês de transação
    janeiro → 2025 (regressão original `MAPFRE 14 JAN 16/18`);
    parcela `1/12` não recua; parcela `2/12` recua 1 mês; parcela
    `3/12` dentro do mesmo ano; parcela malformada (`abc`) cai na
    regra base; parcela vazia também.
  - Vencimento vazio/malformado devolve um ano plausível (2024–2100)
    sem lançar exceção.
  - 14 testes no total.

- **Resultado do suite**: `python -m pytest -q` → **109 passed in 0.18s**.

- **7.2 — Auditoria do histórico git**
  - `git log --all -- '*.pdf' '*.xlsx'` e `git log --all
    --pretty=format: --name-only | grep -Ei '\.(pdf|xlsx|xls|csv)$'`
    → nenhum binário sensível em qualquer commit/branch.
  - `categorias_usuario.json` também nunca foi commitado.
  - `.gitignore` já bloqueia `*.pdf`, `*.xlsx` (whitelist `exemplos/`)
    e `categorias_usuario.json`. **Nada a limpar com BFG/filter-repo.**

### 25/05/2026

- **2.5 — Recategorizar Excel sem reler PDFs**
  - Novo subcomando `python extrator.py recategorizar [excel]` que lê
    a aba `Transações` do Excel, re-aplica `categorizar()` (dicionário
    + `categorias_usuario.json`) em cada linha e reescreve o arquivo,
    reconstruindo **todas** as abas analíticas (Resumo por Categoria,
    Resumo Mensal, Cartão × Mês, Cartão × Categoria, Top Comerciantes,
    Recorrentes). Preserva linhas, ordem, formatação e cabeçalhos —
    filtros e segmentações continuam apontando para os mesmos
    cabeçalhos.
  - Antes, qualquer mudança em `categorias.py`/JSON só afetava
    **faturas novas**; linhas antigas mantinham a categoria literal
    gravada na execução em que a fatura foi adicionada (a coluna é
    texto, não fórmula). Única alternativa era apagar
    `saida/gastometro.xlsx` e reprocessar todos os PDFs.
  - Implementação em `extrator.py::recategorizar_excel`: reusa
    `_carregar_excel_existente`, mapeia descrições para categorias
    novas, monta DataFrame de diff e chama `salvar_excel_acumulativo`
    sem retocar a aba `Informações`. Subcomando ligado em `main()`
    junto com `aprender` (`argv[0] in {"aprender", "recategorizar"}`).
  - **Cuidado documentado**: edições manuais na coluna `Categoria` do
    Excel que ainda não foram capturadas via `aprender` são
    sobrescritas. Fluxo seguro:

    ```bash
    python extrator.py aprender       # salva edicoes do Excel no JSON
    python extrator.py recategorizar  # propaga JSON + dicionario p/ tudo
    ```

  - **Validação** sobre o Excel real (943 transações):
    - Idempotência: 2ª execução = 0 mudanças.
    - Test de regressão: corrompi 5 categorias propositadamente,
      `recategorizar` corrigiu as 5 + outras 11 que estavam
      desatualizadas (descobri de quebra que o `tecnopan` tinha sido
      removido por engano de Casa e Construção em edição manual
      anterior — restaurado como `tecnopan*`).
    - Erro limpo quando o arquivo não existe (`exit code 1`).
  - Documentação atualizada em `README.md` (nova seção
    "Recategorizar o Excel inteiro" + atalho na seção
    "Re-processar uma fatura") e `HANDOFF.md` (seção 5 com os
    subcomandos novos e o fluxo recomendado).

### 23/05/2026

- **5.11 — Relatórios por cartão + abas analíticas + filtros nativos**
  - Atende ao pedido "valor separado de cada cartão mensal e por
    categorias, filtros para ajudar na análise". Cartão é definido como
    `Banco — Titular`, distinguindo Ailos/Nubank do mesmo titular e
    cartões do mesmo banco com titulares diferentes (ex.: Nubank do
    Eliabe vs Nubank da Ana Leticia).
  - **Coluna `Cartão`** adicionada às abas `Informações` e
    `Transações`. Calculada via novo helper
    `extrator._identificador_cartao(banco, titular)`. Continua exibindo
    `Banco` e `Titular` em colunas separadas (não quebra filtros
    existentes).
  - **Retrocompatibilidade**: ao carregar Excel antigo (sem `Cartão`),
    `_garantir_coluna_cartao` reconstrói a coluna a partir de
    `Banco`/`Titular` e o extrator regrava o arquivo automaticamente,
    avisando no terminal. Não exige reprocessar PDFs.
  - **Novas abas analíticas** (todas criadas em
    `extrator.salvar_excel_acumulativo`):
    - **Resumo por Cartão**: uma linha por cartão com `Qtde. Faturas`,
      `Qtde. Transações`, `Primeira/Última Referência`, `Total Gasto`,
      `Média por Fatura`, `Ticket Médio`. Inclui linha `TOTAL` no fim.
    - **Cartão x Mês**: pivot `Referência` × `Cartão`, com `Total`
      por mês e linha `TOTAL` agregada. Responde "quanto cada cartão
      gastou em cada mês".
    - **Cartão x Categoria**: pivot `Categoria` × `Cartão`, ordenado
      pelo total geral por categoria. Mostra como cada cartão se
      distribui por categoria (útil para decidir qual usar para
      quê).
    - **Top Comerciantes**: top 30 descrições por valor acumulado
      (ignora estornos via `Valor > 0`). Inclui `Categoria`
      (moda — categoria mais frequente para aquela descrição),
      `Cartão(ões)` onde apareceu, qtde. de transações, total e
      ticket médio.
    - **Recorrentes**: descrições que aparecem em pelo menos 3 meses
      distintos (parametrizado em `_construir_recorrentes`). Inclui
      qtde. de meses, total e média mensal real (`total / meses`).
      Mapeia gastos fixos (assinaturas, mensalidades, seguros) que
      escapam aos filtros por valor isolado.
  - **Filtros nativos do Excel**: `aba.auto_filter.ref` aplicado às
    abas `Informações`, `Transações`, `Top Comerciantes` e
    `Recorrentes` (lista em `ABAS_COM_FILTRO`). Permite usar a
    seta de filtro do Excel em qualquer coluna sem configurar nada.
  - **Formatação R$**: `_formatar_planilha` expandido para formatar
    como moeda também colunas `Total`, `Médio`, `Média` (não só
    `Valor`/`Total` como antes). Pivots `Cartão x …` herdam o
    tratamento de `Resumo Mensal` (todas as colunas a partir da
    segunda viram moeda) via constante `ABAS_VALOR_PIVOT`.
  - **Validação** sobre o Excel real (33 faturas, 916 transações,
    R$ 76.772,55):
    - 3 cartões detectados: `Ailos — Eliabe Gai` (15 faturas /
      R$ 53.197,73), `Nubank — Eliabe Gai` (14 faturas /
      R$ 16.725,66), `Nubank — Ana Leticia Silva Maciel` (4
      faturas / R$ 6.849,16).
    - TOTAL bate entre as três abas pivot
      (Cartão x Mês, Cartão x Categoria, Resumo por Cartão):
      R$ 76.772,55 em todas.
    - Migração do Excel antigo executada sem perda: as 916 linhas
      antigas mantiveram suas categorias originais (categorizações
      manuais e overrides via `categorias_usuario.json`).
  - **Sugestões adicionais registradas como próximas frentes** (não
    implementadas nesta sessão): 5.12 (`Maiores Gastos` — top
    transações individuais), 5.13 (`Estornos` em aba dedicada),
    5.14 (variação % vs mês anterior no Resumo Mensal), 5.15
    (gráfico de tendência por cartão, depende de 5.2).

### 22/05/2026

- **2.2 — Casamento por substring gera falsos positivos**
  - `categorizar` agora aplica regex com **boundary semântico** ao
    invés de `palavra in descricao`. A normalização tira acentos,
    aplica lower-case e colapsa espaços. Detalhes:
    - O início da keyword sempre exige boundary (não-alfanumérico
      ou começo de string) — `EOMERCADO` não casa `mercado`.
    - O final padrão proíbe **letra** mas admite dígitos — `RAIA`
      casa `RAIA419` mas não `RAIANE`; `BIG` casa `BIG SUPERMERC`
      mas não `BIGODE`.
    - Sufixo `*` ativa **prefix match** para descrições
      concatenadas comuns em fatura: `posto*` casa `POSTOZ19`,
      `shell*` casa `SHELLBO`, `komprao*` casa `KOMPRAO`,
      `spotify*` casa `SpotifyV`, `youtube*` casa
      `YouTubePremiu`, `descomplica*` casa `Descomplica Pos`.
    - Suporte a **regras negativas** com prefixo `!`: a categoria é
      descartada se a keyword excluída casar (ex.: `Mercado` tem
      `!mercado pago`, `!mercadolivre`, `!mercado livre`,
      `!bigode*`). Isso resolve os falsos positivos de Mercado
      Livre/Mercado Pago/Bigode.
  - Revisão do dicionário: adicionadas keywords com `*` para
    `kompra*`, `kompro*`, `condor*`, `eskimo*`, `autoposto*`,
    `restaurante*`, `pizzar*`, `padaria*`, `panificadora*`,
    `lanchonete*`, `cafe*`, `burger*`, `mcdonald*`, `farmacia*`,
    `drogaria*`, `panvel*`, `ultrafarma*`, `hospital*`,
    `clinica*`, `laboratorio*`, `odonto*`, `psicolog*`, `fisio*`,
    `unimed*`, `youtube*`, `spotify*`, `hbo*`, `disney*`,
    `microsoft*`, `steam*`, `playstation*`, `xbox*`,
    `applecombill*`, `shopee*`, `amazon*`, `magazineluiz*`,
    `mercadolivre*`, `mercadopago*`, `uber*`, `estacionamento*`,
    `estapar*`, `epar estacionament*`, `mecanica*`, `oficina*`,
    `autoeletrica*`, `leroy*`, `escola*`, `faculdade*`,
    `universidade*`, `curso*`, `livraria*`, `descomplica*`,
    `anuidade*`, `tarifa*`, `mensalidade*`, `seguro*`. Limpeza
    parcial das duplicatas de 2.1: removidos `amazonmkt`,
    `mercado pago` repetido, `applecombill` redundante.
  - **Validação**: comparação antes/depois sobre as 943 transações
    do Excel real → 58 categorias mudaram, **todas para melhor**:
    - 43 `MERCADOLIVRE*XXX` / `MERCADOPAGO *XXX` agora vão para
      Compra Digital (eram Mercado por substring).
    - 12 `BIGODEDEACO` / `MP *BIGODEDEACO` deixam de ser Mercado
      (falso positivo `big`); ficam em Outros Gastos para
      tratamento via override ou categoria específica.
    - 36/36 casos sintéticos passam (incl. `RAIANE OFICINA` →
      Transporte, `BIGODE LANCHES` → Outros Gastos, `RAIA419` →
      Farmácia).
  - Documentação no docstring de `categorias.py` e no README.

- **1.9 — Parcela do Ailos vazando para a coluna Cidade**
  - `parsers/ailos.py::_classificar_palavras_em_colunas` aplicava
    classificação puramente posicional: tokens com X dentro do
    range da coluna `cidade` (limite_desc_cidade ≤ x <
    limite_cidade_valor) viravam `cidade_tokens`, **mesmo sendo
    indicadores de parcela** (`NN/MM`). O `_montar_transacoes`, por
    sua vez, só procurava parcela na descrição, então a parcela
    nunca era detectada e ficava grudada na cidade (ex.: cidade
    `'02/02 SAO PAULO'`).
  - Fix: classificação semântica antes da posicional — qualquer
    token que case `RE_PARCELA` (`^\d{1,2}/\d{1,2}$`) vai direto
    para `desc_tokens`, independente do X. Seguro porque `NN/MM`
    nunca aparece em data (`DD MMM`) ou valor (com `R$` ou só
    dígitos com `,`/`.`).
  - **Validação**: 15/15 Ailos seguem batendo total (delta R$ 0,00).
    Faturas afetadas:
    - `Fatura_01_2026.pdf`: MLP*NetshoesV agora com parc `02/02`
      e cidade `SAO PAULO`.
    - `Fatura_12_2025.pdf`: MLP*NetshoesV com parc `01/02`,
      cidade `SAO PAULO`.
    - 9 faturas tiveram aumento na contagem de parcelas detectadas
      (totais inalterados).
  - **Lateral encontrado e registrado em 1.10**: em algumas linhas
    longas (ex.: `00401 SH JARAGUA DO ... SU`) o agrupamento por
    `top` quebra a linha em duas (delta ~4pt > tolerância 3pt), e o
    resultado é uma cidade truncada (`DO JARAGUA DO`). Não afeta
    o total nem a parcela.

- **2.3 + 2.4 — Aprendizado por descrição + visibilidade dos "Outros Gastos"**
  - **2.3**: novo arquivo opcional `categorias_usuario.json` (na raiz,
    fora do git) com mapa `descrição → categoria`. Em `categorias.py`:
    - `_normalizar(texto)` aplica `unicodedata.NFD` para remover
      acentos, baixa caixa e colapsa espaços (`"MAPFRE  Seguros"` e
      `"mapfre seguros"` viram a mesma chave).
    - `_carregar_categorias_usuario()` lê o JSON com `lru_cache`,
      tolerando ausência ou JSON inválido (segue silencioso, item é
      opcional).
    - `categorizar()` consulta o override antes do dicionário fixo;
      cai no `categorizar_pelo_dicionario()` quando não há match.
    - `salvar_categorias_usuario(mapa)` persiste o JSON com chaves
      já normalizadas e invalida o cache.
  - **Comando `python extrator.py aprender [excel]`**: lê o Excel
    (padrão `saida/gastometro.xlsx`) e registra como override apenas
    as linhas cuja categoria salva difere do que o dicionário
    devolveria. Sobrescreve o JSON anterior. Útil para reaproveitar
    correções manuais que o usuário fez na coluna `Categoria` do
    Excel sem precisar inflar `categorias.py`.
  - **2.4**: `extrator.py::_imprimir_top_outros_gastos` lê o
    `DataFrame` final de transações, filtra `Categoria == "Outros
    Gastos"` com `Valor > 0` (ignora estornos), agrupa por descrição
    e imprime as 10 com maior soma. Mostra também a contagem
    (`N×`) e instruções de como categorizar.
  - **Privacidade**: `categorias_usuario.json` entrou no `.gitignore`
    (pode conter descrições com dados sensíveis).
  - **Validação**: ciclo completo testado nos 33 PDFs reais. Edição
    de 24 linhas do Excel (3 descrições distintas: `Localiza`,
    `MP *AUTOELETRICAA`, `Google YouTubePremiu`) gerou 5 entradas
    no JSON (graças à normalização) e, após apagar o Excel e
    reprocessar, todas as 24 transações foram categorizadas
    corretamente via override. As 3 descrições saíram do top-10 de
    "Outros Gastos".

- **1.8 — Divergências em faturas Nubank**
  - **`valor_total`**: agora `parsers/nubank.py::_extrair_metadata`
    prioriza `Total de compras` do `RESUMO DA FATURA` em vez de
    `Total a pagar`. Esse é o número correto para comparar com a
    soma das transações: `Total a pagar` inclui IOF, juros, multa
    e pagamentos parciais que não são "compras do mês".
  - **Formato antigo (até meados/2024)**: `RE_TRANSACAO` ficou mais
    permissivo — agora aceita linhas sem `R$` antes do valor
    (`DD MMM Descrição [- X/Y] valor`) e sinal negativo isolado
    (`-` ou `\u2212`) antes do valor. Resultado: `Nubank_2024-05-13.pdf`
    saiu de 0 para 27 transações.
  - **Parcelas no formato antigo**: novo `RE_PARCELA` aceita tanto
    `- Parcela X/Y` (formato atual) quanto `- X/Y` (formato antigo).
  - **Estornos**: linhas iniciadas por `Estorno de "X"` são
    registradas com valor negativo (crédito recebido), refletindo
    a realidade dos gastos do titular.
  - **Conciliação informativa**: `extrator.py::_conciliar_total`
    agora identifica quando a diferença bate com a soma dos
    estornos detectados e troca a mensagem padrão por uma
    informativa ("o banco computa o total bruto"). Útil porque o
    Nubank inclui o valor estornado dentro do `Total de compras`,
    enquanto nosso parser, corretamente, o trata como crédito.
  - **Validação**: 19/19 PDFs Nubank rodando sem erro; 16/19 com
    soma = `Total de compras` (delta R$ 0,00); os 3 restantes têm
    apenas estornos com mensagem informativa
    (`Nubank_2024-05/08/09-13.pdf`). 15/15 Ailos também continuam
    batendo exato. Excel total: 32 faturas, 942 transações
    (vs 914 antes — +28 transações capturadas da Nubank antiga).

- **1.7 — Anuidade Ailos capturada e estornos com sinal correto**
  - **Estornos**: `parsers/ailos.py::_parse_valor_tokens` agora detecta
    tokens `-R$`, `-` ou `\u2212` antes do número e propaga o sinal
    negativo. Caso `Fatura_04_2026.pdf` MERCADOLIVRE*TOTALMO 2026-03-04
    `-R$ 39,99` corrigido de `+39,99` para `-39,99`.
  - **Anuidade**: nova função `_extrair_movimentacoes_conta(coluna,
    data_vencimento)` processa a seção `MOVIMENTAÇÕES DA CONTA` que
    fica acima da tabela principal. Para evitar o intercalamento entre
    colunas que `extract_text()` causa, recebe o crop da coluna
    esquerda direto e localiza a faixa Y entre `MOVIMENTAÇÕES` e o
    cabeçalho `DATA DESCRIÇÃO`, depois agrupa palavras em linhas e
    aceita o padrão "descrição (linha anterior) / DD MMM valor /
    `(NNNN) X/Y` (linha seguinte)".
  - `ADMINISTRATIVOS` reduzido para os termos que realmente são
    metadados (`SALDO ANTERIOR`, `PAGTO DEB EM CONTA`, `PAGAMENTO
    RECEBIDO/EFETUADO`, `TOTAL DE`, `TOTAL R$`); `ANUIDADE
    MASTERCARD`, `DESC ANUIDADE` e `ESTORNO` saíram da lista e voltam
    como transações reais quando aplicável.
  - **Validação**: 15 PDFs Ailos rodados pelo `extrator.py`, todos
    com soma das transações batendo exatamente o `valor_total`
    declarado (delta R$ 0,00). Casos relevantes:
    - `Fatura_02_2026.pdf`: anuidade R$ 11,67 (11/12) capturada → total
      R$ 933,59 bate.
    - `Fatura_03_2026.pdf`: anuidade R$ 11,63 (12/12 — última parcela)
      capturada.
    - `Fatura_04_2026.pdf`: estorno R$ −39,99 preservado.
    - `Fatura_05_2026.pdf`: anuidade R$ 13,50 (01/12 — nova série)
      junto com `DESC ANUIDADE POR USO` R$ −13,50, refletindo o
      desconto integral por uso. Cobre o cenário "se passa de um certo
      valor é abatida".

- **1.2 + 4.2 — Inferência correta do ano da transação + consolidação em `base.py`**
  - Nova função `inferir_ano_transacao(mes_tx, data_vencimento, parcela,
    *, recuar_pelo_numero_da_parcela=False)` em `parsers/base.py`, com
    duas estratégias:
    - **Regra base** (sempre aplicada): se `mes_tx > mes_venc`, ano =
      `ano_venc - 1` (compras de meses anteriores que entram numa
      fatura mais recente, ex.: dezembro caindo na fatura de janeiro).
      Senão, mesmo ano do vencimento.
    - **Recuo por parcela** (`recuar_pelo_numero_da_parcela=True`):
      quando o banco exibe a **data da compra original** (não a data
      da cobrança da parcela atual), o ano da compra é calculado
      recuando `X - 1` meses a partir do mês do vencimento, sendo `X`
      o número da parcela atual em `X/Y`. Cobre o caso `MAPFRE
      SEGUROS 14 JAN 16/18` em fatura maio/2026 → 14/01/2025.
  - **Por banco**:
    - **Ailos**: liga o recuo (mostra data da compra). Inclui ajuste no
      caso especial em que a parcela vem em linha separada do nome do
      produto — a data é recalculada quando a parcela é descoberta.
    - **Nubank**: mantém o recuo desligado (mostra a data da cobrança
      da parcela, sempre próxima do dia 6 do ciclo).
    - **Banco do Brasil**: mantém desligado por enquanto (sem PDF real
      para validar; pode mudar quando houver fatura de teste).
  - **4.2**: a função antiga `_ano_do_vencimento` foi consolidada em
    `parsers/base.py::ano_do_vencimento` (pública) e removida dos 3
    parsers, eliminando triplicação e a importação `from datetime import
    date` redundante nos parsers.
  - **Validação**: rodada com 18 PDFs reais (Ailos + 17 Nubank, indo de
    mai/2024 a mai/2026) → 325 transações, R$ 26.641,41 no total. Em
    `Nubank_2025-01-13.pdf` (fatura jan/2025), as 49 transações com
    data `06 DEZ` foram corretamente atribuídas a 2024; as 2 com data
    em janeiro ficaram em 2025. `MAPFRE SEGUROS 16/18` agora consta
    como 14/01/2025.

- **1.5 — Substituído `import pandas` por `datetime.date` nos parsers**
  - Os três parsers (Ailos, Nubank, BB) usavam `pd.Timestamp.now().year`
    apenas como fallback do ano de vencimento, importando `pandas`
    dentro da função. Trocado por `datetime.date.today().year` (stdlib),
    com `from datetime import date` no topo do módulo.
  - A função `_ano_do_vencimento` ainda está triplicada nos 3 parsers —
    consolidar em `parsers/base.py` está mapeado como item 4.2.
  - Validação: extração nos PDFs reais segue idêntica (48 + 10
    transações); fallback testado retornando o ano atual correto.

- **1.3 — Avisar quando soma diverge do total da fatura**
  - Novo helper `_conciliar_total` em `extrator.py` comparando o
    `valor_total` que o parser extraiu do PDF com a soma das
    transações; imprime aviso amarelo quando há divergência além de
    R$ 0,01, ou quando o total não foi extraído (usa soma como
    fallback e avisa).
  - Removida a auto-correção silenciosa `valor_total = sum(...)` dos 3
    parsers (Ailos, Nubank, Banco do Brasil) — esse comportamento
    mascarava bugs reais de extração. Agora o `extrator.py` é a
    autoridade sobre conciliação.
  - **Bug real descoberto e corrigido**: a regex do parser Ailos
    capturava `"4,422.81."` (com ponto final), e `parse_valor_brl`
    devolvia `None` → o total da fatura nunca era extraído. Adicionado
    `.rstrip(".,")` no início de `parse_valor_brl` para tolerar
    pontuação trailing herdada de capturas amplas. Verificado também
    que o caso `"1.234.56"` (ponto como milhar + decimal, descrito no
    HANDOFF) **não ocorre** nos PDFs Ailos reais — o formato real é o
    americano `"1,234.56"`.
  - Validação: 4 cenários sintéticos (bate, total > soma, total < soma,
    total ausente) + execução real nos 2 PDFs sem avisos espúrios.

- **5.10 — Excel único acumulativo + pastas `entrada/`/`saida/`**
  - `extrator.py` reescrito: PDFs lidos por padrão de `entrada/`,
    resultado gravado sempre em `saida/gastometro.xlsx` (criadas
    automaticamente na primeira execução).
  - Excel agora é único e acumulativo. Cada execução adiciona apenas as
    faturas cujo nome de arquivo ainda não consta na aba `Informações`;
    duplicatas são ignoradas com mensagem clara no terminal.
  - 4 abas no resultado: `Informações` (uma linha por fatura),
    `Transações` (acumulativo com coluna `Arquivo`), `Resumo por
    Categoria` (recalculado) e nova aba `Resumo Mensal` (pivot
    referência × categoria, com totais por linha e coluna).
  - Argumentos posicionais ainda funcionam (PDF avulso ou pasta) e
    continuam gravando em `saida/gastometro.xlsx`.
  - README atualizado com o novo fluxo e instruções para re-processar
    uma fatura.
  - Validação: rodar duas vezes seguidas mantém 2 faturas e 58
    transações (R$ 5.355,35 = R$ 4.422,81 Ailos + R$ 932,54 Nubank);
    duplicar um PDF com outro nome adiciona corretamente como 3ª
    fatura.

- **1.4 / 7.1 — Remover dados pessoais de `PALAVRAS_NAO_TITULAR`**
  - Removidas as entradas `"ELIABE GAI 8449"` e `"ELIABE GAI 7316"` de
    `parsers/base.py`.
  - Análise feita antes de remover: o regex
    `[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}` aplicado token a token já descarta linhas que
    contenham finais de cartão (qualquer dígito), então essas entradas
    eram funcionalmente inúteis (nunca consultadas) e apenas vazavam
    dado pessoal.
  - Adicionado docstring detalhado em `detectar_titular` explicando as
    três camadas de filtro.
  - Validação: extração nos dois PDFs reais segue identificando titular
    `Eliabe Gai`, 48 transações Ailos (R$ 4.422,81) e 10 Nubank
    (R$ 932,54) — idêntico ao baseline do HANDOFF.

---

## Notas para evoluir este arquivo

- Ao iniciar uma melhoria: marcar `[~]` e adicionar `(em andamento)`.
- Ao concluir: marcar `[x]`, mover para a seção "Concluídas" com data e referência do commit.
- Ao propor algo novo: adicionar na seção temática certa, com prioridade e esforço.
- Sempre que rodar `git commit`, citar o número do item no corpo (ex: `feat: 5.1 consolida\u00e7\u00e3o multi-fatura`).
