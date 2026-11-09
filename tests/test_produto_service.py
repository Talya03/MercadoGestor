"""Testes das regras de negócio de produto."""
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import MovimentacaoEstoque
from app.services import categoria_service, produto_service as service
from app.utils.erros import ErroDeNegocio


@pytest.fixture
def categoria(app):
    return categoria_service.criar("Laticínios")


def dados(categoria, **extras):
    base = {
        "categoria_id": categoria.id,
        "nome": "Leite Integral 1L",
        "codigo": "7891000100103",
        "unidade_medida": "UN",
        "preco_custo": "4,50",
        "preco_venda": "6,99",
        "estoque_minimo": "5",
    }
    base.update(extras)
    return base


def definir_estoque(produto, quantidade):
    # Atalho só para os testes (o service de estoque virá na Fase 4).
    produto.quantidade_estoque = Decimal(quantidade)
    db.session.commit()


# ---------- criação ----------
def test_cria_produto_com_valores_em_formato_brasileiro(categoria):
    p = service.criar(dados(categoria))
    assert p.id is not None
    assert p.preco_custo == Decimal("4.50")
    assert p.preco_venda == Decimal("6.99")
    assert p.estoque_minimo == Decimal("5.000")
    assert p.ativo is True


def test_produto_novo_sempre_comeca_com_estoque_zero(categoria):  # RN12
    p = service.criar(dados(categoria, quantidade_estoque="999"))
    assert p.quantidade_estoque == Decimal("0")


def test_limpa_espacos_de_nome_e_codigo(categoria):
    p = service.criar(dados(categoria, nome="  Leite   Integral  ", codigo="  ABC 1 "))
    assert p.nome == "Leite Integral"
    assert p.codigo == "ABC 1"


def test_aceita_preco_zero_e_estoque_minimo_fracionado(categoria):
    p = service.criar(dados(categoria, preco_custo="0", preco_venda="0", estoque_minimo="2,5"))
    assert p.preco_custo == Decimal("0.00")
    assert p.estoque_minimo == Decimal("2.500")


@pytest.mark.parametrize(
    "campo, valor, trecho",
    [
        ("nome", "", "Informe o nome"),
        ("nome", "   ", "Informe o nome"),
        ("nome", "A" * 121, "no máximo 120"),
        ("codigo", "", "Informe o código"),
        ("codigo", "9" * 51, "no máximo 50"),
        ("unidade_medida", "XX", "unidade de medida"),
        ("unidade_medida", "", "unidade de medida"),
        ("categoria_id", "", "Selecione uma categoria"),
        ("categoria_id", None, "Selecione uma categoria"),
        ("categoria_id", 999, "Categoria não encontrada"),
        ("preco_custo", "-1", "não pode ser negativo"),
        ("preco_venda", "-0,01", "não pode ser negativo"),
        ("estoque_minimo", "-2", "não pode ser negativo"),
        ("preco_custo", "4,505", "no máximo 2 casas"),
        ("estoque_minimo", "1,2345", "no máximo 3 casas"),
        ("preco_venda", "100000000", "grande demais"),
        ("preco_venda", "abc", "Valor inválido"),
        ("preco_venda", "NaN", "Valor inválido"),
        ("preco_venda", "", "Informe um valor"),
        ("estoque_minimo", "10000000", "grande demais"),
    ],
)
def test_dados_invalidos_sao_recusados_e_nada_e_gravado(categoria, campo, valor, trecho):
    with pytest.raises(ErroDeNegocio, match=trecho):
        service.criar(dados(categoria, **{campo: valor}))
    assert service.listar(incluir_inativos=True) == []


def test_nao_cadastra_em_categoria_inativa(categoria):  # RN10
    categoria_service.alternar_ativo(categoria.id)
    with pytest.raises(ErroDeNegocio, match="inativa"):
        service.criar(dados(categoria))


@pytest.mark.parametrize("repetido", ["ABC", "abc", " Abc "])
def test_codigo_duplicado_e_recusado_ignorando_caixa(categoria, repetido):  # RN02
    service.criar(dados(categoria, codigo="ABC"))
    with pytest.raises(ErroDeNegocio, match="Já existe um produto"):
        service.criar(dados(categoria, nome="Outro", codigo=repetido))
    assert len(service.listar()) == 1


