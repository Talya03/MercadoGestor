"""Rotas do PDV (Ponto de Venda), do comprovante e da lista de vendas.

Conceito: o carrinho vive na SESSÃO (cookie assinado) e guarda só {produto: quantidade}.
O navegador nunca manda preço: os valores são sempre lidos do banco (veja carrinho_service).
Estes formulários são pequenos e as regras ficam nos services, por isso não há
classes WTForms aqui. O token CSRF continua obrigatório em todos os POST.
"""
import uuid
from datetime import date, datetime, timezone

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.models import FORMAS_PAGAMENTO
from app.services import carrinho_service, produto_service, venda_service
from app.utils.datas import para_local
from app.utils.erros import ErroDeNegocio

pdv_bp = Blueprint("pdv", __name__, url_prefix="/pdv")

LIMITE_RESULTADOS_BUSCA = 12


# ------------------------------------------------------------------ helpers
def _token_da_sessao():
    """Um token novo por venda em andamento (evita vender duas vezes no clique duplo)."""
    if carrinho_service.CHAVE_TOKEN not in session:
        session[carrinho_service.CHAVE_TOKEN] = str(uuid.uuid4())
    return session[carrinho_service.CHAVE_TOKEN]


def _token_valido(texto):
    """Só aceita UUID de verdade; qualquer outra coisa vira 'sem token'."""
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


def _montar_resumo():
    """Resumo do carrinho; se o desconto guardado deixou de valer, remove e avisa."""
    itens = carrinho_service.ler(session)
    desconto = carrinho_service.ler_desconto(session)
    try:
        return venda_service.montar_resumo(itens, desconto)
    except ErroDeNegocio as erro:
        carrinho_service.limpar_desconto(session)
        flash(f"Desconto removido: {erro}", "warning")
        return venda_service.montar_resumo(itens, None)


def _voltar_ao_pdv():
    return redirect(url_for("pdv.tela"))


# --------------------------------------------------------------------- tela
@pdv_bp.route("/")
def tela():
    busca = request.args.get("q", "").strip()
    resultados = produto_service.listar(busca)[:LIMITE_RESULTADOS_BUSCA] if busca else []
    return render_template(
        "pdv/tela.html",
        busca=busca,
        resultados=resultados,
        resumo=_montar_resumo(),
        desconto=carrinho_service.ler_desconto(session),
        formas=FORMAS_PAGAMENTO,
        tipos_desconto=venda_service.TIPOS_DESCONTO,
        desconto_maximo=venda_service.desconto_maximo_percentual(),
        token=_token_da_sessao(),
    )


# ----------------------------------------------------------------- carrinho
@pdv_bp.route("/adicionar", methods=["POST"])
def adicionar():
    produto_id = _inteiro(request.form.get("produto_id"))
    if produto_id is None:
        flash("Produto inválido.", "danger")
        return _voltar_ao_pdv()
    try:
        carrinho_service.adicionar(session, produto_id, request.form.get("quantidade") or "1")
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
    return _voltar_ao_pdv()


@pdv_bp.route("/adicionar-por-codigo", methods=["POST"])
def adicionar_por_codigo():
    try:
        produto = produto_service.buscar_ativo_por_codigo(request.form.get("codigo"))
        carrinho_service.adicionar(session, produto.id, request.form.get("quantidade") or "1")
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
    return _voltar_ao_pdv()


@pdv_bp.route("/item/<int:produto_id>/quantidade", methods=["POST"])
def alterar_quantidade(produto_id):
    try:
        carrinho_service.definir_quantidade(session, produto_id, request.form.get("quantidade"))
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
    return _voltar_ao_pdv()


@pdv_bp.route("/item/<int:produto_id>/remover", methods=["POST"])
def remover_item(produto_id):
    carrinho_service.remover(session, produto_id)
    return _voltar_ao_pdv()


@pdv_bp.route("/cancelar", methods=["POST"])
def cancelar():
    carrinho_service.limpar(session)
    flash("Venda cancelada. O carrinho foi esvaziado.", "info")
    return _voltar_ao_pdv()


# ----------------------------------------------------------------- desconto
@pdv_bp.route("/desconto", methods=["POST"])
def aplicar_desconto():
    tipo = (request.form.get("tipo") or "").strip().upper()
    valor = request.form.get("valor", "")
    try:
        subtotal = venda_service.montar_resumo(carrinho_service.ler(session)).subtotal
        reais = venda_service.calcular_desconto(subtotal, tipo, valor)  # valida tudo (RN22)
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
        return _voltar_ao_pdv()

    if reais == 0:
        carrinho_service.limpar_desconto(session)
    else:
        carrinho_service.definir_desconto(session, tipo, valor)
        flash("Desconto aplicado.", "success")
    return _voltar_ao_pdv()


@pdv_bp.route("/desconto/remover", methods=["POST"])
def remover_desconto():
    carrinho_service.limpar_desconto(session)
    return _voltar_ao_pdv()


# ---------------------------------------------------------------- finalizar
@pdv_bp.route("/finalizar", methods=["POST"])
def finalizar():
    token = _token_valido(request.form.get("token"))

    # Reenvio do mesmo formulário (clique duplo, botão "voltar"): a venda já existe.
    # Em vez de dar erro, levamos a pessoa ao comprovante dela.
    ja_registrada = venda_service.venda_por_token(token)
    if ja_registrada is not None:
        carrinho_service.limpar(session)
        session.pop(carrinho_service.CHAVE_TOKEN, None)
        flash(f"A venda #{ja_registrada.id} já havia sido registrada.", "info")
        return redirect(url_for("pdv.comprovante", venda_id=ja_registrada.id))

    try:
        venda = venda_service.finalizar(
            carrinho_service.ler(session),
            carrinho_service.ler_desconto(session),
            request.form.get("forma"),
            request.form.get("valor_recebido"),
            token,
        )
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
        return _voltar_ao_pdv()

    carrinho_service.limpar(session)
    session.pop(carrinho_service.CHAVE_TOKEN, None)  # a próxima venda terá token novo
    flash(f"Venda #{venda.id} registrada com sucesso.", "success")
    return redirect(url_for("pdv.comprovante", venda_id=venda.id))


# --------------------------------------------------- comprovante e histórico
@pdv_bp.route("/vendas/<int:venda_id>")
def comprovante(venda_id):
    try:
        venda = venda_service.buscar_venda(venda_id)
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
        return redirect(url_for("pdv.vendas"))
    return render_template("pdv/comprovante.html", venda=venda)


@pdv_bp.route("/vendas")
def vendas():
    data_inicio = _data_do_filtro("de")
    data_fim = _data_do_filtro("ate")
    if "de" not in request.args and "ate" not in request.args:
        # Sem filtro, mostramos as vendas de HOJE (no horário do mercado).
        data_inicio = data_fim = para_local(datetime.now(timezone.utc)).date()

    try:
        lista = venda_service.listar_vendas(data_inicio, data_fim)
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
        lista = []

    return render_template(
        "pdv/vendas.html",
        vendas=lista,
        total_periodo=sum((v.total for v in lista), 0),
        data_inicio=data_inicio,
        data_fim=data_fim,
        limite=venda_service.LIMITE_LISTAGEM,
    )
