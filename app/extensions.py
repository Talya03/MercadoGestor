"""Extensões Flask criadas aqui, sem app, e ligadas à aplicação em create_app().

Isso evita importação circular: qualquer módulo pode fazer
`from app.extensions import db` sem depender da aplicação já existir.
"""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