# ---------- edição ----------
def test_edita_produto(categoria):
    p = service.criar(dados(categoria))
    service.editar(p.id, dados(categoria, nome="Leite Desnatado 1L", preco_venda="7,50"))
    atualizado = service.buscar(p.id)
    assert atualizado.nome == "Leite Desnatado 1L"
    assert atualizado.preco_venda == Decimal("7.50")


def test_edicao_nao_altera_o_saldo_de_estoque(categoria):  # RN12
    p = service.criar(dados(categoria))
    definir_estoque(p, "20")
    service.editar(p.id, dados(categoria, quantidade_estoque="0"))
    assert service.buscar(p.id).quantidade_estoque == Decimal("20")


def test_editar_mantendo_o_proprio_codigo_nao_e_duplicado(categoria):
    p = service.criar(dados(categoria, codigo="ABC"))
    service.editar(p.id, dados(categoria, codigo="abc", nome="Mudei só o nome"))
    assert service.buscar(p.id).codigo == "abc"


def test_editar_para_codigo_de_outro_produto_e_recusado(categoria):
    service.criar(dados(categoria, codigo="A1"))
    b = service.criar(dados(categoria, codigo="B2", nome="Outro"))
    with pytest.raises(ErroDeNegocio, match="Já existe um produto"):
        service.editar(b.id, dados(categoria, codigo="a1", nome="Outro"))
    assert service.buscar(b.id).codigo == "B2"


def test_edicao_invalida_nao_altera_o_produto(categoria):
    p = service.criar(dados(categoria))
    with pytest.raises(ErroDeNegocio):
        service.editar(p.id, dados(categoria, nome="Novo nome", preco_venda="-5"))
    assert service.buscar(p.id).nome == "Leite Integral 1L"


def test_produto_pode_continuar_em_categoria_que_foi_desativada(categoria):
    p = service.criar(dados(categoria))
    service.alternar_ativo(p.id)  # inativa o produto...
    categoria_service.alternar_ativo(categoria.id)  # ...e depois a categoria
    service.editar(p.id, dados(categoria, nome="Nome corrigido"))
    assert service.buscar(p.id).nome == "Nome corrigido"


def test_nao_move_produto_para_categoria_inativa(categoria):  # RN10
    p = service.criar(dados(categoria))
    outra = categoria_service.criar("Bebidas")
    categoria_service.alternar_ativo(outra.id)
    with pytest.raises(ErroDeNegocio, match="inativa"):
        service.editar(p.id, dados(outra))


def test_editar_produto_inexistente(app):
    with pytest.raises(ErroDeNegocio, match="não encontrado"):
        service.editar(999, {})


# ---------- unidade de medida (RN11) ----------
def test_muda_unidade_quando_nao_ha_estoque_nem_historico(categoria):
    p = service.criar(dados(categoria))
    service.editar(p.id, dados(categoria, unidade_medida="KG"))
    assert service.buscar(p.id).unidade_medida == "KG"


def test_nao_muda_unidade_com_estoque(categoria):
    p = service.criar(dados(categoria))
    definir_estoque(p, "3")
    with pytest.raises(ErroDeNegocio, match="unidade de medida"):
        service.editar(p.id, dados(categoria, unidade_medida="KG"))
    assert service.buscar(p.id).unidade_medida == "UN"


def test_nao_muda_unidade_com_historico_mesmo_com_saldo_zero(categoria):
    p = service.criar(dados(categoria))
    db.session.add(
        MovimentacaoEstoque(
            produto_id=p.id, tipo="ENTRADA", quantidade=Decimal("1"),
            saldo_anterior=Decimal("0"), saldo_posterior=Decimal("1"), motivo="Teste",
        )
    )
    db.session.commit()
    with pytest.raises(ErroDeNegocio, match="unidade de medida"):
        service.editar(p.id, dados(categoria, unidade_medida="KG"))


# ---------- ativar/desativar ----------
def test_desativa_e_reativa_produto(categoria):
    p = service.criar(dados(categoria))
    assert service.alternar_ativo(p.id).ativo is False
    assert service.alternar_ativo(p.id).ativo is True


