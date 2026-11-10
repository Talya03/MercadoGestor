"""Rotas de Compra de mercadoria.

O formulário tem um cabeçalho (fornecedor, documento, observação) e várias linhas de
item (produto, quantidade, custo). As linhas chegam como listas paralelas
(request.form.getlist). O token CSRF continua obrigatório (CSRFProtect global).
"""
import uuid
from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.services import compra_service, fornecedor_service, produto_service
from app.utils.erros import ErroDeNegocio

compras_bp = Blueprint("compras", __name__, url_prefix="/compras")


def _token_valido(texto):
    try:
        return str(uuid.UUID(str(texto)))
    except ValueError:
        return None


def _inteiro(texto):
    try:
        return int(texto)
    except (TypeError, ValueError):
        return None


def _data_do_filtro(nome):
    texto = request.args.get(nome, "").strip()
    try:
        return date.fromisoformat(texto) if texto else None
    except ValueError:
        return None


def _itens_do_formulario():
    """Monta a lista de itens a partir das colunas paralelas; ignora linhas totalmente vazias."""
    produtos = request.form.getlist("produto_id")
    quantidades = request.form.getlist("quantidade")
    custos = request.form.getlist("custo_unitario")
    itens = []
    for produto, quantidade, custo in zip(produtos, quantidades, custos):
        if not (produto.strip() or quantidade.strip() or custo.strip()):
            continue
        itens.append({"produto_id": produto, "quantidade": quantidade, "custo_unitario": custo})
    return itens


def _tela_nova(fornecedor_id=None, itens=None, documento="", observacao="", token=None,
               condicao="A_VISTA", vencimento=""):
    return render_template(
        "compras/form.html",
        fornecedores=fornecedor_service.listar(),
        produtos=produto_service.listar(),
        fornecedor_id=fornecedor_id,
        itens=itens or [{}],
        documento=documento,
        observacao=observacao,
        token=token or str(uuid.uuid4()),
        condicao=condicao,
        vencimento=vencimento,
    )


@compras_bp.route("/")
def lista():
    data_inicio = _data_do_filtro("de")
    data_fim = _data_do_filtro("ate")
    fornecedor_id = _inteiro(request.args.get("fornecedor"))
    try:
        compras = compra_service.listar(data_inicio, data_fim, fornecedor_id)
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
        compras = []
    return render_template(
        "compras/lista.html",
        compras=compras,
        total_periodo=sum((c.total for c in compras), 0),
        fornecedores=fornecedor_service.listar(incluir_inativos=True),
        fornecedor_id=fornecedor_id,
        data_inicio=data_inicio,
        data_fim=data_fim,
        limite=compra_service.LIMITE_LISTAGEM,
    )


@compras_bp.route("/nova", methods=["GET", "POST"])
def nova():
    if request.method == "GET":
        return _tela_nova(fornecedor_id=_inteiro(request.args.get("fornecedor")))

    token = _token_valido(request.form.get("token"))
    ja_registrada = compra_service.compra_por_token(token)
    if ja_registrada is not None:
        flash(f"A compra #{ja_registrada.id} já havia sido registrada.", "info")
        return redirect(url_for("compras.detalhe", compra_id=ja_registrada.id))

    fornecedor_id = _inteiro(request.form.get("fornecedor_id"))
    itens = _itens_do_formulario()
    documento = request.form.get("numero_documento", "")
    observacao = request.form.get("observacao", "")
    condicao = request.form.get("condicao", "A_VISTA")
    vencimento = request.form.get("vencimento", "")
    try:
        compra = compra_service.registrar(
            fornecedor_id, itens, documento, observacao, token, condicao, vencimento
        )
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
        # Reexibe tudo o que foi digitado, com o MESMO token (a compra ainda não existe).
        return _tela_nova(fornecedor_id, itens, documento, observacao, token or None, condicao, vencimento)

    flash(f"Compra #{compra.id} registrada. O estoque foi atualizado.", "success")
    return redirect(url_for("compras.detalhe", compra_id=compra.id))


@compras_bp.route("/<int:compra_id>")
def detalhe(compra_id):
    try:
        compra = compra_service.buscar(compra_id)
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
        return redirect(url_for("compras.lista"))
    return render_template("compras/detalhe.html", compra=compra)
