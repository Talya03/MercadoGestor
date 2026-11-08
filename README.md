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

## Histórico de versões
- **v0.1**: modelagem de Categoria, Produto e Movimentação de Estoque.
- **v0.2**: estrutura inicial Flask + SQLite + página inicial + testes básicos.
