"""Testes do Financeiro: lançamentos, contas a pagar, compra->conta e resumo mensal (RN40-RN47)."""
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from itertools import count

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Compra, Lancamento, Venda
from app.services import categoria_service, compra_service, estoque_service, fornecedor_service
from app.services import financeiro_service as fin
from app.services import produto_service, venda_service
from app.utils.erros import ErroDeNegocio
from app.utils.hoje import hoje_local

_n = count(1)
D = Decimal


def despesa(descricao="Aluguel", valor="1800,00", venc=None, categoria="ALUGUEL", **kw):
    return fin.criar("DESPESA", categoria, descricao, valor, venc or hoje_local(), **kw)


# ----------------------------------------------------------------- criar
def test_cria_despesa_pendente(app):
    l = despesa("  Aluguel   de novembro ", "1.800,00", date(2026, 11, 10))
    assert (l.descricao, l.valor, l.situacao) == ("Aluguel de novembro", D("1800.00"), "PENDENTE")
    assert l.categoria_nome == "Aluguel"


def test_despesa_ja_paga_usa_hoje_ou_data_informada(app):
    assert despesa(ja_pago=True).pago_em == hoje_local()
    ontem = hoje_local() - timedelta(days=1)
    assert despesa(ja_pago=True, data_pagamento=ontem.isoformat()).pago_em == ontem


def test_pagamento_no_futuro_recusado(app):
    with pytest.raises(ErroDeNegocio, match="futura"):
        despesa(ja_pago=True, data_pagamento=hoje_local() + timedelta(days=1))
    assert db.session.scalar(select(func.count(Lancamento.id))) == 0


def test_receita_nasce_recebida_na_propria_data(app):
    l = fin.criar("RECEITA", "OUTRAS_RECEITAS", "Comissão", "50", "2026-11-05")
    assert l.pago_em == date(2026, 11, 5) and l.situacao == "PAGO"


@pytest.mark.parametrize(
    "args, msg",
    [
        (("OUTRO", "ALUGUEL", "x", "1", "2026-11-01"), "Tipo"),
        (("DESPESA", "MERCADORIA", "x", "1", "2026-11-01"), "Compras"),  # RN41
        (("DESPESA", "XYZ", "x", "1", "2026-11-01"), "categoria"),
        (("DESPESA", "OUTRAS_RECEITAS", "x", "1", "2026-11-01"), "categoria"),
        (("RECEITA", "ALUGUEL", "x", "1", "2026-11-01"), "categoria"),
        (("DESPESA", "ALUGUEL", "  ", "1", "2026-11-01"), "descrição"),
        (("DESPESA", "ALUGUEL", "x" * 121, "1", "2026-11-01"), "120"),
        (("DESPESA", "ALUGUEL", "x", "0", "2026-11-01"), "maior que zero"),
        (("DESPESA", "ALUGUEL", "x", "-5", "2026-11-01"), "negativo"),
        (("DESPESA", "ALUGUEL", "x", "abc", "2026-11-01"), "Valor"),
        (("DESPESA", "ALUGUEL", "x", "1,234", "2026-11-01"), "casas"),
        (("DESPESA", "ALUGUEL", "x", "100000000", "2026-11-01"), "grande"),
        (("DESPESA", "ALUGUEL", "x", "1", ""), "data válida"),
        (("DESPESA", "ALUGUEL", "x", "1", "31/11/2026"), "data válida"),
        (("DESPESA", "ALUGUEL", "x", "1", "1999-12-31"), "ano"),
        (("DESPESA", "ALUGUEL", "x", "1", "2101-01-01"), "ano"),
    ],
)
def test_validacoes(app, args, msg):
    with pytest.raises(ErroDeNegocio, match=msg):
        fin.criar(*args)
    assert db.session.scalar(select(func.count(Lancamento.id))) == 0


# --------------------------------------------------- pagar/desfazer/cancelar
def test_pagar_e_nao_pagar_duas_vezes(app):
    l = despesa()
    fin.pagar(l.id)
    assert l.pago_em == hoje_local()
    with pytest.raises(ErroDeNegocio, match="já está paga"):
        fin.pagar(l.id)


