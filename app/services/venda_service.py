"""Regras de negócio da Venda (PDV).

Numeração continua a de docs/01-modelagem.md (detalhes em docs/02-vendas-pdv.md):
- RN19: venda precisa de ao menos um item; quantidades seguem RN14/RN15 (estoque).
- RN20: preço e custo do item são COPIADOS do produto no momento da venda.
- RN21: subtotal do item = preço x quantidade, arredondado ao centavo (meio para cima).
- RN22: desconto sobre o total da venda, limitado a um percentual máximo (configurável);
        desconto em % é truncado para baixo no centavo (nunca passa do % digitado).
- RN23: o total da venda precisa ser maior que zero.
- RN24: dinheiro exige valor recebido >= total (em branco = valor exato), troco =
        recebido - total; Pix e cartões cobram exatamente o total.
- RN25: finalizar é ATÔMICO: venda + itens + pagamento + baixas de estoque
        (motivo "Venda #N") valem juntos ou não valem nada.
- RN26: venda concluída não é editada nem excluída (estorno/cancelamento: fase futura).
- RN27: o mesmo envio de formulário não gera duas vendas (token de envio único).

Exemplo de mercado: cliente leva 2 leites (R$ 6,99), 0,350 kg de tomate (R$ 8,90/kg)
e paga com nota de R$ 50,00 -> sistema calcula total, troco, baixa o estoque.
"""
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from flask import current_app
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import FORMAS_PAGAMENTO, ItemVenda, Pagamento, Produto, Venda
from app.services import estoque_service
from app.utils.datas import intervalo_utc
from app.utils.erros import ErroDeNegocio
from app.utils.formatacao import moeda, quantidade as formatar_quantidade
from app.utils.numeros import validar_decimal

CENTAVO = Decimal("0.01")
VALOR_MAXIMO = Decimal("99999999.99")
TIPOS_DESCONTO = {"VALOR": "R$", "PERCENTUAL": "%"}
LIMITE_LISTAGEM = 200


def _centavos(valor, modo=ROUND_HALF_UP):
    return Decimal(valor).quantize(CENTAVO, rounding=modo)


def desconto_maximo_percentual():
    return Decimal(str(current_app.config.get("DESCONTO_MAXIMO_PERCENTUAL", "10")))


# ------------------------------------------------------------------- resumo
@dataclass
class LinhaCarrinho:
    produto: Produto
    quantidade: Decimal
    preco_unitario: Decimal
    subtotal: Decimal
    problema: str = None  # texto de alerta para a tela (ex.: saldo insuficiente)


@dataclass
class Resumo:
    linhas: list
    subtotal: Decimal
    desconto: Decimal
    total: Decimal

    @property
    def vazio(self):
        return not self.linhas

    @property
    def tem_problema(self):
        return any(linha.problema for linha in self.linhas)


def calcular_desconto(subtotal, tipo, valor):
    """Converte o desconto pedido (R$ ou %) em reais, respeitando o limite (RN22)."""
    tipo = (tipo or "").strip().upper()
    if tipo not in TIPOS_DESCONTO:
        raise ErroDeNegocio("Escolha se o desconto é em R$ ou em %.")
    numero = validar_decimal(valor, "Desconto", 2, VALOR_MAXIMO)
    if numero == 0:
        return Decimal("0.00")
    if subtotal <= 0:
        raise ErroDeNegocio("Não há o que descontar: o carrinho está vazio.")

    maximo = desconto_maximo_percentual()
    if tipo == "PERCENTUAL":
        if numero > maximo:
            raise ErroDeNegocio(f"O desconto máximo permitido é {formatar_quantidade(maximo)}%.")
        return _centavos(subtotal * numero / 100, ROUND_DOWN)

    if numero > subtotal:
        raise ErroDeNegocio("O desconto não pode ser maior que o total da compra.")
    if numero * 100 > subtotal * maximo:
        limite_reais = _centavos(subtotal * maximo / 100, ROUND_DOWN)
        raise ErroDeNegocio(
            f"O desconto máximo permitido é {formatar_quantidade(maximo)}% "
            f"({moeda(limite_reais)} nesta compra)."
        )
    return numero


def montar_resumo(itens, desconto=None):
    """Calcula linhas, subtotal, desconto e total a partir do carrinho.

    itens: {produto_id: quantidade (Decimal)}.   desconto: None ou (tipo, valor).
    Os PREÇOS vêm sempre do banco, nunca do navegador (RN27 do carrinho).
    """
    produtos = {}
    if itens:
        achados = db.session.execute(select(Produto).where(Produto.id.in_(list(itens)))).scalars()
        produtos = {p.id: p for p in achados}

    linhas = []
    for produto_id, qtd in itens.items():
        produto = produtos.get(produto_id)
        if produto is None:
            continue
        problema = None
        if not produto.ativo:
            problema = "Produto inativo."
        elif qtd > produto.quantidade_estoque:
            problema = (
                f"Saldo insuficiente (há {formatar_quantidade(produto.quantidade_estoque)} "
                f"{produto.unidade_medida})."
            )
        linhas.append(
            LinhaCarrinho(
                produto=produto,
                quantidade=qtd,
                preco_unitario=produto.preco_venda,
                subtotal=_centavos(produto.preco_venda * qtd),  # RN21
                problema=problema,
            )
        )

    subtotal = sum((linha.subtotal for linha in linhas), Decimal("0.00"))
    valor_desconto = calcular_desconto(subtotal, *desconto) if desconto else Decimal("0.00")
    return Resumo(linhas, subtotal, valor_desconto, subtotal - valor_desconto)


