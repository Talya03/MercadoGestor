"""Rotas de Produto."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from wtforms.fields import SelectChoice

from app.forms.produto_form import ProdutoForm
from app.services import categoria_service, produto_service
from app.utils.erros import ErroDeNegocio

produtos_bp = Blueprint("produtos", __name__, url_prefix="/produtos")


def _opcoes_de_categoria(produto=None):
    """Opções do <select>: só categorias ativas (+ a atual do produto, se inativa)."""
    categorias = categoria_service.listar()
    opcoes = [SelectChoice("0", "Selecione...")]
    opcoes += [SelectChoice(str(c.id), c.nome) for c in categorias]
    if produto is not None and produto.categoria not in categorias:
        opcoes.append(SelectChoice(str(produto.categoria.id), f"{produto.categoria.nome} (inativa)"))
    return opcoes


def _avisar_se_preciso(produto):
    aviso = produto_service.avisos(produto)
    if aviso:
        flash(aviso, "warning")


@produtos_bp.route("/")
def lista():
    busca = request.args.get("q", "").strip()
    categoria_id = request.args.get("categoria", type=int)
    incluir_inativos = request.args.get("inativos") == "1"
    estoque_baixo = request.args.get("baixo") == "1"
    produtos = produto_service.listar(busca, categoria_id, incluir_inativos, estoque_baixo)
    return render_template(
        "produtos/lista.html",
        produtos=produtos,
        categorias=categoria_service.listar(incluir_inativas=True),
        busca=busca,
        categoria_id=categoria_id,
        incluir_inativos=incluir_inativos,
        estoque_baixo=estoque_baixo,
    )


@produtos_bp.route("/novo", methods=["GET", "POST"])
def novo():
    if not categoria_service.listar():
        flash("Cadastre ao menos uma categoria antes de cadastrar produtos.", "warning")
        return redirect(url_for("categorias.nova"))

    form = ProdutoForm()
    form.categoria_id.choices = _opcoes_de_categoria()
    if form.validate_on_submit():
        try:
            produto = produto_service.criar(form.dados())
        except ErroDeNegocio as erro:
            flash(str(erro), "danger")
        else:
            flash("Produto cadastrado com sucesso.", "success")
            _avisar_se_preciso(produto)
            return redirect(url_for("produtos.lista"))
    return render_template("produtos/form.html", form=form, titulo="Novo produto", produto=None)


@produtos_bp.route("/<int:produto_id>/editar", methods=["GET", "POST"])
def editar(produto_id):
    try:
        produto = produto_service.buscar(produto_id)
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
        return redirect(url_for("produtos.lista"))

    form = ProdutoForm(obj=produto)
    form.categoria_id.choices = _opcoes_de_categoria(produto)
    if form.validate_on_submit():
        try:
            produto = produto_service.editar(produto_id, form.dados())
        except ErroDeNegocio as erro:
            flash(str(erro), "danger")
        else:
            flash("Produto atualizado com sucesso.", "success")
            _avisar_se_preciso(produto)
            return redirect(url_for("produtos.lista"))
    return render_template(
        "produtos/form.html", form=form, titulo="Editar produto", produto=produto
    )


@produtos_bp.route("/<int:produto_id>/alternar", methods=["POST"])
def alternar(produto_id):
    try:
        produto = produto_service.alternar_ativo(produto_id)
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
    else:
        situacao = "ativado" if produto.ativo else "desativado"
        flash(f"Produto {situacao} com sucesso.", "success")
    return redirect(url_for("produtos.lista"))
