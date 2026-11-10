"""Dados da página inicial (painel). Somente leitura; reaproveita os outros services.

- RN52: "hoje" e "ontem" são dias do mercado (America/Sao_Paulo).
- RN53: estoque baixo segue a RN07 (saldo <= mínimo, produtos ativos); a lista mostra os 5 mais críticos.
- RN54: "contas a vencer" = despesas pendentes vencidas ou que vencem nos próximos 7 dias (as 5 mais antigas).
"""
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select

from app.extensions import db
from app.models import Venda
from app.services import financeiro_service, produto_service
from app.utils.datas import intervalo_utc
from app.utils.hoje import hoje_local

DIAS_ALERTA_CONTAS = 7
ITENS_NO_PAINEL = 5


@dataclass
class Painel:
    hoje: object
    vendas_hoje_qtd: int = 0
    vendas_hoje_total: Decimal = Decimal("0")
    vendas_ontem_total: Decimal = Decimal("0")
    estoque_baixo_total: int = 0
    estoque_baixo: list = field(default_factory=list)
    contas_pendente: Decimal = Decimal("0")
    contas_vencido: Decimal = Decimal("0")
    contas_a_vencer: list = field(default_factory=list)
    mes: object = None  # ResumoMensal do mês atual

    @property
    def ticket_medio_hoje(self):
        if not self.vendas_hoje_qtd:
            return None
        return (self.vendas_hoje_total / self.vendas_hoje_qtd).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _vendas_do_dia(dia):
    inicio, fim = intervalo_utc(dia, dia)
    qtd, total = db.session.execute(
        select(func.count(Venda.id), func.coalesce(func.sum(Venda.total), 0)).where(
            Venda.data_hora >= inicio, Venda.data_hora < fim
        )
    ).one()
    return qtd, Decimal(total).quantize(Decimal("0.01"))


def montar():
    hoje = hoje_local()
    painel = Painel(hoje=hoje)
    painel.vendas_hoje_qtd, painel.vendas_hoje_total = _vendas_do_dia(hoje)
    painel.vendas_ontem_total = _vendas_do_dia(hoje - timedelta(days=1))[1]

    baixo = produto_service.listar(apenas_estoque_baixo=True)
    painel.estoque_baixo_total = len(baixo)
    painel.estoque_baixo = sorted(baixo, key=lambda p: (p.quantidade_estoque - p.estoque_minimo, p.nome.casefold()))[:ITENS_NO_PAINEL]

    painel.contas_pendente, painel.contas_vencido = financeiro_service.total_a_pagar()
    painel.contas_a_vencer = financeiro_service.listar(
        "pendentes", "DESPESA", None, hoje + timedelta(days=DIAS_ALERTA_CONTAS), limite=ITENS_NO_PAINEL
    )
    painel.mes = financeiro_service.resumo_mensal(hoje.year, hoje.month)
    return painel
