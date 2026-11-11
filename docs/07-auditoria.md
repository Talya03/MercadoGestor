# v0.12 — Auditoria e migração do banco

## O que mudou
Vendas, movimentações de estoque (entrada, saída, ajuste), compras e lançamentos financeiros agora guardam **quem fez**
(`usuario_id`). O nome aparece no comprovante ("Operador"), na lista de vendas, no histórico de estoque, nas compras e no financeiro.
Registros anteriores à v0.12 ficam sem autor e aparecem com "—" (nunca inventamos o autor).

## Regras de negócio
- **RN67** O autor vem sempre da sessão de quem está logado, nunca de um campo do formulário. Um `usuario_id` enviado no formulário é ignorado.
- **RN68** O autor é opcional na camada de serviços (rotinas e dados antigos continuam funcionando); as telas sempre o informam.
- **RN69** Numa venda ou compra, a movimentação de estoque gerada guarda o mesmo autor da operação.
- **RN70** Se a operação falha, nada é gravado, nem o autor (a transação é atômica).
- **RN71** Registros antigos (sem autor) são exibidos com "—".

## Migração do banco existente
`db.create_all()` cria tabelas que faltam, mas **nunca altera** tabela existente. Por isso `run.py` chama `app/migracoes.py`
logo depois do `create_all()`:
1. verifica quais colunas novas faltam (`venda`, `movimentacao_estoque`, `compra`, `lancamento` → `usuario_id`);
2. se faltar algo e o banco for um arquivo, faz **cópia de segurança** `instance/mercadogestor.db.antes-da-migracao-AAAAMMDD-HHMMSS`;
3. acrescenta as colunas (`ALTER TABLE ... ADD COLUMN`), sem tocar nos dados;
4. rodar de novo não faz nada (idempotente) e não cria outra cópia.

Limitação: só trata "acrescentar coluna". Renomear/remover/mudar tipo exigiria uma ferramenta de migração (Alembic).

## Como atualizar um sistema que você já usa
1. Feche o servidor e **copie a pasta `instance/`** para um lugar seguro.
2. Aplique os arquivos da v0.12 e rode `python run.py`. As linhas `[migração] ...` mostram o que foi feito.
3. Se algo der errado, restaure o arquivo `.antes-da-migracao-...`.

## Limitações conhecidas
- Não há relatório "por operador" ainda.
- Se um usuário for desativado, o nome continua aparecendo nos registros dele (usuários nunca são apagados).
