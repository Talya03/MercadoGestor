# v0.14 — Precificação

## Para que serve
Responder: "a que preço eu preciso vender para ficar com o lucro que quero?". Menu **Precificação** (dono e gerente).

## Margem não é "% em cima do custo"
| | O que é | Exemplo (custo R$ 7,00, venda R$ 10,00) |
|---|---|---|
| **Margem** | parte do preço que sobra de lucro | (10 − 7) / 10 = **30%** |
| **Markup** | quanto se soma ao custo | (10 − 7) / 7 = **42,86%** |

Quem "coloca 30% em cima do custo" vende a R$ 9,10 e fica com margem de só **23%**. Este módulo usa margem,
e mostra o markup ao lado para você comparar.

## Como usar
1. Informe a **margem desejada** (ex.: 30) e as **despesas sobre a venda** (taxa da maquininha, imposto; ex.: 4). Clique em Calcular.
2. A tabela mostra, por produto: custo, preço atual, margem atual, **preço sugerido** e a situação.
3. Se concordar, clique em **Aplicar** (pede confirmação). Só então o preço de venda do produto muda.

## Regras
- **RN77** Preço sugerido = custo / (1 − (margem + despesas)/100), arredondado **para cima** ao centavo.
- **RN78** Margem e despesas não podem ser negativas; a soma precisa ser menor que 100%.
- **RN79** Produto sem custo não tem sugestão (o sistema avisa em vez de inventar um preço).
- **RN80** Ao aplicar, o preço é recalculado no servidor; o preço nunca vem pronto do navegador.
- **RN81** Margem atual = (preço − custo − despesas) / preço. "Abaixo da meta" = preço de venda menor que o sugerido.
- Simular não grava nada. Quem pode: os mesmos perfis do catálogo (dono e gerente).

## Exemplos de mercado
- Arroz 5 kg, custo R$ 20,00, meta 25%, maquininha 3%: 20 / (1 − 0,28) = **R$ 27,78**.
- Refrigerante, custo R$ 4,50, meta 30%, sem despesas: 4,50 / 0,70 = **R$ 6,43**.

## Limitações
- O preço sugerido é um piso matemático, não considera a concorrência. Preço psicológico (R$ 6,99 em vez de R$ 6,43) se ajusta editando o produto.
- A margem é a mesma para todos os produtos na simulação (não há margem própria por categoria ainda).
- Não há histórico de preços: a tela mostra o preço antigo na mensagem após aplicar, mas ele não fica registrado.
- Não há "aplicar a todos de uma vez" de propósito: mudar preço em massa sem olhar é arriscado.
- Despesas fixas (aluguel, salários) não entram aqui; elas aparecem no Resumo mensal.
