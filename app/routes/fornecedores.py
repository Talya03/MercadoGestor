"""Rotas de Fornecedor (apenas HTTP: recebe o pedido, chama o service, responde)."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.forms.fornecedor_form import FornecedorForm
from app.services import fornecedor_service
from app.utils.erros import ErroDeNegocio

fornecedores_bp = Blueprint("fornecedores", __name__, url_prefix="/fornecedores")


@fornecedores_bp.route("/")
def lista():
    busca = request.args.get("q", "").strip()
    incluir_inativos = request.args.get("inativos") == "1"
    return render_template(
        "fornecedores/lista.html",
        fornecedores=fornecedor_service.listar(busca, incluir_inativos),
        busca=busca,
        incluir_inativos=incluir_inativos,
    )


def _dados(form):
    return form.nome.data, form.documento.data, form.telefone.data, form.contato.data


@fornecedores_bp.route("/novo", methods=["GET", "POST"])
def novo():
    form = FornecedorForm()
    if form.validate_on_submit():
        try:
            fornecedor_service.criar(*_dados(form))
        except ErroDeNegocio as erro:
            flash(str(erro), "danger")
        else:
            flash("Fornecedor cadastrado com sucesso.", "success")
            return redirect(url_for("fornecedores.lista"))
    return render_template("fornecedores/form.html", form=form, titulo="Novo fornecedor")


@fornecedores_bp.route("/<int:fornecedor_id>/editar", methods=["GET", "POST"])
def editar(fornecedor_id):
    try:
        fornecedor = fornecedor_service.buscar(fornecedor_id)
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
        return redirect(url_for("fornecedores.lista"))

    form = FornecedorForm(obj=fornecedor)
    if form.validate_on_submit():
        try:
            fornecedor_service.editar(fornecedor_id, *_dados(form))
        except ErroDeNegocio as erro:
            flash(str(erro), "danger")
        else:
            flash("Fornecedor atualizado com sucesso.", "success")
            return redirect(url_for("fornecedores.lista"))
    return render_template("fornecedores/form.html", form=form, titulo="Editar fornecedor")


@fornecedores_bp.route("/<int:fornecedor_id>/alternar", methods=["POST"])
def alternar(fornecedor_id):
    try:
        fornecedor = fornecedor_service.alternar_ativo(fornecedor_id)
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
    else:
        situacao = "ativado" if fornecedor.ativo else "desativado"
        flash(f"Fornecedor {situacao} com sucesso.", "success")
    return redirect(url_for("fornecedores.lista"))
