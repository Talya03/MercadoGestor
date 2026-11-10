"""Rotas principais.

Conceito: Blueprint agrupa rotas relacionadas. Cada módulo do sistema
(produtos, estoque, PDV...) terá o seu próprio blueprint.
"""
from flask import Blueprint, render_template

from app.services import dashboard_service

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    return render_template("index.html", p=dashboard_service.montar())
