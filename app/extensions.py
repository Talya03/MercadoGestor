"""Extensões Flask criadas aqui, sem app, e ligadas à aplicação em create_app().

Isso evita importação circular: qualquer módulo pode fazer
`from app.extensions import db` sem depender da aplicação já existir.
"""
import sqlite3

from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
# CSRF: protege formulários POST contra requisições forjadas por outros sites.
csrf = CSRFProtect()


@event.listens_for(Engine, "connect")
def ativar_chaves_estrangeiras(dbapi_connection, connection_record):
    """Liga a verificação de chaves estrangeiras no SQLite.

    Conceito: por padrão o SQLite NÃO confere chaves estrangeiras. Sem esta
    linha, seria possível salvar um produto com categoria_id inexistente.
    O comando PRAGMA precisa ser executado em cada nova conexão.
    """
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
