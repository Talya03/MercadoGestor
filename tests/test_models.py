"""Testes dos modelos: Categoria, Produto e MovimentacaoEstoque.

Padrão de cada teste (AAA): Arrange (preparar), Act (agir), Assert (conferir).
Casos de erro usam pytest.raises(IntegrityError): o banco recusou o dado.
"""
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Categoria, MovimentacaoEstoque, Produto


# ---------- helpers ----------
def criar_categoria(nome="Laticínios"):
    categoria = Categoria(nome=nome)
    db.session.add(categoria)
    db.session.commit()
    return categoria


def criar_produto(categoria, **extras):
    dados = dict(
        categoria_id=categoria.id,
        nome="Leite Integral 1L",
        codigo="7891000100103",
        unidade_medida="UN",
        preco_custo=Decimal("4.50"),
        preco_venda=Decimal("6.99"),
        quantidade_estoque=Decimal("20"),
        estoque_minimo=Decimal("5"),
    )
    dados.update(extras)
    produto = Produto(**dados)
    db.session.add(produto)
    db.session.commit()
    return produto


# ---------- Categoria ----------
def test_cadastra_categoria_com_valores_padrao(app):
    categoria = criar_categoria("Bebidas")
    assert categoria.id is not None
    assert categoria.ativo is True


def test_nome_de_categoria_deve_ser_unico(app):
    criar_categoria("Bebidas")
    db.session.add(Categoria(nome="Bebidas"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_categoria_sem_nome_e_recusada(app):
    db.session.add(Categoria(nome=None))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


# ---------- Produto ----------
def test_cadastra_produto_e_relaciona_com_categoria(app):
    categoria = criar_categoria()
    produto = criar_produto(categoria)

    assert produto.id is not None
    assert produto.categoria.nome == "Laticínios"
    assert produto in categoria.produtos
    assert produto.ativo is True
    assert produto.criado_em is not None


def test_codigo_de_produto_deve_ser_unico(app):
    categoria = criar_categoria()
    criar_produto(categoria, codigo="123")
    with pytest.raises(IntegrityError):
        criar_produto(categoria, codigo="123", nome="Outro produto")
    db.session.rollback()


@pytest.mark.parametrize(
    "campo",
    ["preco_custo", "preco_venda", "quantidade_estoque", "estoque_minimo"],
)
def test_valores_negativos_em_produto_sao_recusados(app, campo):
    categoria = criar_categoria()
    with pytest.raises(IntegrityError):
        criar_produto(categoria, **{campo: Decimal("-1")})
    db.session.rollback()


def test_produto_com_categoria_inexistente_e_recusado(app):
    # Prova que as chaves estrangeiras estão ativas no SQLite.
    produto = Produto(categoria_id=999, nome="Fantasma", codigo="000")
    db.session.add(produto)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_estoque_baixo_quando_saldo_igual_ou_menor_que_minimo(app):
    categoria = criar_categoria()
    ok = criar_produto(categoria, codigo="A", quantidade_estoque=Decimal("6"))
    no_limite = criar_produto(categoria, codigo="B", quantidade_estoque=Decimal("5"))
    abaixo = criar_produto(categoria, codigo="C", quantidade_estoque=Decimal("2"))

    assert ok.estoque_baixo is False
    assert no_limite.estoque_baixo is True  # RN07: igual ao mínimo já alerta
    assert abaixo.estoque_baixo is True


def test_produto_aceita_quantidade_fracionada_para_venda_por_peso(app):
    categoria = criar_categoria("Hortifrúti")
    tomate = criar_produto(
        categoria, codigo="TOM", nome="Tomate", unidade_medida="KG",
        quantidade_estoque=Decimal("12.350"),
    )
    assert tomate.quantidade_estoque == Decimal("12.350")


# ---------- MovimentacaoEstoque ----------
def criar_movimentacao(produto, **extras):
    dados = dict(
        produto_id=produto.id,
        tipo="ENTRADA",
        quantidade=Decimal("10"),
        saldo_anterior=Decimal("20"),
        saldo_posterior=Decimal("30"),
        motivo="Compra",
    )
    dados.update(extras)
    mov = MovimentacaoEstoque(**dados)
    db.session.add(mov)
    db.session.commit()
    return mov


def test_registra_movimentacao_ligada_ao_produto(app):
    produto = criar_produto(criar_categoria())
    mov = criar_movimentacao(produto)

    assert mov.id is not None
    assert mov.data_hora is not None
    assert mov.produto.codigo == produto.codigo
    assert mov in produto.movimentacoes


def test_tipo_de_movimentacao_invalido_e_recusado(app):
    produto = criar_produto(criar_categoria())
    with pytest.raises(IntegrityError):
        criar_movimentacao(produto, tipo="ROUBO")
    db.session.rollback()


@pytest.mark.parametrize("quantidade", [Decimal("0"), Decimal("-3")])
def test_quantidade_da_movimentacao_deve_ser_positiva(app, quantidade):
    produto = criar_produto(criar_categoria())
    with pytest.raises(IntegrityError):
        criar_movimentacao(produto, quantidade=quantidade)
    db.session.rollback()


def test_saldo_posterior_negativo_e_recusado(app):
    # RN04/RN06: uma saída maior que o saldo não pode ser registrada.
    produto = criar_produto(criar_categoria())
    with pytest.raises(IntegrityError):
        criar_movimentacao(
            produto, tipo="SAIDA", quantidade=Decimal("25"),
            saldo_anterior=Decimal("20"), saldo_posterior=Decimal("-5"),
        )
    db.session.rollback()


def test_movimentacao_sem_motivo_e_recusada(app):
    produto = criar_produto(criar_categoria())
    with pytest.raises(IntegrityError):
        criar_movimentacao(produto, motivo=None)
    db.session.rollback()
