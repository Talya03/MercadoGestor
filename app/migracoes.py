"""Migração do banco: acrescenta colunas novas a tabelas que JÁ existem, sem perder dados.

Por que isso existe: `db.create_all()` cria tabelas que faltam, mas NUNCA altera uma tabela
existente. Sem este passo, quem já tem um banco da versão anterior receberia erro
("no such column: venda.usuario_id") assim que abrisse uma tela.

Como funciona (simples de propósito):
- cada migração é "ADD COLUMN se ainda não existir" -> pode rodar quantas vezes quiser (idempotente);
- antes de alterar um banco SQLite em arquivo, faz uma CÓPIA de segurança em instance/;
- registros antigos ficam com a coluna vazia (NULL), nunca inventamos dados.

Limitação: é só para ADD COLUMN. Mudanças maiores (renomear, remover, mudar tipo) exigiriam
uma ferramenta de migração de verdade (Alembic), que o projeto evita por enquanto.
"""
import os
import shutil
from datetime import datetime

from sqlalchemy import text

from app.extensions import db

# (tabela, coluna, definição SQL). Em SQLite, ADD COLUMN com REFERENCES exige DEFAULT NULL.
COLUNAS_NOVAS = [
    ("venda", "usuario_id", "INTEGER REFERENCES usuario (id)"),
    ("movimentacao_estoque", "usuario_id", "INTEGER REFERENCES usuario (id)"),
    ("compra", "usuario_id", "INTEGER REFERENCES usuario (id)"),
    ("lancamento", "usuario_id", "INTEGER REFERENCES usuario (id)"),
]


def _colunas_existentes(conexao, tabela):
    return {linha[1] for linha in conexao.execute(text(f'PRAGMA table_info("{tabela}")'))}


def pendentes():
    """Lista de (tabela, coluna, ddl) que ainda faltam no banco atual."""
    faltando = []
    with db.engine.connect() as conexao:
        for tabela, coluna, ddl in COLUNAS_NOVAS:
            colunas = _colunas_existentes(conexao, tabela)
            if colunas and coluna not in colunas:  # tabela inexistente = create_all cuida dela
                faltando.append((tabela, coluna, ddl))
    return faltando


def _caminho_do_banco():
    """Caminho do arquivo SQLite em uso, ou None (banco em memória / outro banco)."""
    url = db.engine.url
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    return url.database


def _copia_de_seguranca(caminho):
    destino = f"{caminho}.antes-da-migracao-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(caminho, destino)
    return destino


def aplicar():
    """Aplica o que falta. Devolve a lista de colunas acrescentadas (vazia = banco já atualizado).

    Chame DEPOIS de db.create_all(). Cada ALTER é atômico no SQLite; se algo falhar no meio,
    rodar de novo completa o que faltou (e a cópia de segurança está em instance/).
    """
    faltando = pendentes()
    if not faltando:
        return []
    caminho = _caminho_do_banco()
    if caminho and os.path.exists(caminho):
        copia = _copia_de_seguranca(caminho)
        print(f"[migração] cópia de segurança do banco: {copia}")
    with db.engine.begin() as conexao:
        for tabela, coluna, ddl in faltando:
            conexao.execute(text(f'ALTER TABLE "{tabela}" ADD COLUMN "{coluna}" {ddl}'))
            print(f"[migração] {tabela}.{coluna} acrescentada")
    return [(t, c) for t, c, _ in faltando]
