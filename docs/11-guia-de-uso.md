# Guia de uso do dia a dia

## Primeira vez
1. Abra o sistema (`python run.py`) e acesse http://127.0.0.1:5000.
2. Crie o usuário **dono**. Guarde a senha em lugar seguro.
3. Em **Usuários**, crie uma conta para cada pessoa (gerente, caixa). Deixe a senha em branco para o sistema gerar uma
   temporária (a pessoa troca no primeiro acesso).
4. Cadastre **Categorias**, depois **Produtos** (nome, código/código de barras, unidade, custo, preço de venda, estoque mínimo).
5. Dê entrada no estoque: **Estoque -> Entrada** (ou registre uma **Compra**, que já dá a entrada sozinha).

## Quem pode o quê
| | Dono | Gerente | Caixa |
|---|:-:|:-:|:-:|
| PDV e vendas | ✓ | ✓ | ✓ |
| Produtos, categorias, estoque, precificação | ✓ | ✓ | |
| Fornecedores e compras | ✓ | ✓ | |
| Relatórios | ✓ | ✓ | |
| Financeiro e resumo mensal | ✓ | | |
| Usuários e backup | ✓ | | |

## Rotina do caixa
1. **PDV (caixa)**: digite ou leia o código de barras, ajuste a quantidade (peso em KG aceita decimais, ex.: 1,250).
2. Desconto (se permitido: até 10% do total por padrão).
3. Escolha a forma de pagamento. Em dinheiro, informe o valor recebido para ver o **troco**.
4. **Finalizar venda**. O estoque baixa sozinho. Imprima o comprovante se quiser (não é nota fiscal).
5. Errou depois de finalizar? Peça ao dono/gerente: venda finalizada não é apagada; o ajuste de estoque fica registrado com o nome de quem fez.

## Rotina do gerente
- Quando chegar mercadoria: **Compras -> Nova compra** (fornecedor, itens, quantidade e custo). Escolha **à vista** ou **a prazo** (a conta a pagar nasce junto).
- Contagem de estoque: **Estoque -> Ajuste** informando o saldo contado e o motivo.
- **Precificação**: informe a margem desejada e as despesas (ex.: taxa da maquininha) e veja quais produtos estão abaixo da meta.
- **Painel inicial**: vendas de hoje, estoque baixo, contas a vencer.

## Rotina do dono
- **Financeiro**: lance despesas (aluguel, luz, salários), marque como pagas, acompanhe o que vence. **Resumo mensal**: vendas, custo das mercadorias vendidas, lucro bruto, despesas e resultado.
- **Relatórios**: produtos mais vendidos, formas de pagamento, vendas por dia (com exportação CSV para Excel).
- **Backup**: todo dia ao fechar, **Backup -> Fazer backup agora -> Baixar** e guardar na pen drive.

## Problemas comuns
| Situação | O que fazer |
|---|---|
| "A página expirou" | Volte, recarregue a página e repita. Acontece quando a tela ficou aberta por muito tempo. |
| "Conta bloqueada" por erros de senha | Espere 5 minutos, ou peça ao dono para redefinir a senha. |
| Esqueci a senha do dono | Se houver outro dono ativo, ele redefine. Se não, restaurar um backup não resolve (a senha também está no banco): é preciso ajuda técnica. **Por isso mantenha um segundo usuário dono.** |
| Estoque "não bate" | Veja **Estoque -> Histórico** (cada movimentação mostra quem fez e por quê) e faça um **Ajuste** com motivo. |
| Banco corrompido / computador novo | Feche o sistema e rode `python restaurar.py <arquivo de backup>` (veja `docs/08-backup-restauracao.md`). |
| Quero mudar o preço em vários produtos | **Precificação**, produto a produto (de propósito não há "aplicar em todos"). |

## Limites do sistema (para não ter surpresa)
- Não emite nota fiscal e não integra com maquininha, balança ou leitor via sistema (o leitor de código de barras funciona como teclado).
- Um computador por vez. Não abra o sistema para a rede do mercado.
- Os dados só existem naquele computador: sem backup fora dele, perder o computador é perder tudo.
