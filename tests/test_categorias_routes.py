"""Testes das telas de categoria (requisições HTTP simuladas)."""
import pytest

from app import create_app
from app.extensions import db
from app.services import categoria_service as service
from tests.conftest import entrar
from config import TestConfig


def _html(resposta):
    return resposta.get_data(as_text=True)


def test_lista_vazia_mostra_orientacao(client):
    resposta = client.get("/categorias/")
    assert resposta.status_code == 200
    assert "Nenhuma categoria cadastrada" in _html(resposta)


def test_formulario_de_nova_categoria_abre(client):
    resposta = client.get("/categorias/nova")
    assert resposta.status_code == 200
    assert "Nova categoria" in _html(resposta)


def test_cadastra_categoria_pela_tela(client):
    resposta = client.post(
        "/categorias/nova",
        data={"nome": "Bebidas", "descricao": "Água e sucos"},
        follow_redirects=True,
    )
    html = _html(resposta)
    assert "Categoria cadastrada com sucesso." in html
    assert "Bebidas" in html


def test_cadastro_com_nome_vazio_mostra_erro_e_nao_grava(client):
    resposta = client.post("/categorias/nova", data={"nome": "", "descricao": ""})
    assert resposta.status_code == 200
    assert "Informe o nome da categoria." in _html(resposta)
    assert service.listar() == []


def test_cadastro_duplicado_mostra_erro(client):
    client.post("/categorias/nova", data={"nome": "Bebidas"})
    resposta = client.post("/categorias/nova", data={"nome": "bebidas"})
    assert "Já existe uma categoria" in _html(resposta)
    assert len(service.listar()) == 1


def test_edita_categoria_pela_tela(client):
    categoria = service.criar("Bebidas")
    resposta = client.post(
        f"/categorias/{categoria.id}/editar",
        data={"nome": "Bebidas Geladas", "descricao": ""},
        follow_redirects=True,
    )
    html = _html(resposta)
    assert "Categoria atualizada com sucesso." in html
    assert "Bebidas Geladas" in html


def test_edicao_exibe_dados_atuais_no_formulario(client):
    categoria = service.criar("Bebidas", "Água e sucos")
    html = _html(client.get(f"/categorias/{categoria.id}/editar"))
    assert 'value="Bebidas"' in html
    assert 'value="Água e sucos"' in html


def test_editar_categoria_inexistente_volta_para_lista_com_aviso(client):
    resposta = client.get("/categorias/999/editar", follow_redirects=True)
    assert "Categoria não encontrada." in _html(resposta)


def test_desativa_pela_tela_e_so_aparece_com_filtro(client):
    categoria = service.criar("Bebidas")
    resposta = client.post(f"/categorias/{categoria.id}/alternar", follow_redirects=True)
    assert "Categoria desativada com sucesso." in _html(resposta)

    assert "Nenhuma categoria cadastrada" in _html(client.get("/categorias/"))
    com_inativas = _html(client.get("/categorias/?inativas=1"))
    assert "Bebidas" in com_inativas
    assert "Inativa" in com_inativas


def test_alternar_nao_aceita_get(client):
    categoria = service.criar("Bebidas")
    assert client.get(f"/categorias/{categoria.id}/alternar").status_code == 405


def test_busca_filtra_a_lista(client):
    service.criar("Laticínios")
    service.criar("Limpeza")
    html = _html(client.get("/categorias/?q=latic"))
    assert "Laticínios" in html
    assert "Limpeza" not in html


def test_busca_sem_resultado_mostra_mensagem(client):
    service.criar("Limpeza")
    assert "Nenhuma categoria encontrada" in _html(client.get("/categorias/?q=zzz"))


def test_nome_com_html_e_escapado_na_tela(client):
    # Proteção contra XSS: o Jinja escapa o conteúdo, o script não executa.
    service.criar("<script>alert(1)</script>")
    html = _html(client.get("/categorias/"))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ---------- CSRF ----------
class _ConfigComCsrf(TestConfig):
    WTF_CSRF_ENABLED = True


@pytest.fixture
def client_com_csrf():
    app = create_app(_ConfigComCsrf)
    with app.app_context():
        db.create_all()
        cliente = app.test_client()
        entrar(cliente)  # logado: o CSRF precisa funcionar também para quem já entrou
        yield cliente
        db.session.remove()
        db.drop_all()


def test_post_sem_token_csrf_e_bloqueado(client_com_csrf):
    resposta = client_com_csrf.post("/categorias/nova", data={"nome": "Bebidas"})
    assert resposta.status_code == 400
    assert service.listar() == []
