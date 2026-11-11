# MercadoGestor

Sistema de gestão **local** para pequenos mercados (minimercados, mercearias, hortifrútis): vendas no PDV,
estoque, compras, financeiro, precificação, relatórios, usuários com perfis e backup.
Projeto acadêmico de Análise e Desenvolvimento de Sistemas, com foco em portfólio.

> **Estado do projeto:** completo para uso **local, num único computador, por um mercado pequeno**, depois da
> revisão de segurança (`docs/10-revisao-seguranca.md`). **Não** é um sistema fiscal (não emite nota) e **não** foi
> feito para ficar na internet nem para vários computadores ao mesmo tempo. Leia as limitações antes de usar com dinheiro de verdade.

## Tecnologias
Python, Flask, SQLite, Flask-SQLAlchemy, Flask-WTF, Bootstrap 5 (incluído no projeto, funciona sem internet), Pytest, Git.

## Módulos
Painel inicial · Categorias e produtos · Estoque (entrada, saída, ajuste, histórico) · PDV (caixa, desconto, Pix/dinheiro/cartões,
comprovante) · Fornecedores e compras · Financeiro (contas a pagar, resumo mensal) · Precificação · Relatórios com CSV ·
Usuários e perfis (dono, gerente, caixa) · Auditoria (quem fez) · Backup e restauração.

## Como instalar e executar

```bash
# 1. Criar e ativar o ambiente virtual
python -m venv venv
venv\Scripts\activate          # Windows (cmd/PowerShell)
source venv/Scripts/activate   # Windows (Git Bash)
source venv/bin/activate       # Linux/macOS

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Executar
python run.py
```

Acesse http://127.0.0.1:5000. No primeiro acesso o sistema pede para criar o usuário **dono** (login e senha de, no mínimo, 8 caracteres).
O banco é criado/atualizado sozinho em `instance/mercadogestor.db`.

Para desenvolver com recarga automática ao salvar arquivos: `MERCADOGESTOR_DEBUG=1 python run.py` (Git Bash).
**Nunca** ligue isso num computador usado por outras pessoas: o modo debug permite executar código pelo navegador.

## Como atualizar de uma versão anterior
1. Feche o sistema e **copie a pasta `instance/`** para um lugar seguro.
2. Extraia os arquivos novos por cima do projeto (na ordem das versões).
3. `pip install -r requirements.txt` e `python run.py`. Colunas novas do banco são acrescentadas sozinhas (com cópia de segurança em `instance/`).

## Backup (faça!)
Menu **Backup → Fazer backup agora** e baixe o arquivo para uma pen drive. Restaurar: feche o sistema e rode
`python restaurar.py caminho/do/backup.db`. Detalhes em `docs/08-backup-restauracao.md`.

## Como executar os testes
```bash
pytest -v
```
Os testes usam banco em memória e não tocam nos seus dados.

## Documentação
| Arquivo | Assunto |
|---|---|
| `docs/01-modelagem.md` | Modelagem do banco, regras RN01–RN18 |
| `docs/02-vendas-pdv.md` | PDV e vendas (RN19–RN30) |
| `docs/03-compras.md` | Fornecedores e compras (RN31–RN39) |
| `docs/04-financeiro.md` | Financeiro e resumo mensal (RN40–RN47) |
| `docs/05-relatorios-dashboard.md` | Painel e relatórios (RN48–RN55) |
| `docs/06-usuarios-seguranca.md` | Login, perfis e permissões (RN56–RN66) |
| `docs/07-auditoria.md` | Quem fez cada operação e migração do banco (RN67–RN71) |
| `docs/08-backup-restauracao.md` | Backup e restauração (RN72–RN76) |
| `docs/09-precificacao.md` | Precificação por margem (RN77–RN81) |
| `docs/10-revisao-seguranca.md` | Revisão final de segurança, riscos que restam |
| `docs/11-guia-de-uso.md` | Guia do dia a dia para dono, gerente e caixa |

## Estrutura de pastas
```
MercadoGestor/
├── app/            # models, routes, services, forms, templates, static (inclui Bootstrap), utils
├── docs/           # documentação
├── instance/       # DADOS PRIVADOS (banco, backups, chave secreta): fica fora do Git
├── tests/          # testes automatizados
├── config.py
├── run.py          # inicia o sistema
└── restaurar.py    # restaura um backup
```

