"""Rotas de Categoria (apenas HTTP: recebe o pedido, chama o service, responde)."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.forms.categoria_form import CategoriaForm
from app.services import categoria_service
from app.utils.erros import ErroDeNegocio

categorias_bp = Blueprint("categorias", __name__, url_prefix="/categorias")


@categorias_bp.route("/")
def lista():
    busca = request.args.get("q", "").strip()
    incluir_inativas = request.args.get("inativas") == "1"
    categorias = categoria_service.listar(busca, incluir_inativas)
    return render_template(
        "categorias/lista.html",
        categorias=categorias,
        busca=busca,
        incluir_inativas=incluir_inativas,
    )


@categorias_bp.route("/nova", methods=["GET", "POST"])
def nova():
    form = CategoriaForm()
    if form.validate_on_submit():
        try:
            categoria_service.criar(form.nome.data, form.descricao.data)
        except ErroDeNegocio as erro:
            flash(str(erro), "danger")
        else:
            flash("Categoria cadastrada com sucesso.", "success")
            return redirect(url_for("categorias.lista"))
    return render_template("categorias/form.html", form=form, titulo="Nova categoria")


@categorias_bp.route("/<int:categoria_id>/editar", methods=["GET", "POST"])
def editar(categoria_id):
    try:
        categoria = categoria_service.buscar(categoria_id)
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
        return redirect(url_for("categorias.lista"))

    form = CategoriaForm(obj=categoria)
    if form.validate_on_submit():
        try:
            categoria_service.editar(categoria_id, form.nome.data, form.descricao.data)
        except ErroDeNegocio as erro:
            flash(str(erro), "danger")
        else:
            flash("Categoria atualizada com sucesso.", "success")
            return redirect(url_for("categorias.lista"))
    return render_template("categorias/form.html", form=form, titulo="Editar categoria")


@categorias_bp.route("/<int:categoria_id>/alternar", methods=["POST"])
def alternar(categoria_id):
    # Só aceita POST: ações que alteram dados nunca devem ser um simples link (GET).
    try:
        categoria = categoria_service.alternar_ativo(categoria_id)
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
    else:
        situacao = "ativada" if categoria.ativo else "desativada"
        flash(f"Categoria {situacao} com sucesso.", "success")
    return redirect(url_for("categorias.lista"))
