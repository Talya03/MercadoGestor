"""v0.14 — regras de precificação (RN77–RN81). As contas usam exemplos de mercado de bairro."""
from decimal import Decimal as D
from itertools import count

import pytest

from app.extensions import db
from app.models import Produto
from app.services import categoria_service, produto_service
from app.services import precificacao_service as svc
from app.utils.erros import ErroDeNegocio

_n = count(1)


def novo(custo="7,00", venda="10,00", **extras):
    cat = categoria_service.listar()[0] if categoria_service.listar() else categoria_service.criar("Mercearia")
    dados = {"categoria_id": cat.id, "nome": f"Produto {next(_n)}", "codigo": f"C{next(_n)}",
                "unidade_medida": "UN", "preco_custo": custo, "preco_venda": venda, "estoque_minimo": "1"}
    dados.update(extras)
    return produto_service.criar(dados)


# ------------------------------------------------------------------ a conta
def test_exemplo_do_enunciado_custo_7_margem_30_da_10():
    assert svc.preco_sugerido("7", "30") == D("10.00")


def test_margem_e_diferente_de_markup():
    """Pôr 30% EM CIMA do custo (markup) dá 9,10, que é margem de 23%, não 30%."""
    assert svc.margem_liquida("7", "9.10") == D("23.08")
    assert svc.markup("7", "10") == D("42.86")


def test_despesas_entram_na_conta():
    # custo 10, margem 20% + 5% de taxa da maquininha: 10 / 0,75 = 13,333... -> 13,34
    assert svc.preco_sugerido("10", "20", "5") == D("13.34")


def test_arredonda_sempre_para_cima_e_nunca_fica_abaixo_da_margem():
    for custo in ("3.33", "4.50", "0.01", "19.99", "123.45"):
        for margem in ("10", "25.5", "33.33", "50"):
            preco = svc.preco_sugerido(custo, margem)
            assert svc.margem_liquida(custo, preco) >= D(margem) - D("0.01")  # só o arredondamento do %
            assert preco == preco.quantize(D("0.01"))
            assert preco * (1 - D(margem) / 100) >= D(custo)  # exato: descontada a margem, cobre o custo


def test_margem_zero_devolve_o_proprio_custo():
    assert svc.preco_sugerido("4.50", "0") == D("4.50")


def test_margem_atual_com_e_sem_preco():
    assert svc.margem_liquida("7", "10") == D("30.00")
    assert svc.margem_liquida("7", "10", "5") == D("25.00")
    assert svc.margem_liquida("12", "10") == D("-20.00")  # prejuízo aparece como margem negativa
    assert svc.margem_liquida("7", "0") is None


def test_sem_custo_nao_ha_sugestao_nem_markup():  # RN79
    assert svc.preco_sugerido("0", "30") is None
    assert svc.markup("0", "10") is None


# ------------------------------------------------------------- parâmetros
@pytest.mark.parametrize("margem,despesas", [("-1", "0"), ("30", "-5"), ("100", "0"), ("60", "40"),
                                                ("99,99", "0,01"), ("abc", "0"), ("", "0"), ("30", ""),
                                                ("1e2", "0"), ("NaN", "0"), ("30,123", "0")])
def test_parametros_invalidos_sao_recusados(margem, despesas):  # RN78
    with pytest.raises(ErroDeNegocio):
        svc.validar_parametros(margem, despesas)


def test_parametros_validos_aceitam_virgula():
    assert svc.validar_parametros("32,5", "4,25") == (D("32.50"), D("4.25"))
    assert svc.validar_parametros("99,98", "0") == (D("99.98"), D("0.00"))


def test_preco_enorme_e_recusado_em_vez_de_estourar_o_banco():
    with pytest.raises(ErroDeNegocio, match="grande demais"):
        svc.preco_sugerido("99999999.99", "50")


# ------------------------------------------------------------- situação/linhas
def test_situacao_de_cada_produto(app):
    sem_custo = novo(custo="0", venda="5")
    sem_preco = novo(custo="7", venda="0")
    abaixo = novo(custo="7", venda="9,99")
    exato = novo(custo="7", venda="10")
    acima = novo(custo="7", venda="15")
    por_id = {l["produto"].id: l for l in svc.linhas(D("30"), D("0"))}
    assert por_id[sem_custo.id]["situacao"] == svc.SEM_CUSTO and por_id[sem_custo.id]["sugerido"] is None
    assert por_id[sem_preco.id]["situacao"] == svc.SEM_PRECO
    assert por_id[abaixo.id]["situacao"] == svc.ABAIXO
    assert por_id[exato.id]["situacao"] == svc.OK       # preço igual ao sugerido já cumpre a meta
    assert por_id[acima.id]["situacao"] == svc.OK


def test_filtro_apenas_abaixo_traz_abaixo_e_sem_preco(app):
    abaixo = novo(custo="7", venda="9")
    sem_preco = novo(custo="7", venda="0")
    novo(custo="7", venda="12")
    novo(custo="0", venda="3")
    ids = {l["produto"].id for l in svc.linhas(D("30"), D("0"), apenas_abaixo=True)}
    assert ids == {abaixo.id, sem_preco.id}


def test_linhas_ignoram_produto_inativo_e_respeitam_busca(app):
    a = novo(nome="Arroz Tio João")
    b = novo(nome="Feijão Carioca")
    produto_service.alternar_ativo(b.id)
    nomes = [l["produto"].nome for l in svc.linhas(D("30"), D("0"))]
    assert nomes == ["Arroz Tio João"]
    assert svc.linhas(D("30"), D("0"), busca="zzz") == []


# ------------------------------------------------------------------ aplicar
def test_aplicar_grava_o_preco_sugerido_e_devolve_o_antigo(app):
    p = novo(custo="7", venda="8")
    produto, antigo = svc.aplicar(p.id, "30", "0")
    assert antigo == D("8.00") and produto.preco_venda == D("10.00")
    db.session.expire_all()
    assert db.session.get(Produto, p.id).preco_venda == D("10.00")


def test_aplicar_nao_mexe_em_custo_nem_estoque(app):
    p = novo(custo="7", venda="8")
    svc.aplicar(p.id, "30", "0")
    db.session.expire_all()
    p = db.session.get(Produto, p.id)
    assert p.preco_custo == D("7.00") and p.quantidade_estoque == 0


@pytest.mark.parametrize("margem,despesas", [("100", "0"), ("-5", "0"), ("x", "0")])
def test_aplicar_com_parametros_invalidos_nao_grava(app, margem, despesas):
    p = novo(custo="7", venda="8")
    with pytest.raises(ErroDeNegocio):
        svc.aplicar(p.id, margem, despesas)
    db.session.expire_all()
    assert db.session.get(Produto, p.id).preco_venda == D("8.00")


def test_aplicar_sem_custo_e_recusado(app):  # RN79
    p = novo(custo="0", venda="8")
    with pytest.raises(ErroDeNegocio, match="sem preço de custo"):
        svc.aplicar(p.id, "30", "0")
    db.session.expire_all()
    assert db.session.get(Produto, p.id).preco_venda == D("8.00")


def test_aplicar_em_inativo_ou_inexistente_e_recusado(app):
    p = novo()
    produto_service.alternar_ativo(p.id)
    with pytest.raises(ErroDeNegocio, match="inativo"):
        svc.aplicar(p.id, "30", "0")
    with pytest.raises(ErroDeNegocio):
        svc.aplicar(9999, "30", "0")
