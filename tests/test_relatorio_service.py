"""Testes dos relatórios de vendas e do painel inicial (RN48 a RN54)."""
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from itertools import count

import pytest

from app.extensions import db
from app.models import Venda
from app.services import categoria_service, dashboard_service, estoque_service, financeiro_service
from app.services import produto_service, relatorio_service as rel, venda_service
from app.utils.erros import ErroDeNegocio
from app.utils.hoje import hoje_local

D = Decimal
_n = count(1)
NOV = (date(2026, 11, 1), date(2026, 11, 30))


@pytest.fixture
def cat(app):
    return categoria_service.criar("Mercearia")


def produto(cat, nome, venda, custo, unidade="UN", saldo="1000", minimo="5"):
    p = produto_service.criar({
        "categoria_id": cat.id, "nome": nome, "codigo": f"P{next(_n)}", "unidade_medida": unidade,
        "preco_custo": custo, "preco_venda": venda, "estoque_minimo": minimo})
    if D(saldo) > 0:
        estoque_service.entrada(p.id, saldo, "Estoque inicial")
    return p


def vender(itens, quando_utc, forma="PIX", recebido=None, desconto=None):
    """itens: {produto: quantidade}. Grava a venda e carimba o horário (UTC)."""
    v = venda_service.finalizar({p.id: D(q) for p, q in itens.items()}, desconto, forma, recebido, str(uuid.uuid4()))
    v.data_hora = quando_utc
    db.session.commit()
    return v


# ----------------------------------------------------------------- período
def test_periodo_padrao_vai_do_dia_1_ate_hoje(app):
    de, ate = rel.periodo_padrao()
    assert de == hoje_local().replace(day=1) and ate == hoje_local()


@pytest.mark.parametrize("de, ate, msg", [
    (None, date(2026, 1, 1), "Informe"),
    (date(2026, 1, 1), None, "Informe"),
    (date(2026, 2, 1), date(2026, 1, 1), "posterior"),
    (date(2025, 1, 1), date(2026, 1, 2), "366"),
])
def test_periodo_invalido(app, de, ate, msg):
    for funcao in (rel.produtos_vendidos, rel.vendas_por_forma_pagamento, rel.vendas_por_dia):
        with pytest.raises(ErroDeNegocio, match=msg):
            funcao(de, ate)


def test_periodo_de_366_dias_e_aceito_e_um_dia_tambem(app):
    assert rel.vendas_por_dia(date(2026, 1, 1), date(2027, 1, 1)) == []  # 366 dias
    assert rel.vendas_por_dia(date(2026, 1, 1), date(2026, 1, 1)) == []


# -------------------------------------------------------- produtos vendidos
def test_produtos_vendidos_soma_quantidade_receita_custo_lucro_margem(cat):
    leite = produto(cat, "Leite 1L", "6,99", "4,50")
    tomate = produto(cat, "Tomate", "8,90", "5,00", "KG")
    vender({leite: 10, tomate: "2.5"}, datetime(2026, 11, 10, 15))
    vender({leite: 5}, datetime(2026, 11, 20, 15))
    linhas = {l.nome: l for l in rel.produtos_vendidos(*NOV, ordem="receita")}
    l = linhas["Leite 1L"]
    assert (l.quantidade, l.receita, l.custo) == (D("15"), D("104.85"), D("67.50"))  # 15x6,99 ; 15x4,50
    assert l.lucro == D("37.35") and l.margem == D("35.6")
    t = linhas["Tomate"]
    assert (t.quantidade, t.receita, t.custo) == (D("2.5"), D("22.25"), D("12.50"))
    assert t.unidade == "KG"


