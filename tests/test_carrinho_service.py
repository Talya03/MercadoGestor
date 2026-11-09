"""Testes do carrinho do PDV (a 'sessão' aqui é um dicionário comum)."""
from decimal import Decimal
from itertools import count

import pytest

from app.services import carrinho_service as carrinho
from app.services import categoria_service, estoque_service, produto_service
from app.utils.erros import ErroDeNegocio

_codigos = count(1)


@pytest.fixture
def categoria(app):
    return categoria_service.criar("Mercearia")


def novo_produto(categoria, unidade="UN", saldo="20", **extras):
    dados = {
        "categoria_id": categoria.id,
        "nome": f"Produto {next(_codigos)}",
        "codigo": f"C{next(_codigos)}",
        "unidade_medida": unidade,
        "preco_custo": "4,50",
        "preco_venda": "6,99",
        "estoque_minimo": "5",
    }
    dados.update(extras)
    produto = produto_service.criar(dados)
    if Decimal(saldo) > 0:
        estoque_service.entrada(produto.id, saldo, "Estoque inicial")
    return produto


@pytest.fixture
def leite(categoria):
    return novo_produto(categoria, nome="Leite 1L", saldo="20")


@pytest.fixture
def tomate(categoria):
    return novo_produto(categoria, unidade="KG", nome="Tomate", saldo="10")


# ---------------------------------------------------------------- adicionar
def test_adiciona_item_e_soma_quantidades_repetidas(leite):
    sessao = {}
    carrinho.adicionar(sessao, leite.id, "2")
    carrinho.adicionar(sessao, leite.id, "3")
    assert carrinho.ler(sessao) == {leite.id: Decimal("5")}


def test_quantidade_padrao_e_um_quando_nao_informada(leite):
    sessao = {}
    carrinho.adicionar(sessao, leite.id)
    assert carrinho.ler(sessao) == {leite.id: Decimal("1")}


def test_carrinho_guarda_apenas_quantidade_nunca_preco(leite):
    sessao = {}
    carrinho.adicionar(sessao, leite.id, "2")
    guardado = str(sessao)
    assert "6.99" not in guardado and "6,99" not in guardado
    assert sessao[carrinho.CHAVE_CARRINHO] == {str(leite.id): "2.000"}


def test_produto_por_peso_aceita_quantidade_fracionada_com_virgula(tomate):
    sessao = {}
    carrinho.adicionar(sessao, tomate.id, "0,350")
    assert carrinho.ler(sessao) == {tomate.id: Decimal("0.350")}


def test_unidade_contavel_recusa_meia_unidade(leite):
    sessao = {}
    with pytest.raises(ErroDeNegocio, match="quantidades inteiras"):
        carrinho.adicionar(sessao, leite.id, "1,5")
    assert carrinho.ler(sessao) == {}


@pytest.mark.parametrize("quantidade", ["0", "-1", "abc", "NaN", "", "1,2345"])
def test_quantidade_invalida_e_recusada(tomate, quantidade):
    sessao = {}
    with pytest.raises(ErroDeNegocio):
        carrinho.adicionar(sessao, tomate.id, quantidade)
    assert carrinho.ler(sessao) == {}


def test_nao_adiciona_mais_do_que_o_saldo(leite):
    sessao = {}
    with pytest.raises(ErroDeNegocio, match="Saldo insuficiente de .*há 20 UN"):
        carrinho.adicionar(sessao, leite.id, "21")
    assert carrinho.ler(sessao) == {}


def test_soma_que_estoura_o_saldo_e_recusada_e_preserva_o_que_ja_estava(leite):
    sessao = {}
    carrinho.adicionar(sessao, leite.id, "15")
    with pytest.raises(ErroDeNegocio, match="Saldo insuficiente"):
        carrinho.adicionar(sessao, leite.id, "6")
    assert carrinho.ler(sessao) == {leite.id: Decimal("15")}


