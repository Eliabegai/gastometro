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

- [ ] **1.1 — `parse_valor_brl` falha com múltiplos pontos** — P1 / S
  - `parsers/base.py::parse_valor_brl` não trata `"1.234.56"` (formato visto em faturas Ailos). Cai no `float()` direto e levanta `ValueError`.
  - Tratar caso "vários pontos" como milhares (último ponto = decimal).
  - Adicionar testes para: `"1.234,56"`, `"1.234.56"`, `"1234,56"`, `"-R$ 50,00"`, `"R$ 0,00"`, `"\u22125,00"`.

- [ ] **1.2 — Inferência de ano errada em parcelas antigas** — P1 / S
  - `parsers/ailos.py::_ano_do_vencimento` (idem nubank/banco_brasil) aplica o ano do vencimento a todas as transações.
  - Caso de teste: `MAPFRE SEGUROS 14 JAN` em fatura de maio.
  - Regra sugerida: se mês da transação > mês do vencimento, ano = ano_vencimento - 1.

- [ ] **1.3 — Avisar quando soma diverge do total da fatura** — P1 / XS
  - Hoje, se houver lançamento não capturado, ninguém percebe. Quando `meta.valor_total > 0` e `abs(meta.valor_total - sum(t.valor)) > 0.01`, imprimir aviso.

- [ ] **1.4 — Remover dados pessoais de `PALAVRAS_NAO_TITULAR`** — P0 / XS
  - `parsers/base.py` tem `"ELIABE GAI 8449"` e `"ELIABE GAI 7316"` chumbados na blocklist (nome + finais de cartão). Problemático para repo público e para outros usuários.
  - Remover essas entradas e, se necessário, mascarar finais de cartão via regex genérica.

- [ ] **1.5 — `import pandas` dentro de função (3 lugares)** — P3 / XS
  - `parsers/ailos.py:126`, `parsers/nubank.py:117`, `parsers/banco_brasil.py:100`.
  - Trocar por `datetime.date.today().year` (stdlib).

- [ ] **1.6 — PDF lido duas vezes (detecção + extração)** — P2 / S
  - `parsers/__init__.py::detectar_banco` + `extrair_fatura` chamam `_ler_texto` independentemente.
  - Refatorar para abrir o PDF uma vez e reaproveitar o texto.

## 2. Categorização (`categorias.py`)

- [ ] **2.1 — Duplicatas e conflitos no dicionário** — P2 / XS
  - `apple.com/bill` e `google play` estão em "Assinatura Digital" **e** "Compra Digital" (a segunda nunca pega).
  - `"mercado pago"` aparece duas vezes na mesma categoria.
  - Consolidar e decidir critério.

- [ ] **2.2 — Casamento por substring gera falsos positivos** — P1 / M
  - `"big"` casa `"BIGODE LANCHES"`, `"raia"` casa `"RAIANE OFICINA"`, etc.
  - Suporte a regex com `\b...\b`.
  - Normalização de acentos (remover diacríticos antes de comparar).
  - Considerar pesos ("quem casa mais palavras vence" em vez de "primeira que casa").
  - Permitir regras negativas ("posto" → Combustível, exceto se também contiver "vet" ou "saúde").

- [ ] **2.3 — Aprendizado a partir do usuário** — P2 / M
  - Criar `categorias_usuario.json` (não versionado), mapeando descrição normalizada → categoria.
  - `categorizar()` consulta esse arquivo antes do dicionário fixo.
  - Bônus: ler de volta um Excel já corrigido manualmente e auto-alimentar o arquivo.

- [ ] **2.4 — Visibilidade do "Outros Gastos"** — P2 / S
  - No fim de cada execução, imprimir top-10 descrições não categorizadas (com valor agregado), pra evoluir o dicionário.

## 3. Testes automatizados

- [ ] **3.1 — Setup do pytest** — P1 / XS
  - Pasta `tests/`, `pytest` em dev-requirements (ou extras `[dev]` no `pyproject.toml`).

- [ ] **3.2 — Testes de `parse_valor_brl`** — P1 / S

- [ ] **3.3 — Testes de `categorizar`** — P1 / S
  - Pelo menos 2 positivos e 1 negativo por categoria.

- [ ] **3.4 — Testes de `referencia_pelo_vencimento` e ano por parcela** — P1 / XS

