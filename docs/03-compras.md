# Fornecedores e Compras (v0.8)

## Para que serve
Registrar **de quem** o mercado compra e **o que chegou**. Cada compra dá entrada no estoque
e atualiza o custo dos produtos (base do cálculo de lucro das próximas fases).

## Modelo de dados
```
Fornecedor 1—N Compra 1—N ItemCompra N—1 Produto
```

| Tabela | Campos principais | Proteções do banco |
|---|---|---|
| `fornecedor` | nome, documento (CPF/CNPJ só dígitos), telefone, contato, ativo | `nome` UNIQUE; `documento` UNIQUE (vários vazios permitidos) |
| `compra` | fornecedor_id, data_hora (UTC), numero_documento, observacao, total, token_envio | `total > 0`; `token_envio` UNIQUE; FK do fornecedor |
| `item_compra` | compra_id, produto_id, quantidade, custo_unitario, subtotal | quantidade, custo e subtotal `> 0`; UNIQUE (compra, produto) |

O item guarda o **custo pago naquela compra**: o histórico não muda quando o custo do produto for atualizado.

## Regras de negócio
- **RN31** Nome do fornecedor único (sem diferenciar maiúsculas/minúsculas). CPF/CNPJ opcional, só dígitos (11 ou 14), único quando informado. Os dígitos verificadores **não** são conferidos.
- **RN32** Fornecedor não é excluído, só desativado. Fornecedor inativo não recebe compras; as antigas continuam visíveis.
- **RN33** Compra exige fornecedor ativo e ao menos um item (máx. 200). Cada produto aparece uma vez e precisa estar ativo.
- **RN34** Quantidade > 0 (inteira para UN/CX/PCT; até 3 casas para KG/G/L/ML, como na RN14) e custo unitário > 0 (até 2 casas). Valores com mais casas são recusados, não arredondados.
- **RN35** Subtotal = custo × quantidade, arredondado ao centavo (meio para cima). Total = soma dos subtotais. Subtotal zerado ou acima de R$ 99.999.999,99 é recusado.
- **RN36** Registrar é **atômico**: compra + itens + entradas de estoque (motivo "Compra #N") + atualização de custo valem juntos ou não valem nada.
- **RN37** O custo do produto passa a ser o da **última compra**. O preço de venda **não** muda sozinho; o detalhe da compra avisa quando o preço de venda atual está abaixo do custo.
- **RN38** O mesmo envio de formulário não gera duas compras (token UUID único). Reenviar leva à compra original.
- **RN39** Compra concluída não é editada nem excluída.

## Fluxo atômico
1. Valida fornecedor, itens, quantidades, custos e duplicidades (nada é gravado ainda).
2. Grava a compra (`flush`, para obter o número) e, para cada item, o `ItemCompra` e a entrada de estoque com `confirmar=False`.
3. Atualiza o custo de cada produto.
4. Um único `commit`. Qualquer erro em qualquer passo faz `rollback` de tudo, inclusive das entradas já feitas.

## Exemplo de mercado
Chegam 24 UN de leite a R$ 4,80 e 10 kg de tomate a R$ 6,20 da "Distribuidora Bom Preço":
subtotais R$ 115,20 + R$ 62,00 = **R$ 177,20**; o estoque sobe, o custo do leite vira R$ 4,80 e a
conferência de saldos continua sem divergência.

## Limitações conhecidas
- Não há estorno/cancelamento nem edição de compra concluída (erro de digitação: corrija com um ajuste de estoque, que fica no histórico).
- Custo = última compra (não é custo médio ponderado).
- Não há contas a pagar, parcelas nem vencimento: isso entra no módulo Financeiro (próxima etapa).
- A data da compra é o momento do registro (não dá para lançar compra com data passada).
- O seletor de produtos da tela lista todos os produtos ativos; para catálogos muito grandes, será necessária uma busca.
- A tela de compra usa JavaScript (linhas dinâmicas e prévia do total); esse JavaScript não tem teste automatizado.