def test_pagar_com_data_e_validacoes(app):
    l = despesa()
    with pytest.raises(ErroDeNegocio, match="futura"):
        fin.pagar(l.id, hoje_local() + timedelta(days=1))
    with pytest.raises(ErroDeNegocio, match="data válida"):
        fin.pagar(l.id, "lixo")
    ontem = hoje_local() - timedelta(days=1)  # relativo a hoje: não quebra com o passar do tempo
    assert fin.pagar(l.id, ontem.isoformat()).pago_em == ontem


def test_receita_nao_paga_nem_desfaz(app):
    r = fin.criar("RECEITA", "OUTRAS_RECEITAS", "x", "1", "2026-11-05")
    with pytest.raises(ErroDeNegocio, match="já nascem recebidas"):
        fin.pagar(r.id)
    with pytest.raises(ErroDeNegocio, match="Receitas"):
        fin.desfazer_pagamento(r.id)
    with pytest.raises(ErroDeNegocio):
        fin.cancelar(r.id)


def test_desfazer_pagamento(app):
    l = despesa(ja_pago=True)
    assert fin.desfazer_pagamento(l.id).pago_em is None
    with pytest.raises(ErroDeNegocio, match="não está paga"):
        fin.desfazer_pagamento(l.id)


def test_cancelar_so_pendente_e_some_das_listas(app):
    pend, paga = despesa("A"), despesa("B", ja_pago=True)
    with pytest.raises(ErroDeNegocio, match="pendentes"):
        fin.cancelar(paga.id)
    fin.cancelar(pend.id)
    assert pend.situacao == "CANCELADO"
    assert [l.descricao for l in fin.listar("todos")] == ["B"]
    with pytest.raises(ErroDeNegocio, match="já foi cancelado"):
        fin.cancelar(pend.id)
    with pytest.raises(ErroDeNegocio, match="cancelado"):
        fin.pagar(pend.id)


def test_acoes_em_inexistente(app):
    for f in (fin.pagar, fin.desfazer_pagamento, fin.cancelar, fin.buscar):
        with pytest.raises(ErroDeNegocio, match="não encontrado"):
            f(999)


def test_banco_barra_estados_impossiveis(app):
    for l in (
        Lancamento(tipo="RECEITA", categoria="OUTRAS_RECEITAS", descricao="x", valor=1, vencimento=date.today()),
        Lancamento(tipo="DESPESA", categoria="ALUGUEL", descricao="x", valor=1, vencimento=date.today(),
                   pago_em=date.today(), cancelado=True),
        Lancamento(tipo="DESPESA", categoria="ALUGUEL", descricao="x", valor=0, vencimento=date.today()),
        Lancamento(tipo="DESPESA", categoria="XYZ", descricao="x", valor=1, vencimento=date.today()),
    ):
        db.session.add(l)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


# ----------------------------------------------------------------- listar
def test_listar_filtros_e_ordem(app):
    hoje = hoje_local()
    b = despesa("B", venc=hoje + timedelta(days=5))
    a = despesa("A", venc=hoje - timedelta(days=2))
    c = despesa("C", venc=hoje, ja_pago=True)
    r = fin.criar("RECEITA", "OUTRAS_RECEITAS", "R", "10", hoje)
    assert [l.descricao for l in fin.listar()] == ["A", "B"]  # pendentes, mais antigos primeiro
    assert [l.descricao for l in fin.listar("pagos")] == ["C", "R"]
    assert len(fin.listar("todos")) == 4
    assert [l.descricao for l in fin.listar("todos", "RECEITA")] == ["R"]
    assert [l.descricao for l in fin.listar("todos", data_inicio=hoje, data_fim=hoje)] == ["C", "R"]
    with pytest.raises(ErroDeNegocio):
        fin.listar("xxx")
    with pytest.raises(ErroDeNegocio):
        fin.listar(tipo="X")
    with pytest.raises(ErroDeNegocio, match="data inicial"):
        fin.listar(data_inicio=hoje, data_fim=hoje - timedelta(days=1))


def test_vencida_e_totais(app):
    hoje = hoje_local()
    antiga = despesa("antiga", "100", hoje - timedelta(days=1))
    hoje_l = despesa("hoje", "50", hoje)
    futura = despesa("futura", "25", hoje + timedelta(days=1))
    despesa("paga", "999", hoje - timedelta(days=9), ja_pago=True)
    assert fin.esta_vencida(antiga) and not fin.esta_vencida(hoje_l) and not fin.esta_vencida(futura)
    assert fin.total_a_pagar() == (D("175.00"), D("100.00"))