def test_produto_sem_estoque_nao_entra_no_carrinho(categoria):
    vazio = novo_produto(categoria, saldo="0")
    with pytest.raises(ErroDeNegocio, match="Saldo insuficiente"):
        carrinho.adicionar({}, vazio.id, "1")


def test_produto_inativo_nao_entra_no_carrinho(leite):
    produto_service.alternar_ativo(leite.id)
    with pytest.raises(ErroDeNegocio, match="inativo"):
        carrinho.adicionar({}, leite.id, "1")


def test_produto_inexistente(app):
    with pytest.raises(ErroDeNegocio, match="Produto não encontrado"):
        carrinho.adicionar({}, 999, "1")


# -------------------------------------------------------- alterar e remover
def test_define_nova_quantidade(leite):
    sessao = {}
    carrinho.adicionar(sessao, leite.id, "2")
    carrinho.definir_quantidade(sessao, leite.id, "7")
    assert carrinho.ler(sessao) == {leite.id: Decimal("7")}


def test_quantidade_zero_remove_o_item(leite):
    sessao = {}
    carrinho.adicionar(sessao, leite.id, "2")
    carrinho.definir_quantidade(sessao, leite.id, "0")
    assert carrinho.ler(sessao) == {}


def test_definir_quantidade_de_item_que_nao_esta_no_carrinho(leite):
    with pytest.raises(ErroDeNegocio, match="não está no carrinho"):
        carrinho.definir_quantidade({}, leite.id, "1")


@pytest.mark.parametrize("quantidade", ["21", "-1", "abc", "1,5"])
def test_definir_quantidade_invalida_nao_altera_o_carrinho(leite, quantidade):
    sessao = {}
    carrinho.adicionar(sessao, leite.id, "2")
    with pytest.raises(ErroDeNegocio):
        carrinho.definir_quantidade(sessao, leite.id, quantidade)
    assert carrinho.ler(sessao) == {leite.id: Decimal("2")}


def test_remove_item_e_ignora_item_ausente(leite, tomate):
    sessao = {}
    carrinho.adicionar(sessao, leite.id, "2")
    carrinho.adicionar(sessao, tomate.id, "1")
    carrinho.remover(sessao, leite.id)
    carrinho.remover(sessao, 999)  # não existe: nada acontece
    assert carrinho.ler(sessao) == {tomate.id: Decimal("1")}


# -------------------------------------------------- dado corrompido na sessão
def test_leitura_ignora_dados_invalidos_da_sessao():
    sessao = {
        carrinho.CHAVE_CARRINHO: {
            "abc": "1",
            "5": "xyz",
            "7": "-2",
            "0": "1",
            "": "1",
            "8": "NaN",
            "9": "Infinity",
            "3": "2",
        }
    }
    assert carrinho.ler(sessao) == {3: Decimal("2")}


def test_leitura_com_sessao_vazia_ou_estranha():
    assert carrinho.ler({}) == {}
    assert carrinho.ler({carrinho.CHAVE_CARRINHO: None}) == {}


# ----------------------------------------------------------------- desconto
def test_desconto_na_sessao():
    sessao = {}
    assert carrinho.ler_desconto(sessao) is None
    carrinho.definir_desconto(sessao, "PERCENTUAL", "5")
    assert carrinho.ler_desconto(sessao) == ("PERCENTUAL", "5")
    carrinho.limpar_desconto(sessao)
    assert carrinho.ler_desconto(sessao) is None


@pytest.mark.parametrize("lixo", ["texto", 5, ["so-um"], ["a", "b", "c"], {}])
def test_desconto_corrompido_na_sessao_e_ignorado(lixo):
    assert carrinho.ler_desconto({carrinho.CHAVE_DESCONTO: lixo}) is None


def test_limpar_esvazia_carrinho_e_desconto(leite):
    sessao = {}
    carrinho.adicionar(sessao, leite.id, "2")
    carrinho.definir_desconto(sessao, "VALOR", "1")
    carrinho.limpar(sessao)
    assert carrinho.ler(sessao) == {}
    assert carrinho.ler_desconto(sessao) is None