- [ ] **3.5 — Smoke tests dos parsers com fixtures de texto** — P2 / M
  - Salvar o texto bruto extraído de cada PDF de teste em `tests/fixtures/*.txt` e validar contagem/total.

- [ ] **3.6 — Anonimizar 1 PDF de exemplo em `exemplos/`** — P3 / M
  - Trocar nome do titular por "FULANO TESTE" e mascarar finais de cartão.

## 4. Arquitetura

- [ ] **4.1 — Desacoplar parser de categorização** — P2 / S
  - Parsers devolvem `Transacao` com `categoria=""`; o `extrator.py` aplica `categorizar()` num passo separado.
  - Remove import `from categorias import categorizar` dos 3 parsers.
  - Permite reprocessar Excel sem reabrir PDF.

- [ ] **4.2 — Mover `_ano_do_vencimento` para `parsers/base.py`** — P3 / XS
  - Triplicada hoje.

- [ ] **4.3 — Definir Protocol/ABC para parser** — P3 / S
  - Contrato `detectar() -> bool`, `extrair(pdf) -> Fatura`, `NOME_BANCO: str`.

- [ ] **4.4 — Refatorar `_montar_transacoes` do Ailos** — P2 / M
  - 85 linhas com várias mutações de estado (`desc_pendente`, `cidade_pendente`).
  - Quebrar em funções menores ou pequena máquina de estados.

## 5. Features

- [ ] **5.1 — Consolidação multi-fatura** — P1 / M
  - Excel mestre com aba `Consolidado` (todas as transações de N PDFs) + `Comparativo` (categoria × mês).

- [ ] **5.2 — Gráficos no Excel** — P2 / S
  - `openpyxl.chart.PieChart` (categorias) e `BarChart` (mensal).

- [ ] **5.3 — Interface Streamlit** — P2 / M
  - Drag-and-drop de PDF, baixar Excel.

- [ ] **5.4 — Suporte a outros bancos populares** — P2 / L
  - Itaú, Bradesco, Inter, C6. Um arquivo por banco em `parsers/`.

- [ ] **5.5 — Detecção de duplicatas entre faturas** — P2 / S
  - Útil ao consolidar; pega cobrança em duplicidade.

- [ ] **5.6 — Comparativo mensal automático** — P2 / S
  - "Mercado R$ X (+12% vs mês passado)".

- [ ] **5.7 — Exportar JSON/CSV além de Excel** — P3 / XS

- [ ] **5.8 — Modo "diff" (apenas lançamentos novos)** — P3 / M

- [ ] **5.9 — Alertas configuráveis (`config.yaml`)** — P3 / M

## 6. Tooling / DX

- [ ] **6.1 — `pyproject.toml` + `ruff` + `mypy`** — P2 / S

- [ ] **6.2 — GitHub Actions: `pytest` + `ruff` em cada push** — P2 / S

- [ ] **6.3 — `pre-commit` bloqueando PDFs/XLSX por engano** — P3 / S

- [ ] **6.4 — Substituir `print` por `logging`** — P3 / S
  - Permite `--quiet`, `--debug` e log em arquivo.

- [ ] **6.5 — Pacote instalável (`pip install -e .`) com entrypoint `gastometro`** — P2 / S

- [ ] **6.6 — `argparse` no lugar de `sys.argv[1]`** — P2 / XS
  - Flags: `--output`, `--quiet`, `--banco=ailos`, `--no-categorize`.

## 7. Segurança e privacidade

- [ ] **7.1 — Limpar dados pessoais do código** — P0 / XS
  - Idêntico ao item 1.4 (rastrear como duplicado: concluir os dois juntos).

- [ ] **7.2 — Verificar histórico do git por PDFs commitados** — P1 / XS
  - `git log --all -- '*.pdf' '*.xlsx'` para confirmar que nunca vazaram.

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

_Ainda nada concluído nesta rodada de melhorias._

---

## Notas para evoluir este arquivo

- Ao iniciar uma melhoria: marcar `[~]` e adicionar `(em andamento)`.
- Ao concluir: marcar `[x]`, mover para a seção "Concluídas" com data e referência do commit.
- Ao propor algo novo: adicionar na seção temática certa, com prioridade e esforço.
- Sempre que rodar `git commit`, citar o número do item no corpo (ex: `feat: 5.1 consolida\u00e7\u00e3o multi-fatura`).