def test_ordenacao_e_desempate(cat):
    a = produto(cat, "Arroz", "10", "9")      # lucro 1/un
    b = produto(cat, "Bolacha", "5", "1")     # lucro 4/un
    c = produto(cat, "Café", "10", "9")
    vender({a: 3, b: 1, c: 3}, datetime(2026, 11, 10, 15))
    nomes = lambda o: [l.nome for l in rel.produtos_vendidos(*NOV, ordem=o)]
    assert nomes("quantidade") == ["Arroz", "Café", "Bolacha"]  # empate: por nome
    assert nomes("receita") == ["Arroz", "Café", "Bolacha"]
    assert nomes("lucro") == ["Bolacha", "Arroz", "Café"]
    with pytest.raises(ErroDeNegocio, match="Ordenação"):
        rel.produtos_vendidos(*NOV, ordem="nome")


def test_custo_e_o_copiado_na_venda_nao_o_atual(cat):
    p = produto(cat, "Arroz", "25", "19")
    vender({p: 1}, datetime(2026, 11, 10, 15))
    p.preco_custo = D("30")
    db.session.commit()
    assert rel.produtos_vendidos(*NOV)[0].custo == D("19.00")


def test_margem_none_sem_receita_e_lucro_negativo(cat):
    p = produto(cat, "Promoção", "3", "5")  # vende abaixo do custo
    vender({p: 2}, datetime(2026, 11, 10, 15))
    l = rel.produtos_vendidos(*NOV)[0]
    assert l.lucro == D("-4.00") and l.margem == D("-66.7")
    assert rel.LinhaProduto(1, "c", "n", "UN").margem is None


def test_produto_inativo_continua_no_historico(cat):
    p = produto(cat, "Antigo", "5", "3")
    vender({p: 1}, datetime(2026, 11, 10, 15))
    produto_service.alternar_ativo(p.id)
    assert [l.nome for l in rel.produtos_vendidos(*NOV)] == ["Antigo"]


def test_fronteira_do_periodo_usa_o_dia_do_mercado(cat):
    p = produto(cat, "Pão", "1", "0,5")
    vender({p: 1}, datetime(2026, 12, 1, 2, 59))   # 30/11 23:59 em SP -> dentro de novembro
    vender({p: 1}, datetime(2026, 12, 1, 3, 0))    # 01/12 00:00 em SP -> fora
    vender({p: 1}, datetime(2026, 11, 1, 2, 59))   # 31/10 23:59 em SP -> fora
    vender({p: 1}, datetime(2026, 11, 1, 3, 0))    # 01/11 00:00 em SP -> dentro
    assert rel.produtos_vendidos(*NOV)[0].quantidade == 2
    assert [l.data for l in rel.vendas_por_dia(*NOV)] == [date(2026, 11, 1), date(2026, 11, 30)]


# ---------------------------------------------------------------- pagamentos
def test_formas_de_pagamento_somam_valor_sem_troco(cat):
    p = produto(cat, "Leite", "10", "5")
    vender({p: 1}, datetime(2026, 11, 10, 15), "DINHEIRO", recebido="50")   # troco 40; valor 10
    vender({p: 3}, datetime(2026, 11, 11, 15), "PIX")
    vender({p: 2}, datetime(2026, 11, 12, 15), "PIX")
    vender({p: 1}, datetime(2026, 11, 13, 15), "CREDITO")
    linhas = rel.vendas_por_forma_pagamento(*NOV)
    assert [(l.nome, l.quantidade, l.valor) for l in linhas] == [
        ("Pix", 2, D("50.00")), ("Cartão de crédito", 1, D("10.00")), ("Dinheiro", 1, D("10.00"))]


def test_pagamentos_fora_do_periodo_ficam_de_fora(cat):
    p = produto(cat, "Leite", "10", "5")
    vender({p: 1}, datetime(2026, 10, 15, 15))
    assert rel.vendas_por_forma_pagamento(*NOV) == []


