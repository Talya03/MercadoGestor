"""Application Factory do MercadoGestor.

Conceito: em vez de criar o `app` direto no topo do arquivo, usamos uma
função `create_app()`. Assim podemos criar aplicações diferentes (uma para
uso normal, outra para testes) com configurações distintas.
"""
from flask import Flask

from config import Config
from app.extensions import db


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    db.init_app(app)

    from app.routes.main import main_bp

    app.register_blueprint(main_bp)

    return app
