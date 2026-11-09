"""Testes das regras de Fornecedor (RN31, RN32)."""
import pytest

from app.models import Fornecedor
from app.services import fornecedor_service as svc
from app.utils.erros import ErroDeNegocio


def test_cria_fornecedor_normalizando_dados(app):
    f = svc.criar("  Distribuidora   Bom Preço ", "12.345.678/0001-90", " (11) 98765-4321 ", " João ")
    assert f.nome == "Distribuidora Bom Preço"
    assert f.documento == "12345678000190"
    assert f.telefone == "(11) 98765-4321"
    assert f.contato == "João"
    assert f.ativo is True


def test_campos_opcionais_vazios_viram_none(app):
    f = svc.criar("Padaria Central", "", "  ", "")
    assert (f.documento, f.telefone, f.contato) == (None, None, None)


def test_dois_fornecedores_sem_documento_sao_permitidos(app):
    svc.criar("A")
    svc.criar("B")
    assert len(svc.listar()) == 2


@pytest.mark.parametrize("nome", ["", "   ", None, "x" * 121])
def test_nome_invalido(app, nome):
    with pytest.raises(ErroDeNegocio):
        svc.criar(nome)


def test_nome_duplicado_sem_diferenciar_caixa(app):
    svc.criar("Hortifrúti Silva")
    with pytest.raises(ErroDeNegocio, match="Já existe"):
        svc.criar("HORTIFRÚTI  silva")


@pytest.mark.parametrize(
    "documento", ["123", "1234567890", "123456789012", "abc45678901", "123456789012345"]
)
def test_documento_invalido(app, documento):
    with pytest.raises(ErroDeNegocio):
        svc.criar("X", documento)


def test_aceita_cpf_e_documento_duplicado_e_recusado(app):
    svc.criar("A", "123.456.789-01")
    with pytest.raises(ErroDeNegocio, match="CPF/CNPJ"):
        svc.criar("B", "12345678901")


@pytest.mark.parametrize("telefone", ["abc", "123", "12345678a", "1" * 21])
def test_telefone_invalido(app, telefone):
    with pytest.raises(ErroDeNegocio):
        svc.criar("X", telefone=telefone)


def test_contato_longo_demais(app):
    with pytest.raises(ErroDeNegocio):
        svc.criar("X", contato="c" * 81)


def test_editar_mantem_proprio_nome_e_documento(app):
    f = svc.criar("A", "12345678901")
    svc.editar(f.id, "A", "123.456.789-01", "(11) 3333-4444", "Maria")
    assert svc.buscar(f.id).contato == "Maria"


def test_editar_nao_pode_usar_nome_de_outro(app):
    svc.criar("A")
    b = svc.criar("B")
    with pytest.raises(ErroDeNegocio):
        svc.editar(b.id, "a")


def test_editar_nao_pode_usar_documento_de_outro(app):
    svc.criar("A", "12345678901")
    b = svc.criar("B")
    with pytest.raises(ErroDeNegocio):
        svc.editar(b.id, "B", "12345678901")


def test_editar_inexistente(app):
    with pytest.raises(ErroDeNegocio, match="não encontrado"):
        svc.editar(999, "X")


def test_alternar_ativo_e_listagem(app):
    f = svc.criar("A")
    assert svc.alternar_ativo(f.id).ativo is False
    assert svc.listar() == []
    assert len(svc.listar(incluir_inativos=True)) == 1
    assert svc.alternar_ativo(f.id).ativo is True


def test_busca_por_nome_contato_e_documento(app):
    svc.criar("Bom Preço", "12.345.678/0001-90", contato="João")
    svc.criar("Padaria", contato="Ana")
    assert [f.nome for f in svc.listar("bom")] == ["Bom Preço"]
    assert [f.nome for f in svc.listar("ana")] == ["Padaria"]
    assert [f.nome for f in svc.listar("0001-90")] == ["Bom Preço"]
    assert svc.listar("zzz") == []


def test_busca_com_texto_sem_digitos_nao_casa_tudo_pelo_documento(app):
    svc.criar("A", "12345678901")
    assert svc.listar("xyz") == []


def test_banco_barra_nome_duplicado_mesmo_sem_service(app):
    from app.extensions import db
    from sqlalchemy.exc import IntegrityError

    svc.criar("A")
    db.session.add(Fornecedor(nome="A"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