# ---------------------------------------------------------------- pagamento
def _validar_pagamento(forma, valor_recebido, total):
    """Devolve (forma, valor, valor_recebido, troco) (RN24)."""
    forma = (forma or "").strip().upper()
    if forma not in FORMAS_PAGAMENTO:
        raise ErroDeNegocio("Selecione a forma de pagamento.")
    if forma != "DINHEIRO":
        return forma, total, None, Decimal("0.00")

    if valor_recebido is None or not str(valor_recebido).strip():
        recebido = total  # em branco: o cliente deu o valor exato
    else:
        recebido = validar_decimal(valor_recebido, "Valor recebido", 2, VALOR_MAXIMO)
    if recebido < total:
        raise ErroDeNegocio(f"Valor recebido insuficiente: faltam {moeda(total - recebido)}.")
    return forma, total, recebido, recebido - total


# ----------------------------------------------------------------- gravação
def finalizar(itens, desconto, forma_pagamento, valor_recebido=None, token_envio=None):
    """Registra a venda inteira de forma atômica (RN19 a RN27). Devolve a Venda.

    Tudo acontece em UMA transação: a venda, os itens, o pagamento e as
    baixas de estoque. Se qualquer passo falhar (ex.: o terceiro produto não
    tem saldo), o rollback desfaz tudo, inclusive as baixas dos dois primeiros.
    """
    if not itens:
        raise ErroDeNegocio("O carrinho está vazio.")  # RN19
    if token_envio and db.session.execute(
        select(Venda.id).where(Venda.token_envio == token_envio)
    ).first():
        raise ErroDeNegocio("Esta venda já foi registrada.")  # RN27

    try:
        resumo = montar_resumo(itens, desconto)
        if len(resumo.linhas) != len(itens):
            raise ErroDeNegocio("Há produto no carrinho que não existe mais.")
        if resumo.total <= 0:  # RN23
            raise ErroDeNegocio("A venda precisa ter valor maior que zero.")
        forma, valor, recebido, troco = _validar_pagamento(
            forma_pagamento, valor_recebido, resumo.total
        )

        venda = Venda(
            subtotal=resumo.subtotal,
            desconto=resumo.desconto,
            total=resumo.total,
            token_envio=token_envio or None,
        )
        db.session.add(venda)
        db.session.flush()  # gera o número da venda para usar no motivo da baixa

        for linha in resumo.linhas:
            db.session.add(
                ItemVenda(
                    venda_id=venda.id,
                    produto_id=linha.produto.id,
                    quantidade=linha.quantidade,
                    preco_unitario=linha.preco_unitario,  # RN20
                    custo_unitario=linha.produto.preco_custo,  # RN20
                    subtotal=linha.subtotal,
                )
            )
            try:
                estoque_service.saida(
                    linha.produto.id, linha.quantidade, f"Venda #{venda.id}", confirmar=False
                )
            except ErroDeNegocio as erro:
                raise ErroDeNegocio(f"{linha.produto.nome}: {erro}")

        db.session.add(
            Pagamento(venda_id=venda.id, forma=forma, valor=valor, valor_recebido=recebido, troco=troco)
        )
        db.session.commit()  # único commit: tudo vale junto
    except ErroDeNegocio:
        db.session.rollback()
        raise
    except IntegrityError:
        db.session.rollback()
        if token_envio and db.session.execute(
            select(Venda.id).where(Venda.token_envio == token_envio)
        ).first():
            raise ErroDeNegocio("Esta venda já foi registrada.")
        raise ErroDeNegocio("Não foi possível registrar a venda. Nada foi alterado.")
    except Exception:
        db.session.rollback()
        raise
    return venda


# ---------------------------------------------------------------- consultas
def venda_por_token(token):
    """A venda já registrada com este token de envio, ou None (RN27)."""
    if not token:
        return None
    return db.session.execute(select(Venda).where(Venda.token_envio == token)).scalar_one_or_none()


def buscar_venda(venda_id):
    consulta = (
        select(Venda)
        .options(
            joinedload(Venda.itens).joinedload(ItemVenda.produto),
            joinedload(Venda.pagamentos),
        )
        .where(Venda.id == venda_id)
    )
    venda = db.session.execute(consulta).unique().scalar_one_or_none()
    if venda is None:
        raise ErroDeNegocio("Venda não encontrada.")
    return venda


def listar_vendas(data_inicio=None, data_fim=None, limite=LIMITE_LISTAGEM):
    """Vendas da mais recente para a mais antiga. Datas no horário local (inclusivas)."""
    if data_inicio and data_fim and data_inicio > data_fim:
        raise ErroDeNegocio("A data inicial não pode ser posterior à data final.")
    consulta = (
        select(Venda)
        .options(joinedload(Venda.pagamentos))
        .order_by(Venda.data_hora.desc(), Venda.id.desc())
        .limit(limite)
    )
    inicio, fim_exclusivo = intervalo_utc(data_inicio, data_fim)
    if inicio:
        consulta = consulta.where(Venda.data_hora >= inicio)
    if fim_exclusivo:
        consulta = consulta.where(Venda.data_hora < fim_exclusivo)
    return db.session.execute(consulta).unique().scalars().all()
