"""Rotas do Financeiro: lançamentos (contas a pagar/receitas) e resumo mensal."""
import re
from datetime import date

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from app.models import TIPOS_LANCAMENTO
from app.models.lancamento import CATEGORIAS, CATEGORIAS_DESPESA, CATEGORIAS_RECEITA
from app.services import financeiro_service as fin
from app.utils.erros import ErroDeNegocio
from app.utils.hoje import hoje_local

financeiro_bp = Blueprint("financeiro", __name__, url_prefix="/financeiro")


def _data_do_filtro(nome):
    texto = request.args.get(nome, "").strip()
    try:
        return date.fromisoformat(texto) if texto else None
    except ValueError:
        return None


def _voltar(destino=None):
    """Volta para a lista com o mesmo filtro (campo 'voltar' é aceito só se for caminho interno)."""
    alvo = request.form.get("voltar", "")
    if alvo.startswith("/financeiro/") and not alvo.startswith("//"):
        return redirect(alvo)
    return redirect(url_for("financeiro.lista"))


@financeiro_bp.route("/")
def lista():
    status = request.args.get("status", "pendentes")
    if status not in fin.STATUS_VALIDOS:
        status = "pendentes"
    tipo = request.args.get("tipo") or None
    if tipo not in TIPOS_LANCAMENTO:
        tipo = None
    data_inicio, data_fim = _data_do_filtro("de"), _data_do_filtro("ate")
    try:
        lancamentos = fin.listar(status, tipo, data_inicio, data_fim)
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
        lancamentos = []
    total_pendente, total_vencido = fin.total_a_pagar()
    hoje = hoje_local()
    return render_template(
        "financeiro/lista.html",
        lancamentos=lancamentos,
        vencida=lambda l: fin.esta_vencida(l, hoje),
        status=status, tipo=tipo, data_inicio=data_inicio, data_fim=data_fim,
        total_pendente=total_pendente, total_vencido=total_vencido,
        hoje=hoje, limite=fin.LIMITE_LISTAGEM,
        voltar=request.full_path.rstrip("?"),
    )


@financeiro_bp.route("/novo", methods=["GET", "POST"])
def novo():
    tipo = request.values.get("tipo", "DESPESA")
    if tipo not in TIPOS_LANCAMENTO:
        tipo = "DESPESA"
    categorias = CATEGORIAS_DESPESA if tipo == "DESPESA" else CATEGORIAS_RECEITA
    categorias = [c for c in categorias if c != "MERCADORIA"]
    valores = request.form if request.method == "POST" else {}
    if request.method == "POST":
        try:
            fin.criar(
                tipo, valores.get("categoria"), valores.get("descricao"), valores.get("valor"),
                valores.get("data"), ja_pago=valores.get("ja_pago") == "1",
                data_pagamento=valores.get("data_pagamento"),
                usuario_id=g.usuario.id,  # RN67
            )
        except ErroDeNegocio as erro:
            flash(str(erro), "danger")
        else:
            flash("Receita lançada." if tipo == "RECEITA" else "Despesa lançada.", "success")
            return redirect(url_for("financeiro.lista", status="todos" if tipo == "RECEITA" else "pendentes"))
    return render_template(
        "financeiro/form.html", tipo=tipo, categorias=[(c, CATEGORIAS[c]) for c in categorias],
        valores=valores, hoje=hoje_local(),
    )


def _acao(funcao, mensagem):
    def rota(lancamento_id):
        try:
            if funcao is fin.pagar:
                funcao(lancamento_id, request.form.get("data_pagamento"))
            else:
                funcao(lancamento_id)
        except ErroDeNegocio as erro:
            flash(str(erro), "danger")
        else:
            flash(mensagem, "success")
        return _voltar()

    return rota


# Ações que alteram dados: só POST (e com CSRF).
financeiro_bp.add_url_rule("/<int:lancamento_id>/pagar", "pagar", _acao(fin.pagar, "Pagamento registrado."), methods=["POST"])
financeiro_bp.add_url_rule("/<int:lancamento_id>/desfazer", "desfazer", _acao(fin.desfazer_pagamento, "Pagamento desfeito: a conta voltou a pendente."), methods=["POST"])
financeiro_bp.add_url_rule("/<int:lancamento_id>/cancelar", "cancelar", _acao(fin.cancelar, "Lançamento cancelado."), methods=["POST"])


@financeiro_bp.route("/resumo")
def resumo():
    texto = request.args.get("mes", "")
    hoje = hoje_local()
    ano, mes = hoje.year, hoje.month
    if texto:
        achado = re.fullmatch(r"(\d{4})-(\d{2})", texto)
        if achado:
            ano, mes = int(achado.group(1)), int(achado.group(2))
        else:
            flash("Mês inválido. Mostrando o mês atual.", "warning")
    try:
        dados = fin.resumo_mensal(ano, mes)
    except ErroDeNegocio as erro:
        flash(f"{erro} Mostrando o mês atual.", "warning")
        ano, mes = hoje.year, hoje.month
        dados = fin.resumo_mensal(ano, mes)
    anterior = date(ano - 1, 12, 1) if mes == 1 else date(ano, mes - 1, 1)
    proximo = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
    return render_template(
        "financeiro/resumo.html", r=dados,
        anterior=anterior.strftime("%Y-%m") if anterior.year >= fin.ANO_MIN else None,
        proximo=proximo.strftime("%Y-%m") if proximo.year <= fin.ANO_MAX else None,
        mes_valor=f"{ano:04d}-{mes:02d}",
    )
