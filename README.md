# MercadoGestor

Sistema de gestão para pequenos mercados locais (minimercados, mercearias, hortifrútis).
Projeto acadêmico de Análise e Desenvolvimento de Sistemas, com foco em portfólio.

## Tecnologias
Python, Flask, SQLite, Flask-SQLAlchemy, Bootstrap, Pytest, Git.

## Como instalar e executar

```bash
# 1. Criar e ativar o ambiente virtual
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Linux/macOS

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Executar
python run.py
# No primeiro acesso o sistema pede para criar o usuário DONO (login e senha).
```

Acesse http://127.0.0.1:5000

## Como executar os testes

```bash
pytest -v
```

## Estrutura de pastas

```
MercadoGestor/
├── app/            # aplicação (models, routes, services, forms, templates, static, utils)
├── docs/           # documentação (modelagem, requisitos)
├── instance/       # banco SQLite local (não vai para o Git)
├── migrations/     # reservado para migrações futuras
├── tests/          # testes automatizados
├── config.py
├── run.py
└── requirements.txt
```

## Configurações opcionais (variáveis de ambiente)

| Variável | Para quê | Padrão |
|---|---|---|
| `SECRET_KEY` | Assina o cookie de sessão (quem a conhece forja um login) e o CSRF. Se não for definida, o sistema gera uma chave aleatória e a guarda em `instance/secret_key` (**não compartilhe nem versione essa pasta**). | gerada automaticamente |
| `SESSAO_HORAS` | Por quanto tempo uma sessão fica válida, em horas | `12` |
| `DATABASE_URL` | Troca o banco | SQLite em `instance/mercadogestor.db` |
| `DESCONTO_MAXIMO_PERCENTUAL` | Desconto máximo do caixa, em % do total | `10` |

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
