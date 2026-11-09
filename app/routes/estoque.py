"""Rotas do Controle de Estoque."""
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from wtforms.fields import SelectChoice

from app.forms.estoque_form import MovimentacaoForm
from app.models.movimentacao_estoque import TIPOS_MOVIMENTACAO
from app.services import estoque_service, produto_service
from app.utils.erros import ErroDeNegocio
from app.utils.formatacao import quantidade

estoque_bp = Blueprint("estoque", __name__, url_prefix="/estoque")

# Uma única tela serve as três operações; só mudam textos e o service chamado.
OPERACOES = {
    "entrada": {
        "titulo": "Entrada de mercadoria",
        "rotulo_quantidade": "Quantidade recebida",
        "ajuda": "Use quando chegar mercadoria. (Compras de fornecedores terão tela própria em breve.)",
        "botao": "Registrar entrada",
        "sucesso": "Entrada registrada",
        "motivos": ["Compra de fornecedor", "Estoque inicial", "Devolução de cliente", "Bonificação do fornecedor"],
        "servico": estoque_service.entrada,
    },
    "saida": {
        "titulo": "Saída de mercadoria",
        "rotulo_quantidade": "Quantidade que saiu",
        "ajuda": "Use para perdas, vencimentos, consumo próprio etc. (As vendas serão baixadas pelo PDV.)",
        "botao": "Registrar saída",
        "sucesso": "Saída registrada",
        "motivos": ["Produto vencido", "Perda ou quebra", "Consumo próprio", "Doação", "Troca com fornecedor"],
        "servico": estoque_service.saida,
    },
    "ajuste": {
        "titulo": "Ajuste de estoque",
        "rotulo_quantidade": "Quantidade contada (novo saldo)",
        "ajuda": "Depois de contar as prateleiras, informe quanto realmente existe. O sistema calcula a diferença.",
        "botao": "Registrar ajuste",
        "sucesso": "Ajuste registrado",
        "motivos": ["Contagem de inventário", "Correção de lançamento", "Diferença encontrada"],
        "servico": estoque_service.ajuste,
    },
}


def _data_do_filtro(nome):
    """Lê ?de=2026-11-01 da URL; valor inválido é simplesmente ignorado."""
    texto = request.args.get(nome, "").strip()
    try:
        return date.fromisoformat(texto) if texto else None
    except ValueError:
        return None


@estoque_bp.route("/")
def lista():
    """Consulta de saldo atual, com alerta de estoque mínimo."""
    busca = request.args.get("q", "").strip()
    apenas_baixo = request.args.get("baixo") == "1"
    produtos = produto_service.listar(busca, apenas_estoque_baixo=apenas_baixo)
    total_baixo = len(produto_service.listar(apenas_estoque_baixo=True))
    return render_template(
        "estoque/lista.html",
        produtos=produtos,
        busca=busca,
        apenas_baixo=apenas_baixo,
        total_baixo=total_baixo,
    )


@estoque_bp.route("/<any(entrada,saida,ajuste):operacao>", methods=["GET", "POST"])
def movimentar(operacao):
    config = OPERACOES[operacao]
    produtos = produto_service.listar()
    if not produtos:
        flash("Cadastre ao menos um produto antes de movimentar o estoque.", "warning")
        return redirect(url_for("produtos.novo"))

    form = MovimentacaoForm()
    form.produto_id.choices = [SelectChoice("0", "Selecione...")] + [
        SelectChoice(
            str(p.id),
            f"{p.nome} · {p.codigo} (saldo: {quantidade(p.quantidade_estoque)} {p.unidade_medida})",
        )
        for p in produtos
    ]
    form.quantidade.label.text = config["rotulo_quantidade"]
    form.submit.label.text = config["botao"]

    if request.method == "GET":
        # Vindo da lista de saldos, o produto já chega escolhido: ?produto=7
        form.produto_id.data = request.args.get("produto", type=int)

    if form.validate_on_submit():
        try:
            movimentacao = config["servico"](
                form.produto_id.data, form.quantidade.data, form.motivo.data
            )
        except ErroDeNegocio as erro:
            flash(str(erro), "danger")
        else:
            produto = movimentacao.produto
            flash(
                f"{config['sucesso']}: {produto.nome} agora tem "
                f"{quantidade(produto.quantidade_estoque)} {produto.unidade_medida}.",
                "success",
            )
            if produto.quantidade_estoque == 0:
                flash(f"Atenção: {produto.nome} está sem estoque.", "warning")
            elif produto.estoque_baixo:
                flash(
                    f"Atenção: {produto.nome} está com estoque baixo "
                    f"(mínimo: {quantidade(produto.estoque_minimo)} {produto.unidade_medida}).",
                    "warning",
                )
            return redirect(url_for("estoque.lista"))

    return render_template("estoque/form.html", form=form, operacao=operacao, config=config)


@estoque_bp.route("/historico")
def historico():
    produto_id = request.args.get("produto", type=int)
    tipo = request.args.get("tipo", "").strip().upper() or None
    data_inicio = _data_do_filtro("de")
    data_fim = _data_do_filtro("ate")

    try:
        movimentacoes = estoque_service.historico(produto_id, tipo, data_inicio, data_fim)
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
        movimentacoes = []

    return render_template(
        "estoque/historico.html",
        movimentacoes=movimentacoes,
        produtos=produto_service.listar(incluir_inativos=True),
        tipos=TIPOS_MOVIMENTACAO,
        produto_id=produto_id,
        tipo=tipo,
        data_inicio=data_inicio,
        data_fim=data_fim,
        limite=estoque_service.LIMITE_HISTORICO,
    )