# ------------------------------------------------------ compra -> conta a pagar
@pytest.fixture
def cenario(app):
    cat = categoria_service.criar("Laticínios")
    forn = fornecedor_service.criar("Bom Preço")
    prod = produto_service.criar(
        {"categoria_id": cat.id, "nome": "Leite", "codigo": f"X{next(_n)}", "unidade_medida": "UN",
         "preco_custo": "4,50", "preco_venda": "6,99", "estoque_minimo": "5"}
    )
    return forn, prod


def comprar(forn, prod, **kw):
    return compra_service.registrar(
        forn.id, [{"produto_id": prod.id, "quantidade": "10", "custo_unitario": "4,80"}], **kw
    )


def test_compra_a_vista_gera_conta_paga_hoje(cenario):
    c = comprar(*cenario)
    l = c.lancamento
    assert (l.tipo, l.categoria, l.valor, l.compra_id) == ("DESPESA", "MERCADORIA", D("48.00"), c.id)
    assert l.vencimento == l.pago_em == hoje_local()
    assert f"Compra #{c.id}" in l.descricao and "Bom Preço" in l.descricao


def test_compra_a_prazo_gera_conta_pendente(cenario):
    venc = hoje_local() + timedelta(days=30)
    l = comprar(*cenario, condicao="A_PRAZO", vencimento=venc.isoformat()).lancamento
    assert l.pago_em is None and l.vencimento == venc
    assert fin.pagar(l.id).pago_em == hoje_local()


def test_compra_a_prazo_vence_hoje_e_valido(cenario):
    assert comprar(*cenario, condicao="A_PRAZO", vencimento=hoje_local()).lancamento.pago_em is None


@pytest.mark.parametrize("cond, venc, msg", [
    ("A_PRAZO", None, "vencimento"),
    ("A_PRAZO", "", "vencimento"),
    ("A_PRAZO", "lixo", "data válida"),
    ("A_PRAZO", "2000-01-01", "anterior a hoje"),
    ("TALVEZ", None, "à vista ou a prazo"),
])
def test_compra_condicao_invalida_nao_grava_nada(cenario, cond, venc, msg):
    forn, prod = cenario
    with pytest.raises(ErroDeNegocio, match=msg):
        comprar(forn, prod, condicao=cond, vencimento=venc)
    assert db.session.scalar(select(func.count(Compra.id))) == 0
    assert db.session.scalar(select(func.count(Lancamento.id))) == 0
    db.session.refresh(prod)
    assert prod.quantidade_estoque == 0


def test_falha_ao_gerar_conta_desfaz_a_compra_inteira(cenario, monkeypatch):
    """Se a conta a pagar não puder ser gravada, compra + estoque + custo voltam atrás."""
    forn, prod = cenario
    original = db.session.commit

    def commit_falha():
        raise IntegrityError("x", {}, Exception("simulado"))

    monkeypatch.setattr(db.session, "commit", commit_falha)
    with pytest.raises(ErroDeNegocio, match="Nada foi alterado"):
        comprar(forn, prod)
    monkeypatch.setattr(db.session, "commit", original)
    assert db.session.scalar(select(func.count(Compra.id))) == 0
    assert db.session.scalar(select(func.count(Lancamento.id))) == 0
    db.session.refresh(prod)
    assert prod.quantidade_estoque == 0 and prod.preco_custo == D("4.50")


def test_conta_de_compra_nao_pode_ser_cancelada_mas_pode_desfazer_pagamento(cenario):
    l = comprar(*cenario, condicao="A_PRAZO", vencimento=hoje_local()).lancamento
    with pytest.raises(ErroDeNegocio, match="compra"):
        fin.cancelar(l.id)  # RN44
    fin.pagar(l.id)
    assert fin.desfazer_pagamento(l.id).pago_em is None


# ------------------------------------------------------------ resumo mensal
def vender(prod, qtd, quando_utc):
    v = venda_service.finalizar({prod.id: D(qtd)}, None, "PIX", None, str(uuid.uuid4()))
    v.data_hora = quando_utc
    db.session.commit()
    return v


@pytest.fixture
def loja(app):
    cat = categoria_service.criar("Mercearia")
    prod = produto_service.criar(
        {"categoria_id": cat.id, "nome": "Arroz", "codigo": f"A{next(_n)}", "unidade_medida": "UN",
         "preco_custo": "19,00", "preco_venda": "25,00", "estoque_minimo": "1"}
    )
    estoque_service.entrada(prod.id, "100", "Estoque inicial")
    return prod


