"""Rotas dos relatórios (tela e exportação CSV)."""
from datetime import date

from flask import Blueprint, flash, render_template, request

from app.services import relatorio_service as rel
from app.utils.csv_export import resposta_csv
from app.utils.erros import ErroDeNegocio

relatorios_bp = Blueprint("relatorios", __name__, url_prefix="/relatorios")


def _data(nome):
    try:
        return date.fromisoformat(request.args.get(nome, "").strip())
    except ValueError:
        return None


def _periodo():
    """Período pedido na URL; se faltar ou for inválido, usa o mês atual e avisa."""
    de, ate = _data("de"), _data("ate")
    if "de" not in request.args and "ate" not in request.args:
        return rel.periodo_padrao()
    try:
        rel.validar_periodo(de, ate)
    except ErroDeNegocio as erro:
        # Em CSV não há tela para mostrar o aviso: um flash ficaria "preso" e apareceria
        # na próxima página que a pessoa abrir.
        if not _quer_csv():
            flash(f"{erro} Mostrando o mês atual.", "warning")
        return rel.periodo_padrao()
    return de, ate


def _quer_csv():
    return request.args.get("formato") == "csv"


@relatorios_bp.route("/")
def indice():
    de, ate = rel.periodo_padrao()
    return render_template("relatorios/indice.html", de=de, ate=ate)


@relatorios_bp.route("/produtos")
def produtos():
    de, ate = _periodo()
    ordem = request.args.get("ordem", "quantidade")
    if ordem not in rel.ORDENS:
        ordem = "quantidade"
    linhas = rel.produtos_vendidos(de, ate, ordem)
    if _quer_csv():
        return resposta_csv(
            f"produtos-vendidos_{de}_{ate}.csv",
            [("Código", "texto"), ("Produto", "texto"), ("Unidade", "texto"), ("Quantidade", "qtd"),
             ("Receita", "moeda"), ("Custo", "moeda"), ("Lucro", "moeda"), ("Margem %", "pct")],
            [[l.codigo, l.nome, l.unidade, l.quantidade, l.receita, l.custo, l.lucro, l.margem] for l in linhas],
        )
    return render_template("relatorios/produtos.html", linhas=linhas, de=de, ate=ate, ordem=ordem, ordens=rel.ORDENS,
                           total_receita=sum(l.receita for l in linhas), total_custo=sum(l.custo for l in linhas))


@relatorios_bp.route("/pagamentos")
def pagamentos():
    de, ate = _periodo()
    linhas = rel.vendas_por_forma_pagamento(de, ate)
    if _quer_csv():
        return resposta_csv(
            f"formas-de-pagamento_{de}_{ate}.csv",
            [("Forma de pagamento", "texto"), ("Pagamentos", "inteiro"), ("Valor", "moeda")],
            [[l.nome, l.quantidade, l.valor] for l in linhas],
        )
    return render_template("relatorios/pagamentos.html", linhas=linhas, de=de, ate=ate,
                           total=sum(l.valor for l in linhas))


@relatorios_bp.route("/dias")
def dias():
    de, ate = _periodo()
    linhas = rel.vendas_por_dia(de, ate)
    if _quer_csv():
        return resposta_csv(
            f"vendas-por-dia_{de}_{ate}.csv",
            [("Data", "data"), ("Vendas", "inteiro"), ("Desconto", "moeda"), ("Total", "moeda"), ("Ticket médio", "moeda")],
            [[l.data, l.quantidade, l.desconto, l.total, l.ticket_medio] for l in linhas],
        )
    return render_template("relatorios/dias.html", linhas=linhas, de=de, ate=ate, totais=rel.totais_por_dia(linhas))