# --------------------------------------------------------------------- dias
def test_vendas_por_dia_com_desconto_total_e_ticket(cat):
    p = produto(cat, "Leite", "10", "5")
    vender({p: 10}, datetime(2026, 11, 10, 15), desconto=("PERCENTUAL", "10"))  # 100 -> 90
    vender({p: 5}, datetime(2026, 11, 10, 18))                                    # 50
    vender({p: 1}, datetime(2026, 11, 12, 15))                                    # 10
    linhas = rel.vendas_por_dia(*NOV)
    assert [l.data for l in linhas] == [date(2026, 11, 10), date(2026, 11, 12)]  # em ordem; sem dias vazios
    d10 = linhas[0]
    assert (d10.quantidade, d10.desconto, d10.total, d10.ticket_medio) == (2, D("10.00"), D("140.00"), D("70.00"))
    assert rel.totais_por_dia(linhas) == (3, D("10.00"), D("150.00"))
    assert rel.LinhaDia(date.today()).ticket_medio is None
    assert rel.totais_por_dia([]) == (0, D("0"), D("0"))


# ---------------------------------------------------------------- dashboard
def test_painel_vazio(app):
    p = dashboard_service.montar()
    assert (p.vendas_hoje_qtd, p.vendas_hoje_total, p.vendas_ontem_total) == (0, 0, 0)
    assert p.ticket_medio_hoje is None and p.estoque_baixo == [] and p.contas_a_vencer == []
    assert p.mes.resultado == 0 and p.hoje == hoje_local()


def test_painel_vendas_hoje_ontem_e_ticket(cat):
    from datetime import timezone
    from app.utils.datas import FUSO_LOCAL
    p = produto(cat, "Leite", "10", "5")
    hoje = hoje_local()

    def em(dia, hora):  # hora local -> UTC naive
        return datetime.combine(dia, datetime.min.time()).replace(hour=hora, tzinfo=FUSO_LOCAL).astimezone(timezone.utc).replace(tzinfo=None)

    vender({p: 3}, em(hoje, 9))
    vender({p: 2}, em(hoje, 10))
    vender({p: 4}, em(hoje - timedelta(days=1), 23))
    vender({p: 9}, em(hoje - timedelta(days=2), 12))
    painel = dashboard_service.montar()
    assert (painel.vendas_hoje_qtd, painel.vendas_hoje_total) == (2, D("50.00"))
    assert painel.ticket_medio_hoje == D("25.00")
    assert painel.vendas_ontem_total == D("40.00")


def test_painel_estoque_baixo_limita_a_5_e_ordena_pelos_mais_criticos(cat):
    for i in range(7):
        produto(cat, f"Baixo {i}", "5", "3", saldo=str(i), minimo="10")  # saldos 0..6, todos <= mínimo
    produto(cat, "Folgado", "5", "3", saldo="100", minimo="10")
    inativo = produto(cat, "Inativo", "5", "3", saldo="0", minimo="10")
    produto_service.alternar_ativo(inativo.id)
    painel = dashboard_service.montar()
    assert painel.estoque_baixo_total == 7  # inativo e folgado não contam
    assert [p.nome for p in painel.estoque_baixo] == [f"Baixo {i}" for i in range(5)]


def test_painel_contas(app):
    hoje = hoje_local()
    financeiro_service.criar("DESPESA", "ALUGUEL", "vencida", "100", hoje - timedelta(days=2))
    financeiro_service.criar("DESPESA", "ENERGIA", "em 7 dias", "50", hoje + timedelta(days=7))
    financeiro_service.criar("DESPESA", "AGUA", "em 8 dias", "30", hoje + timedelta(days=8))
    financeiro_service.criar("DESPESA", "AGUA", "paga", "999", hoje, ja_pago=True)
    financeiro_service.criar("RECEITA", "OUTRAS_RECEITAS", "receita", "5", hoje)
    painel = dashboard_service.montar()
    assert [l.descricao for l in painel.contas_a_vencer] == ["vencida", "em 7 dias"]  # a de 8 dias fica fora
    assert (painel.contas_pendente, painel.contas_vencido) == (D("180.00"), D("100.00"))


def test_painel_limita_contas_a_5(app):
    for i in range(8):
        financeiro_service.criar("DESPESA", "ALUGUEL", f"c{i}", "1", hoje_local())
    assert len(dashboard_service.montar().contas_a_vencer) == 5