def test_resumo_vazio(app):
    r = fin.resumo_mensal(2026, 11)
    assert (r.vendas, r.custo_vendido, r.lucro_bruto, r.resultado, r.margem_bruta) == (0, 0, 0, 0, None)
    assert r.despesas_por_categoria == [] and r.qtd_vendas == 0


def test_resumo_completo(loja, app):
    vender(loja, "4", datetime(2026, 11, 10, 15, 0))  # 4 x 25 = 100 ; custo 4 x 19 = 76
    vender(loja, "2", datetime(2026, 11, 20, 15, 0))  # 50 ; custo 38
    fin.criar("DESPESA", "ALUGUEL", "Aluguel", "30", "2026-11-10")  # pendente
    fin.criar("DESPESA", "ENERGIA", "Luz", "10", "2026-11-12", ja_pago=True)
    fin.criar("RECEITA", "OUTRAS_RECEITAS", "Comissão", "5", "2026-11-15")
    r = fin.resumo_mensal(2026, 11)
    assert (r.vendas, r.qtd_vendas, r.custo_vendido) == (D("150.00"), 2, D("114.00"))
    assert r.lucro_bruto == D("36.00") and r.margem_bruta == D("24.0")
    assert (r.despesas, r.despesas_pagas, r.despesas_pendentes) == (D("40.00"), D("10.00"), D("30.00"))
    assert r.outras_receitas == D("5.00")
    assert r.resultado == D("1.00")  # 36 + 5 - 40
    assert r.despesas_por_categoria == [("Aluguel", D("30.00")), ("Energia elétrica", D("10.00"))]


def test_mes_segue_o_horario_do_mercado_nao_o_utc(loja):
    # 01/12 01:00 UTC = 30/11 22:00 em São Paulo -> ainda é novembro.
    vender(loja, "1", datetime(2026, 12, 1, 1, 0))
    # 01/11 02:00 UTC = 31/10 23:00 em São Paulo -> é outubro.
    vender(loja, "1", datetime(2026, 11, 1, 2, 0))
    assert fin.resumo_mensal(2026, 11).qtd_vendas == 1
    assert fin.resumo_mensal(2026, 10).qtd_vendas == 1
    assert fin.resumo_mensal(2026, 12).qtd_vendas == 0


def test_compra_nao_vira_despesa_operacional_e_e_informativa(cenario):
    forn, prod = cenario
    c = comprar(forn, prod)
    mes = c.data_hora
    r = fin.resumo_mensal(hoje_local().year, hoje_local().month)
    assert r.compras == D("48.00")
    assert r.despesas == 0 and r.resultado == 0  # RN46: sem contagem em dobro
    assert mes is not None


def test_cancelados_ficam_fora_do_resumo(app):
    l = fin.criar("DESPESA", "ALUGUEL", "x", "99", "2026-11-10")
    fin.cancelar(l.id)
    assert fin.resumo_mensal(2026, 11).despesas == 0


def test_custo_usa_o_custo_copiado_na_venda_mesmo_se_o_produto_mudar_depois(loja):
    vender(loja, "1", datetime(2026, 11, 10, 15, 0))
    loja.preco_custo = D("30.00")
    db.session.commit()
    assert fin.resumo_mensal(2026, 11).custo_vendido == D("19.00")


def test_margem_e_resultado_negativo(loja):
    vender(loja, "1", datetime(2026, 11, 10, 15, 0))
    fin.criar("DESPESA", "SALARIOS", "Salário", "100", "2026-11-05")
    r = fin.resumo_mensal(2026, 11)
    assert r.resultado == D("-94.00")


@pytest.mark.parametrize("ano, mes", [(2026, 0), (2026, 13), (1999, 5), (2101, 1)])
def test_mes_invalido(app, ano, mes):
    with pytest.raises(ErroDeNegocio, match="Mês inválido"):
        fin.resumo_mensal(ano, mes)


def test_fevereiro_bissexto_inclui_dia_29(app):
    fin.criar("DESPESA", "ALUGUEL", "x", "10", "2028-02-29")
    assert fin.resumo_mensal(2028, 2).despesas == D("10.00")
    assert fin.resumo_mensal(2028, 3).despesas == 0
