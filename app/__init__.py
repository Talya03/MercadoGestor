"""Application Factory do MercadoGestor.

Conceito: em vez de criar o `app` direto no topo do arquivo, usamos uma
função `create_app()`. Assim podemos criar aplicações diferentes (uma para
uso normal, outra para testes) com configurações distintas.
"""
from flask import Flask

from config import Config
from app.extensions import csrf, db


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    db.init_app(app)
    csrf.init_app(app)

    from app import models  # noqa: F401  (registra os modelos no SQLAlchemy)
    from app.routes.categorias import categorias_bp
    from app.routes.main import main_bp
    from app.routes.produtos import produtos_bp
    from app.utils.formatacao import moeda, quantidade

    app.register_blueprint(main_bp)
    app.register_blueprint(categorias_bp)
    app.register_blueprint(produtos_bp)

    # Filtros usados nos templates: {{ preco|moeda }}, {{ saldo|quantidade }}
    app.add_template_filter(moeda, "moeda")
    app.add_template_filter(quantidade, "quantidade")

    return app
