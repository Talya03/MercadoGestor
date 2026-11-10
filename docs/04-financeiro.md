# Financeiro (v0.9)

## Para que serve
Saber **quanto o mercado ganhou e gastou no mês** e **o que ainda precisa pagar**.

## Modelo de dados
`lancamento`: tipo (DESPESA/RECEITA), categoria, descricao, valor, vencimento (data), pago_em (data ou vazio),
cancelado, compra_id (opcional, único), criado_em.

Proteções do banco: `valor > 0`; tipo e categoria só dos valores permitidos; receita sempre com `pago_em`;
lançamento cancelado nunca tem `pago_em`; no máximo um lançamento por compra.

Datas financeiras são **datas do calendário do mercado** (não instantes UTC): "vence dia 10".

## Regras de negócio
- **RN40** Lançamento: tipo, categoria, descrição (≤120), valor > 0 com 2 casas e data. Receita avulsa nasce recebida na própria data. Despesa nasce pendente ou já paga.
- **RN41** A categoria "Compra de mercadoria" só é criada por uma Compra. Não dá para digitá-la à mão.
- **RN42** Pagar = informar a data do pagamento (padrão hoje, nunca no futuro). Só despesa pendente e não cancelada.
- **RN43** Desfazer pagamento devolve a despesa a pendente (para corrigir engano). Receita não.
- **RN44** Cancelar só vale para despesa **pendente que não veio de compra**. Nada é excluído; cancelados saem das listas e do resumo.
- **RN45** Conta vencida = pendente com vencimento antes de hoje (hoje no horário do mercado).
- **RN46** Resumo mensal: `resultado = (vendas − custo das mercadorias vendidas) + outras receitas − despesas operacionais`. As compras de mercadoria **não** entram nas despesas (o dinheiro delas já aparece no custo vendido; somar os dois contaria em dobro). Aparecem só como linha informativa.
- **RN47** Toda compra gera, **na mesma transação**, uma conta a pagar: à vista = já paga hoje; a prazo = pendente, com vencimento hoje ou depois. Se algo falhar, compra, estoque, custo e conta voltam atrás juntos.

## Como o resumo é calculado
| Linha | Origem |
|---|---|
| Vendas | soma de `venda.total` das vendas do mês (dia do mercado) |
| Custo das mercadorias vendidas | Σ (custo copiado no item × quantidade), arredondado por item ao centavo |
| Lucro bruto / margem | vendas − custo vendido; margem = lucro bruto ÷ vendas |
| Outras receitas | receitas avulsas com data no mês |
| Despesas operacionais | despesas (exceto mercadoria) com **vencimento** no mês; mostra quanto está pago e pendente |
| Resultado | conforme RN46 |

## Exemplo de mercado
Em novembro: vendas R$ 150,00 (custo R$ 114,00) → lucro bruto R$ 36,00 (24%). Aluguel R$ 30,00 pendente + luz R$ 10,00 paga
= despesas R$ 40,00. Comissão avulsa R$ 5,00. Resultado = 36 + 5 − 40 = **R$ 1,00**.

## Limitações conhecidas
- Visão **gerencial simples**: não é apuração contábil, fiscal nem fluxo de caixa. Despesas entram pelo mês do vencimento, vendas pelo dia da venda.
- O custo vendido usa o custo da **última compra** (RN37) vigente na venda, não o custo médio.
- Não há edição de lançamento: para corrigir valor ou data, cancele (se pendente) e lance de novo. Contas de compra não podem ser canceladas.
- Pagamentos parciais, parcelas, juros/multa e recorrência (aluguel mensal automático) não existem ainda.
- Vendas a prazo/fiado e contas a receber não existem; toda venda do PDV é considerada recebida no ato.
- Estorno de venda ou de compra não existe, então não há reflexo no resumo.
- As telas usam JavaScript simples (campos que aparecem/somem); ele foi exercitado manualmente num navegador, sem teste automatizado.
