# Relatórios e página inicial (v0.10)

## Para que serve
Responder, sem planilha: **quanto vendi, do quê, como me pagaram e o que exige atenção hoje**.
Tudo é **somente leitura**: nenhum relatório ou painel altera dados (POST nessas rotas devolve 405).

## Página inicial (painel)
| Bloco | Origem |
|---|---|
| Vendas de hoje (quantidade, total, ticket médio) e total de ontem | vendas do dia do mercado |
| Estoque baixo (contagem + 5 mais críticos) | produtos ativos com saldo ≤ mínimo (RN07) |
| Contas vencidas e total a pagar | financeiro (despesas pendentes) |
| Contas a vencer | pendentes vencidas ou que vencem em até 7 dias (as 5 mais antigas) |
| Mês atual: vendas, lucro bruto, resultado | o mesmo cálculo do Resumo mensal (RN46) |

- **RN52** "Hoje" e "ontem" são dias do mercado (America/Sao_Paulo), não de UTC.
- **RN53** Estoque baixo segue a RN07 e só considera produtos ativos; o painel mostra os 5 mais críticos (menor saldo menos o mínimo).
- **RN54** Contas a vencer = despesas pendentes vencidas ou com vencimento nos próximos 7 dias; o painel mostra as 5 mais antigas.

## Relatórios (`/relatorios/`)
Todos têm período (padrão: do dia 1º do mês até hoje), filtro por data e botão **Baixar CSV**.

- **RN48** Período com data inicial ≤ final e **no máximo 366 dias**. Período inválido volta ao mês atual com um aviso (na tela; no CSV, sem aviso, para não "vazar" para outra página).
- **RN49** *Produtos mais vendidos*: por produto, quantidade, receita (soma dos subtotais dos itens), custo (custo **copiado na venda** × quantidade, por item arredondado ao centavo) e lucro/margem. Ordem por quantidade, receita ou lucro, com desempate por nome. Produtos inativos continuam no histórico.
- **RN50** *Formas de pagamento*: soma do valor de cada forma nas vendas do período. É o valor que abateu da venda, **sem o troco**.
- **RN51** *Vendas por dia*: dia do mercado, nº de vendas, desconto, total e ticket médio. Dias sem venda não aparecem.
- **RN55** *CSV*: separador `;`, números com vírgula decimal, BOM UTF-8 (o Excel/LibreOffice em português abre direto com acentos). Em colunas de texto, valores que começam com `=`, `+`, `-`, `@`, tab ou enter recebem um apóstrofo na frente (**proteção contra "CSV injection"**: um produto chamado `=HYPERLINK(...)` não vira fórmula na planilha).

## Exemplo de mercado
No mês, o leite vendeu 15 UN: receita R$ 104,85, custo R$ 67,50, lucro R$ 37,35, margem 35,6%.
Se no caixa foi dado R$ 8,99 de desconto, ele aparece em "Vendas por dia", não no relatório por produto.

## Limitações conhecidas
- **Receita e lucro por produto são antes do desconto dado no caixa.** O desconto é do total da venda e não é rateado entre os itens; por isso a soma do relatório por produto pode ser maior que o total de "Vendas por dia" (a diferença é o desconto).
- O lucro é **bruto** (sem despesas) e usa o custo da última compra vigente no dia da venda, não o custo médio.
- Sem gráficos, sem relatório de estoque valorizado, de vendas por operador ou por categoria, e sem exportação em PDF/XLSX.
- Os relatórios carregam as linhas do período em memória: adequado a um mercado pequeno e ao limite de 366 dias.
- Não há estorno de venda: se existir um dia, os relatórios precisarão ser ajustados.
- Os totais de pagamentos contam *pagamentos* (uma venda hoje tem um só), não vendas.