## Configurações opcionais (variáveis de ambiente)
| Variável | Para que serve | Padrão |
|---|---|---|
| `SECRET_KEY` | Chave que assina o login. Se não definir, o sistema cria uma aleatória em `instance/secret_key` | automática |
| `DATABASE_URL` | Troca o banco | SQLite em `instance/mercadogestor.db` |
| `DESCONTO_MAXIMO_PERCENTUAL` | Desconto máximo do caixa, em % do total | `10` |
| `SESSAO_HORAS` | Duração do login | `12` |
| `BACKUP_DIR` / `BACKUP_MANTER` | Pasta e quantidade de backups guardados | `instance/backups` / `14` |
| `MERCADOGESTOR_DEBUG` | `1` liga o modo de desenvolvimento (inseguro) | desligado |

## Histórico de versões
- **v0.1**: modelagem de Categoria, Produto e Movimentação de Estoque.
- **v0.2**: estrutura inicial Flask + SQLite + página inicial + testes básicos.
- **v0.3**: modelos Categoria, Produto e MovimentacaoEstoque com restrições (UNIQUE, CHECK, chaves estrangeiras) e testes.
- **v0.4**: CRUD de categorias (listar, cadastrar, editar, desativar/reativar, busca), menu lateral, mensagens, proteção CSRF.
- **v0.5**: CRUD de produtos (busca por nome/código, filtros por categoria e estoque baixo), entrada de valores em formato brasileiro, regras RN09–RN13.
- **v0.6**: controle de estoque: entrada, saída e ajuste por contagem, histórico com filtros (produto, tipo, período), alerta de estoque baixo, gravação atômica com controle de concorrência, auditoria de saldos. Regras RN14–RN18.
- **v0.7**: PDV: busca e adição por código, carrinho, desconto controlado, pagamento (dinheiro com troco, Pix, débito, crédito), comprovante imprimível e lista de vendas. Venda atômica com baixa de estoque e proteção contra venda duplicada. Regras RN19–RN30 (`docs/02-vendas-pdv.md`).
- **v0.8**: Fornecedores (cadastro, busca, desativar/reativar) e Compras de mercadoria: vários itens por compra, entrada automática no estoque na mesma transação, custo do produto atualizado pela última compra, proteção contra compra duplicada. Regras RN31–RN39 (`docs/03-compras.md`).
- **v0.9**: Financeiro: despesas e receitas avulsas, contas a pagar (pagar, desfazer pagamento, cancelar), compra à vista/a prazo gerando a conta na mesma transação, e resumo mensal (vendas, custo das mercadorias vendidas, lucro bruto, despesas, resultado). Regras RN40–RN47 (`docs/04-financeiro.md`).
- **v0.10**: Página inicial com painel (vendas de hoje, estoque baixo, contas a vencer, mês atual) e Relatórios (produtos mais vendidos, formas de pagamento, vendas por dia) com exportação CSV segura para Excel. Regras RN48–RN55 (`docs/05-relatorios-dashboard.md`).
- **v0.11**: Segurança de acesso: login, perfis (dono, gerente, caixa), proteção de **todas** as rotas (negar por padrão), tela de primeiro acesso, bloqueio após erros de senha, troca obrigatória de senha temporária, gestão de usuários e chave secreta automática. Regras RN56–RN66 (`docs/06-usuarios-seguranca.md`).
- **v0.12**: Auditoria: vendas, ajustes de estoque, compras e lançamentos guardam e mostram quem os fez (o autor vem da sessão, nunca do formulário) e migração automática e segura do banco existente, com cópia de segurança. Regras RN67–RN71 (`docs/07-auditoria.md`).
- **v0.13**: Backup e restauração do banco: backup com um clique (só o dono), verificado e com retenção dos 14 mais recentes, download seguro e `restaurar.py` que guarda o banco atual antes de restaurar. Regras RN72–RN76 (`docs/08-backup-restauracao.md`).
- **v0.14**: Precificação: preço sugerido a partir do custo, da margem desejada e das despesas sobre a venda (margem ≠ markup), margem atual por produto, filtro "abaixo da meta" e botão Aplicar com confirmação (preço recalculado no servidor). Regras RN77–RN81 (`docs/09-precificacao.md`).
- **v0.15**: Fechamento da Fase 9: revisão de segurança do sistema inteiro (CSRF em toda rota POST, política de segurança de conteúdo/CSP, Bootstrap local sem internet, depurador desligado por padrão, páginas de erro seguras, `instance/` fora do Git), testes de recuperação de desastre e documentação final (`docs/10-revisao-seguranca.md`, `docs/11-guia-de-uso.md`).
