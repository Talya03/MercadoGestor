"""Configurações da aplicação.

Conceito: separar configuração do código permite trocar o comportamento
(desenvolvimento, testes, produção) sem alterar a lógica do sistema.
Valores sensíveis (como SECRET_KEY) vêm de variáveis de ambiente.
"""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # Em desenvolvimento usamos um valor padrão. Em uso real, defina a
    # variável de ambiente SECRET_KEY com um valor longo e aleatório.
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-chave-apenas-para-desenvolvimento")

    # SQLite: um único arquivo dentro da pasta instance/.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(BASE_DIR, "instance", "mercadogestor.db"),
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class TestConfig(Config):
    """Configuração dos testes: banco em memória, isolado do banco real."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    # Nos testes de rotas não precisamos enviar o token CSRF manualmente.
    # Um teste específico liga a proteção para provar que ela funciona.
    WTF_CSRF_ENABLED = False
