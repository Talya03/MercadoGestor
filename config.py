"""Configurações da aplicação.

Conceito: separar configuração do código permite trocar o comportamento
(desenvolvimento, testes, produção) sem alterar a lógica do sistema.
Valores sensíveis (como SECRET_KEY) vêm de variáveis de ambiente.
"""
import hashlib
import os
from datetime import timedelta
from decimal import Decimal

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


# Valor de desenvolvimento. Se ele ainda estiver em uso fora dos testes, o sistema gera uma
# chave aleatória própria e a guarda em instance/secret_key (veja create_app).
CHAVE_DEV = "dev-chave-apenas-para-desenvolvimento"


class Config:
    # Em desenvolvimento usamos um valor padrão. Em uso real, defina a
    # variável de ambiente SECRET_KEY com um valor longo e aleatório.
    SECRET_KEY = os.environ.get("SECRET_KEY", CHAVE_DEV)

    # SQLite: um único arquivo dentro da pasta instance/.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(BASE_DIR, "instance", "mercadogestor.db"),
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Desconto máximo (em % do total da venda) que o caixa pode dar.
    # Quando existirem perfis de usuário (Fase 8), o administrador poderá ter outro limite.
    DESCONTO_MAXIMO_PERCENTUAL = Decimal(os.environ.get("DESCONTO_MAXIMO_PERCENTUAL", "10"))

    # --- Segurança de acesso (Fase 8) ---
    # Cookie de sessão: inacessível ao JavaScript e não enviado em requisições de outros sites.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Se for publicar atrás de HTTPS, defina SESSION_COOKIE_SECURE = True.
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.environ.get("SESSAO_HORAS", "12")))
    LOGIN_MAX_TENTATIVAS = 5  # erros seguidos até bloquear a conta
    LOGIN_BLOQUEIO_MINUTOS = 5
    SENHA_TAMANHO_MIN = 8
    # scrypt é o padrão atual do Werkzeug; se o Python não o tiver, cai para PBKDF2.
    PASSWORD_HASH_METHOD = "scrypt" if hasattr(hashlib, "scrypt") else "pbkdf2:sha256:600000"


class TestConfig(Config):
    """Configuração dos testes: banco em memória, isolado do banco real."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    # Nos testes de rotas não precisamos enviar o token CSRF manualmente.
    # Um teste específico liga a proteção para provar que ela funciona.
    WTF_CSRF_ENABLED = False
    # Hash barato só nos testes (a suíte faria centenas de logins); um teste cobre o padrão real.
    PASSWORD_HASH_METHOD = "pbkdf2:sha256:1000"
