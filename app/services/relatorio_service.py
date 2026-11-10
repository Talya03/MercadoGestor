"""Relatórios de vendas (somente leitura).

Numeração continua a de docs/04-financeiro.md (detalhes em docs/05-relatorios-dashboard.md):
- RN48: todo relatório tem um período (datas inclusivas, no horário do mercado), com data inicial
        <= final e no máximo 366 dias (protege a tela de consultas gigantes).
- RN49: "Produtos mais vendidos": por produto, quantidade, receita (soma dos subtotais dos itens),
        custo (custo COPIADO na venda x quantidade) e lucro. Esses valores são ANTES do desconto
        dado no total da venda; o desconto aparece no relatório "por dia".
- RN50: "Formas de pagamento": soma do valor de cada forma nas vendas do período (o valor já é o
        que abateu da venda, sem o troco).
- RN51: "Vendas por dia": dia do mercado, nº de vendas, desconto, total e ticket médio.
        Dias sem venda não aparecem.

Exemplo de mercado: no mês, o leite vendeu 120 UN (R$ 838,80) com custo de R$ 540,00:
lucro bruto de R$ 298,80 e margem de 35,6%, antes dos descontos dados no caixa.
"""
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select

from app.extensions import db
from app.models import FORMAS_PAGAMENTO, ItemVenda, Pagamento, Produto, Venda
from app.utils.datas import intervalo_utc, para_local
from app.utils.erros import ErroDeNegocio
from app.utils.hoje import hoje_local

CENTAVO = Decimal("0.01")
MAX_DIAS = 366
ORDENS = {"quantidade": "Quantidade", "receita": "Receita", "lucro": "Lucro"}


def periodo_padrao():
    """Do dia 1º do mês atual até hoje (horário do mercado)."""
    hoje = hoje_local()
    return hoje.replace(day=1), hoje


def validar_periodo(data_inicio, data_fim):
    if data_inicio is None or data_fim is None:
        raise ErroDeNegocio("Informe a data inicial e a final.")
    if data_inicio > data_fim:
        raise ErroDeNegocio("A data inicial não pode ser posterior à data final.")
    if (data_fim - data_inicio).days + 1 > MAX_DIAS:
        raise ErroDeNegocio(f"O período pode ter no máximo {MAX_DIAS} dias.")


def _porcentagem(parte, todo):
    if not todo:
        return None
    return (Decimal(parte) / Decimal(todo) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


# ------------------------------------------------------- produtos mais vendidos
@dataclass
class LinhaProduto:
    produto_id: int
    codigo: str
    nome: str
    unidade: str
    quantidade: Decimal = Decimal("0")
    receita: Decimal = Decimal("0")
    custo: Decimal = Decimal("0")

    @property
    def lucro(self):
        return self.receita - self.custo

    @property
    def margem(self):
        return _porcentagem(self.lucro, self.receita)


def produtos_vendidos(data_inicio, data_fim, ordem="quantidade"):
    validar_periodo(data_inicio, data_fim)
    if ordem not in ORDENS:
        raise ErroDeNegocio("Ordenação inválida.")
    inicio, fim = intervalo_utc(data_inicio, data_fim)
    linhas = db.session.execute(
        select(
            Produto.id, Produto.codigo, Produto.nome, Produto.unidade_medida,
            ItemVenda.quantidade, ItemVenda.subtotal, ItemVenda.custo_unitario,
        )
        .join(ItemVenda, ItemVenda.produto_id == Produto.id)
        .join(Venda, Venda.id == ItemVenda.venda_id)
        .where(Venda.data_hora >= inicio, Venda.data_hora < fim)
    ).all()
    por_produto = {}
    for pid, codigo, nome, unidade, qtd, subtotal, custo in linhas:
        linha = por_produto.setdefault(pid, LinhaProduto(pid, codigo, nome, unidade))
        linha.quantidade += Decimal(qtd)
        linha.receita += Decimal(subtotal)
        linha.custo += (Decimal(custo) * Decimal(qtd)).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    # Desempate por nome para a ordem ser sempre a mesma.
    return sorted(por_produto.values(), key=lambda l: (-getattr(l, ordem), l.nome.casefold(), l.produto_id))


# ----------------------------------------------------------- formas de pagamento
@dataclass
class LinhaPagamento:
    forma: str
    nome: str
    quantidade: int
    valor: Decimal


def vendas_por_forma_pagamento(data_inicio, data_fim):
    validar_periodo(data_inicio, data_fim)
    inicio, fim = intervalo_utc(data_inicio, data_fim)
    linhas = db.session.execute(
        select(Pagamento.forma, Pagamento.valor)
        .join(Venda, Venda.id == Pagamento.venda_id)
        .where(Venda.data_hora >= inicio, Venda.data_hora < fim)
    ).all()
    por_forma = {}
    for forma, valor in linhas:
        atual = por_forma.setdefault(forma, LinhaPagamento(forma, FORMAS_PAGAMENTO.get(forma, forma), 0, Decimal("0")))
        atual.quantidade += 1
        atual.valor += Decimal(valor)
    return sorted(por_forma.values(), key=lambda l: (-l.valor, l.nome))


# ------------------------------------------------------------------ por dia
@dataclass
class LinhaDia:
    data: object
    quantidade: int = 0
    desconto: Decimal = Decimal("0")
    total: Decimal = Decimal("0")

    @property
    def ticket_medio(self):
        return (self.total / self.quantidade).quantize(CENTAVO, rounding=ROUND_HALF_UP) if self.quantidade else None


def vendas_por_dia(data_inicio, data_fim):
    validar_periodo(data_inicio, data_fim)
    inicio, fim = intervalo_utc(data_inicio, data_fim)
    vendas = db.session.execute(
        select(Venda.data_hora, Venda.desconto, Venda.total).where(Venda.data_hora >= inicio, Venda.data_hora < fim)
    ).all()
    por_dia = {}
    for momento, desconto, total in vendas:
        dia = para_local(momento).date()  # o dia é o do MERCADO, não o de UTC (RN51)
        linha = por_dia.setdefault(dia, LinhaDia(dia))
        linha.quantidade += 1
        linha.desconto += Decimal(desconto)
        linha.total += Decimal(total)
    return [por_dia[d] for d in sorted(por_dia)]


def totais_por_dia(linhas):
    """(nº de vendas, descontos, total) somando as linhas do relatório por dia."""
    return (
        sum(l.quantidade for l in linhas),
        sum((l.desconto for l in linhas), Decimal("0")),
        sum((l.total for l in linhas), Decimal("0")),
    )
