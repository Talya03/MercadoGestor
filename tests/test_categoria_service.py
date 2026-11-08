"""Testes das regras de negócio de categoria (sem passar pelo navegador)."""
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Categoria, Produto
from app.services import categoria_service as service
from app.utils.erros import ErroDeNegocio


def test_cria_categoria_e_limpa_espacos_do_nome(app):
    categoria = service.criar("   Hortifrúti   de   Bairro  ", "  Frutas e verduras ")
    assert categoria.id is not None
    assert categoria.nome == "Hortifrúti de Bairro"
    assert categoria.descricao == "Frutas e verduras"
    assert categoria.ativo is True


def test_descricao_vazia_vira_nula(app):
    assert service.criar("Bebidas", "   ").descricao is None


@pytest.mark.parametrize("nome", ["", "   ", None])
def test_nome_vazio_e_recusado(app, nome):
    with pytest.raises(ErroDeNegocio, match="Informe o nome"):
        service.criar(nome)


def test_nome_acima_do_limite_e_recusado(app):
    with pytest.raises(ErroDeNegocio, match="no máximo 80"):
        service.criar("A" * 81)


def test_descricao_acima_do_limite_e_recusada(app):
    with pytest.raises(ErroDeNegocio, match="no máximo 255"):
        service.criar("Bebidas", "x" * 256)


@pytest.mark.parametrize("repetido", ["Laticínios", "laticínios", "LATICÍNIOS", " Laticínios "])
def test_nome_duplicado_e_recusado_ignorando_caixa_e_espacos(app, repetido):
    service.criar("Laticínios")
    with pytest.raises(ErroDeNegocio, match="Já existe"):
        service.criar(repetido)
    assert db.session.query(Categoria).count() == 1


def test_edita_categoria(app):
    categoria = service.criar("Bebidas")
    service.editar(categoria.id, "Bebidas e Sucos", "Água, refrigerante")
    atualizada = service.buscar(categoria.id)
    assert atualizada.nome == "Bebidas e Sucos"
    assert atualizada.descricao == "Água, refrigerante"


def test_edita_mantendo_o_proprio_nome_nao_conta_como_duplicado(app):
    categoria = service.criar("Bebidas")
    service.editar(categoria.id, "bebidas", "Só mudei a caixa")
    assert service.buscar(categoria.id).nome == "bebidas"


def test_edita_para_nome_de_outra_categoria_e_recusado(app):
    service.criar("Bebidas")
    outra = service.criar("Limpeza")
    with pytest.raises(ErroDeNegocio, match="Já existe"):
        service.editar(outra.id, "BEBIDAS")
    assert service.buscar(outra.id).nome == "Limpeza"


def test_buscar_categoria_inexistente_da_erro_de_negocio(app):
    with pytest.raises(ErroDeNegocio, match="não encontrada"):
        service.buscar(999)


def test_desativa_e_reativa_categoria(app):
    categoria = service.criar("Bebidas")
    assert service.alternar_ativo(categoria.id).ativo is False
    assert service.alternar_ativo(categoria.id).ativo is True


def _produto(categoria, codigo, ativo=True):
    produto = Produto(
        categoria_id=categoria.id, nome=f"Produto {codigo}", codigo=codigo,
        preco_custo=Decimal("1"), preco_venda=Decimal("2"), ativo=ativo,
    )
    db.session.add(produto)
    db.session.commit()
    return produto


def test_nao_desativa_categoria_com_produto_ativo(app):  # RN09
    categoria = service.criar("Bebidas")
    _produto(categoria, "A1", ativo=True)
    with pytest.raises(ErroDeNegocio, match="produtos ativos"):
        service.alternar_ativo(categoria.id)
    assert service.buscar(categoria.id).ativo is True


def test_desativa_categoria_cujos_produtos_estao_todos_inativos(app):
    categoria = service.criar("Bebidas")
    _produto(categoria, "A1", ativo=False)
    assert service.alternar_ativo(categoria.id).ativo is False


def test_listagem_oculta_inativas_por_padrao_e_ordena_por_nome(app):
    service.criar("Limpeza")
    service.criar("Bebidas")
    velha = service.criar("Antigos")
    service.alternar_ativo(velha.id)

    assert [c.nome for c in service.listar()] == ["Bebidas", "Limpeza"]
    assert [c.nome for c in service.listar(incluir_inativas=True)] == [
        "Antigos", "Bebidas", "Limpeza",
    ]


def test_busca_ignora_caixa_e_funciona_no_meio_do_nome(app):
    service.criar("Laticínios")
    service.criar("Limpeza")
    assert [c.nome for c in service.listar("LATIC")] == ["Laticínios"]
    assert [c.nome for c in service.listar("lim")] == ["Limpeza"]
    assert service.listar("xyz") == []
