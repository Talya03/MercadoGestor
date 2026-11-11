"""Application Factory do MercadoGestor.

Conceito: em vez de criar o `app` direto no topo do arquivo, usamos uma
função `create_app()`. Assim podemos criar aplicações diferentes (uma para
uso normal, outra para testes) com configurações distintas.
"""
import os
import secrets

from flask import Flask

from config import CHAVE_DEV, Config
from app.extensions import csrf, db


def _garantir_chave_secreta(app):
    """A chave assina o cookie de sessão: quem a conhece forja um login. Se ainda é a chave de
    desenvolvimento (pública, está no código), cria uma aleatória e a guarda em instance/secret_key.
    Prefira definir a variável de ambiente SECRET_KEY; os testes não passam por aqui."""
    if app.config["SECRET_KEY"] != CHAVE_DEV or app.config.get("TESTING"):
        return
    os.makedirs(app.instance_path, exist_ok=True)
    caminho = os.path.join(app.instance_path, "secret_key")
    try:
        with open(caminho, encoding="utf-8") as arquivo:
            chave = arquivo.read().strip()
    except FileNotFoundError:
        chave = ""
    if len(chave) < 32:
        chave = secrets.token_hex(32)
        descritor = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # só o dono lê
        with os.fdopen(descritor, "w", encoding="utf-8") as arquivo:
            arquivo.write(chave)
    app.config["SECRET_KEY"] = chave


def create_app(config_class=Config, instance_path=None):
    app = Flask(__name__, instance_relative_config=True, instance_path=instance_path)
    app.config.from_object(config_class)
    _garantir_chave_secreta(app)

    db.init_app(app)
    csrf.init_app(app)

    from app import models  # noqa: F401  (registra os modelos no SQLAlchemy)
    from app import seguranca
    from app.routes.auth import auth_bp
    from app.routes.backup import backup_bp
    from app.routes.categorias import categorias_bp
    from app.routes.compras import compras_bp
    from app.routes.estoque import estoque_bp
    from app.routes.financeiro import financeiro_bp
    from app.routes.fornecedores import fornecedores_bp
    from app.routes.main import main_bp
    from app.routes.pdv import pdv_bp
    from app.routes.precificacao import precificacao_bp
    from app.routes.produtos import produtos_bp
    from app.routes.relatorios import relatorios_bp
    from app.routes.usuarios import usuarios_bp
    from app.utils.formatacao import data_hora, moeda, percentual, quantidade, quantidade_com_sinal

    # O porteiro (before_request) é registrado DEPOIS do CSRF: o CSRF é conferido primeiro.
    seguranca.registrar(app)

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(categorias_bp)
    app.register_blueprint(produtos_bp)
    app.register_blueprint(estoque_bp)
    app.register_blueprint(precificacao_bp)
    app.register_blueprint(pdv_bp)
    app.register_blueprint(fornecedores_bp)
    app.register_blueprint(compras_bp)
    app.register_blueprint(financeiro_bp)
    app.register_blueprint(relatorios_bp)
    app.register_blueprint(usuarios_bp)
    app.register_blueprint(backup_bp)

    # Filtros usados nos templates: {{ preco|moeda }}, {{ saldo|quantidade }}
    app.add_template_filter(moeda, "moeda")
    app.add_template_filter(quantidade, "quantidade")
    app.add_template_filter(percentual, "percentual")
    app.add_template_filter(quantidade_com_sinal, "quantidade_com_sinal")
    app.add_template_filter(data_hora, "data_hora")

    return app
