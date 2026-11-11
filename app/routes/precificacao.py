"""Precificação: simular o preço ideal e, se quiser, aplicá-lo (quem pode: mesmo grupo do catálogo)."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.services import categoria_service, precificacao_service as prec
from app.services import produto_service
from app.utils.erros import ErroDeNegocio
from app.utils.numeros import formatar_decimal_br

precificacao_bp = Blueprint("precificacao", __name__, url_prefix="/precificacao")

# Só estas chaves voltam na URL depois de aplicar (nada vindo do formulário é repassado além delas).
_FILTROS = ("margem", "despesas", "q", "categoria", "abaixo")


def _parametros(origem):
    """Margem e despesas pedidas; se faltarem ou forem inválidas, usa os padrões e avisa."""
    margem_txt = origem.get("margem", "").strip() or formatar_decimal_br(prec.MARGEM_PADRAO)
    despesas_txt = origem.get("despesas", "").strip() or formatar_decimal_br(prec.DESPESAS_PADRAO)
    try:
        return (*prec.validar_parametros(margem_txt, despesas_txt), margem_txt, despesas_txt)
    except ErroDeNegocio as erro:
        flash(f"{erro} Mostrando os valores padrão.", "warning")
        return (prec.MARGEM_PADRAO, prec.DESPESAS_PADRAO,
                formatar_decimal_br(prec.MARGEM_PADRAO), formatar_decimal_br(prec.DESPESAS_PADRAO))


@precificacao_bp.route("/")
def lista():
    margem, despesas, margem_txt, despesas_txt = _parametros(request.args)
    busca = request.args.get("q", "").strip()
    categoria_id = request.args.get("categoria", type=int)
    abaixo = request.args.get("abaixo") == "1"
    linhas = prec.linhas(margem, despesas, busca=busca, categoria_id=categoria_id, apenas_abaixo=abaixo)
    return render_template(
        "precificacao/lista.html", linhas=linhas, categorias=categoria_service.listar(),
        margem=margem_txt, despesas=despesas_txt, busca=busca, categoria_id=categoria_id, abaixo=abaixo,
        filtros={k: request.args.get(k) for k in _FILTROS if request.args.get(k)},
    )


@precificacao_bp.route("/<int:produto_id>/aplicar", methods=["POST"])
def aplicar(produto_id):
    filtros = {k: request.form.get(k) for k in _FILTROS if request.form.get(k)}
    try:
        # RN80: o preço é recalculado aqui; o formulário só informa margem e despesas.
        produto, antigo = prec.aplicar(produto_id, request.form.get("margem", ""), request.form.get("despesas", ""))
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
    else:
        flash(f'Preço de "{produto.nome}" alterado de R$ {formatar_decimal_br(antigo)} '
              f'para R$ {formatar_decimal_br(produto.preco_venda)}.', "success")
    return redirect(url_for("precificacao.lista", **filtros))
