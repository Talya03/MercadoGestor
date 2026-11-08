"""Fixtures compartilhadas pelos testes.

Conceito: uma fixture do pytest prepara algo que vários testes precisam.
Aqui criamos uma aplicação com banco em memória, nova a cada teste.
"""
import pytest

from app import create_app
from app.extensions import db
from config import TestConfig


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