def test_nao_reativa_produto_de_categoria_inativa(categoria):  # RN10
    p = service.criar(dados(categoria))
    service.alternar_ativo(p.id)
    categoria_service.alternar_ativo(categoria.id)
    with pytest.raises(ErroDeNegocio, match="Reative primeiro a categoria"):
        service.alternar_ativo(p.id)
    assert service.buscar(p.id).ativo is False


# ---------- avisos (RN13) ----------
def test_aviso_de_venda_abaixo_do_custo(categoria):
    p = service.criar(dados(categoria, preco_custo="5", preco_venda="4"))
    assert "abaixo do preço de custo" in service.avisos(p)


def test_aviso_de_preco_zerado(categoria):
    p = service.criar(dados(categoria, preco_venda="0"))
    assert "zerado" in service.avisos(p)


def test_sem_aviso_quando_o_preco_e_normal(categoria):
    assert service.avisos(service.criar(dados(categoria))) is None


# ---------- listagem e busca ----------
def test_busca_por_nome_ou_codigo_ignorando_caixa(categoria):
    service.criar(dados(categoria, nome="Café Torrado 500g", codigo="789001"))
    service.criar(dados(categoria, nome="Açúcar 1kg", codigo="789002"))

    assert [p.nome for p in service.listar("CAFÉ")] == ["Café Torrado 500g"]
    assert [p.nome for p in service.listar("789002")] == ["Açúcar 1kg"]
    assert len(service.listar("7890")) == 2
    assert service.listar("zzz") == []


def test_listagem_ordenada_oculta_inativos_e_filtra_por_categoria(categoria):
    bebidas = categoria_service.criar("Bebidas")
    service.criar(dados(categoria, nome="Queijo", codigo="1"))
    service.criar(dados(categoria, nome="Leite", codigo="2"))
    suco = service.criar(dados(bebidas, nome="Suco", codigo="3"))
    service.alternar_ativo(suco.id)

    assert [p.nome for p in service.listar()] == ["Leite", "Queijo"]
    assert [p.nome for p in service.listar(incluir_inativos=True)] == ["Leite", "Queijo", "Suco"]
    assert [p.nome for p in service.listar(categoria_id=bebidas.id, incluir_inativos=True)] == ["Suco"]


def test_filtro_de_estoque_baixo(categoria):  # RN07
    ok = service.criar(dados(categoria, nome="Ok", codigo="1", estoque_minimo="5"))
    no_limite = service.criar(dados(categoria, nome="Limite", codigo="2", estoque_minimo="5"))
    baixo = service.criar(dados(categoria, nome="Baixo", codigo="3", estoque_minimo="5"))
    definir_estoque(ok, "6")
    definir_estoque(no_limite, "5")
    definir_estoque(baixo, "1")

    assert [p.nome for p in service.listar(apenas_estoque_baixo=True)] == ["Baixo", "Limite"]


# ---------- busca exata por código (usada pelo PDV) ----------
def test_busca_ativa_por_codigo_exato_ignorando_caixa_e_espacos(categoria):
    p = service.criar(dados(categoria, codigo="ABC123"))
    assert service.buscar_ativo_por_codigo("abc123").id == p.id
    assert service.buscar_ativo_por_codigo("  ABC123 ").id == p.id


def test_busca_por_codigo_nao_aceita_codigo_parcial_nem_parecido(categoria):
    service.criar(dados(categoria, codigo="ABC12", nome="Curto"))
    longo = service.criar(dados(categoria, codigo="ABC123", nome="Longo"))
    assert service.buscar_ativo_por_codigo("ABC123").id == longo.id
    with pytest.raises(ErroDeNegocio, match="Nenhum produto ativo"):
        service.buscar_ativo_por_codigo("ABC1")


def test_busca_por_codigo_ignora_produto_inativo(categoria):
    p = service.criar(dados(categoria, codigo="ABC123"))
    service.alternar_ativo(p.id)
    with pytest.raises(ErroDeNegocio, match="Nenhum produto ativo"):
        service.buscar_ativo_por_codigo("ABC123")


@pytest.mark.parametrize("codigo", ["", "   ", None])
def test_busca_por_codigo_vazio(categoria, codigo):
    with pytest.raises(ErroDeNegocio, match="Informe o código"):
        service.buscar_ativo_por_codigo(codigo)
