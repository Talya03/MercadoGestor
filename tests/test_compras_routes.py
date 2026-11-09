"""Testes das telas de Fornecedores e Compras (requisições HTTP simuladas)."""
import re
import uuid
from decimal import Decimal
from itertools import count

import pytest

from app import create_app
from app.extensions import db
from app.models import Compra, Fornecedor, Produto
from app.services import categoria_service, fornecedor_service, produto_service
from config import TestConfig

_n = count(1)


def html(r):
    return r.get_data(as_text=True)


@pytest.fixture
def fornecedor(app):
    return fornecedor_service.criar("Distribuidora Bom Preço", "12345678000190")


@pytest.fixture
def leite(app):
    cat = categoria_service.criar("Laticínios")
    return produto_service.criar(
        {
            "categoria_id": cat.id, "nome": "Leite integral 1L", "codigo": f"L{next(_n)}",
            "unidade_medida": "UN", "preco_custo": "4,50", "preco_venda": "6,99", "estoque_minimo": "5",
        }
    )


def dados_compra(fornecedor, produto, **extras):
    dados = {
        "token": str(uuid.uuid4()),
        "fornecedor_id": str(fornecedor.id),
        "numero_documento": "NF 1",
        "observacao": "",
        "produto_id": [str(produto.id)],
        "quantidade": ["24"],
        "custo_unitario": ["4,80"],
    }
    dados.update(extras)
    return dados


# --------------------------------------------------------------- fornecedores
def test_paginas_de_fornecedor_abrem(client, fornecedor):
    assert fornecedor.nome in html(client.get("/fornecedores/"))
    assert client.get("/fornecedores/novo").status_code == 200
    assert client.get(f"/fornecedores/{fornecedor.id}/editar").status_code == 200


def test_cria_fornecedor_pela_tela(client):
    r = client.post(
        "/fornecedores/novo",
        data={"nome": "Padaria Central", "documento": "", "telefone": "(11) 3333-4444", "contato": "Ana"},
        follow_redirects=True,
    )
    assert "Fornecedor cadastrado com sucesso" in html(r)
    assert "Padaria Central" in html(r)


def test_nome_vazio_mostra_erro_e_nao_grava(client, app):
    r = client.post("/fornecedores/novo", data={"nome": ""})
    assert "Informe o nome do fornecedor" in html(r)
    assert db.session.query(Fornecedor).count() == 0


def test_erro_de_negocio_aparece_na_tela(client, fornecedor):
    r = client.post("/fornecedores/novo", data={"nome": "x", "documento": "123"})
    assert "11 dígitos" in html(r)
    r = client.post("/fornecedores/novo", data={"nome": fornecedor.nome.upper()})
    assert "Já existe um fornecedor" in html(r)


def test_editar_fornecedor_e_inexistente(client, fornecedor):
    r = client.post(f"/fornecedores/{fornecedor.id}/editar", data={"nome": "Novo Nome"}, follow_redirects=True)
    assert "atualizado com sucesso" in html(r)
    r = client.get("/fornecedores/999/editar", follow_redirects=True)
    assert "Fornecedor não encontrado" in html(r)


def test_alternar_so_aceita_post_e_funciona(client, fornecedor):
    assert client.get(f"/fornecedores/{fornecedor.id}/alternar").status_code == 405
    r = client.post(f"/fornecedores/{fornecedor.id}/alternar", follow_redirects=True)
    assert "desativado com sucesso" in html(r)
    assert fornecedor.nome not in html(client.get("/fornecedores/"))
    assert fornecedor.nome in html(client.get("/fornecedores/?inativos=1"))
    r = client.post("/fornecedores/999/alternar", follow_redirects=True)
    assert "não encontrado" in html(r)


def test_nome_com_html_e_escapado(client, app):
    fornecedor_service.criar('<script>alert("x")</script>')
    corpo = html(client.get("/fornecedores/"))
    assert "<script>alert" not in corpo
    assert "&lt;script&gt;" in corpo


# -------------------------------------------------------------------- compras
def test_paginas_de_compra_abrem(client, fornecedor, leite):
    assert client.get("/compras/").status_code == 200
    r = client.get(f"/compras/nova?fornecedor={fornecedor.id}")
    assert r.status_code == 200
    assert re.search(rf'<option value="{fornecedor.id}"\s+selected', html(r))
    assert 'name="token"' in html(r)


def test_nova_compra_sem_fornecedor_ou_produto_orienta(client, app):
    assert "Cadastre um fornecedor" in html(client.get("/compras/nova"))
    fornecedor_service.criar("A")
    assert "Cadastre um produto" in html(client.get("/compras/nova"))


def test_registra_compra_pela_tela(client, fornecedor, leite):
    r = client.post("/compras/nova", data=dados_compra(fornecedor, leite), follow_redirects=True)
    corpo = html(r)
    assert "registrada. O estoque foi atualizado" in corpo
    assert "R$ 115,20" in corpo
    db.session.refresh(leite)
    assert leite.quantidade_estoque == Decimal("24")
    assert leite.preco_custo == Decimal("4.80")
    assert "Preço de venda abaixo do custo" not in corpo


def test_aviso_quando_custo_passa_do_preco_de_venda(client, fornecedor, leite):
    r = client.post(
        "/compras/nova", data=dados_compra(fornecedor, leite, custo_unitario=["7,50"]),
        follow_redirects=True,
    )
    assert "Preço de venda abaixo do custo" in html(r)


def test_linhas_totalmente_vazias_sao_ignoradas(client, fornecedor, leite):
    dados = dados_compra(
        fornecedor, leite,
        produto_id=["", str(leite.id), ""], quantidade=["", "2", ""], custo_unitario=["", "3", ""],
    )
    client.post("/compras/nova", data=dados, follow_redirects=True)
    compra = db.session.query(Compra).one()
    assert len(compra.itens) == 1 and compra.total == Decimal("6.00")


def test_linha_incompleta_e_erro(client, fornecedor, leite):
    dados = dados_compra(fornecedor, leite, custo_unitario=[""])
    r = client.post("/compras/nova", data=dados)
    assert "custo unitário" in html(r)
    assert db.session.query(Compra).count() == 0


def test_erro_reexibe_o_que_foi_digitado_com_o_mesmo_token(client, fornecedor, leite):
    dados = dados_compra(fornecedor, leite, quantidade=["0"], observacao="entrega de terça")
    r = client.post("/compras/nova", data=dados)
    corpo = html(r)
    assert "maior que zero" in corpo
    assert f'value="{dados["token"]}"' in corpo
    assert "entrega de terça" in corpo
    assert 'value="NF 1"' in corpo
    assert re.search(rf'<option value="{leite.id}"\s+selected', corpo)


def test_sem_itens_e_sem_fornecedor(client, fornecedor, leite):
    r = client.post("/compras/nova", data={"token": str(uuid.uuid4()), "fornecedor_id": str(fornecedor.id)})
    assert "ao menos um item" in html(r)
    r = client.post("/compras/nova", data=dados_compra(fornecedor, leite, fornecedor_id=""))
    assert "Selecione o fornecedor" in html(r)
    r = client.post("/compras/nova", data=dados_compra(fornecedor, leite, fornecedor_id="abc"))
    assert "Selecione o fornecedor" in html(r)


def test_reenvio_do_mesmo_formulario_leva_a_mesma_compra(client, fornecedor, leite):
    dados = dados_compra(fornecedor, leite)
    client.post("/compras/nova", data=dados)
    r = client.post("/compras/nova", data=dados, follow_redirects=True)
    assert "já havia sido registrada" in html(r)
    assert db.session.query(Compra).count() == 1
    db.session.refresh(leite)
    assert leite.quantidade_estoque == Decimal("24")


def test_token_invalido_nao_quebra(client, fornecedor, leite):
    r = client.post("/compras/nova", data=dados_compra(fornecedor, leite, token="lixo"), follow_redirects=True)
    assert "registrada" in html(r)
    assert db.session.query(Compra).one().token_envio is None


def test_detalhe_lista_e_filtros(client, fornecedor, leite):
    client.post("/compras/nova", data=dados_compra(fornecedor, leite))
    compra = db.session.query(Compra).one()
    assert "Compra #" in html(client.get(f"/compras/{compra.id}"))
    assert "não encontrada" in html(client.get("/compras/999", follow_redirects=True))
    corpo = html(client.get(f"/compras/?fornecedor={fornecedor.id}"))
    assert "R$ 115,20" in corpo
    assert "Nenhuma compra" in html(client.get("/compras/?fornecedor=999"))
    assert "Nenhuma compra" in html(client.get("/compras/?de=2000-01-01&ate=2000-01-02"))
    assert "data inicial" in html(client.get("/compras/?de=2000-01-05&ate=2000-01-02"))
    assert client.get("/compras/?de=lixo&fornecedor=abc").status_code == 200


def test_get_nunca_cria_compra(client, fornecedor, leite):
    client.get(f"/compras/nova?fornecedor={fornecedor.id}&produto_id={leite.id}&quantidade=5")
    assert db.session.query(Compra).count() == 0


def test_nome_de_produto_com_html_e_escapado_no_formulario(client, fornecedor, app):
    cat = categoria_service.criar("X")
    produto_service.criar(
        {"categoria_id": cat.id, "nome": "<b>Xss</b>", "codigo": "XSS1", "unidade_medida": "UN",
         "preco_custo": "1", "preco_venda": "2", "estoque_minimo": "0"}
    )
    corpo = html(client.get("/compras/nova"))
    assert "<b>Xss</b>" not in corpo and "&lt;b&gt;Xss&lt;/b&gt;" in corpo


# ----------------------------------------------------------------------- CSRF
@pytest.fixture
def client_csrf(app):
    class Cfg(TestConfig):
        WTF_CSRF_ENABLED = True

    app2 = create_app(Cfg)
    with app2.app_context():
        db.create_all()
        yield app2.test_client()
        db.session.remove()
        db.drop_all()


def test_post_sem_csrf_e_recusado(client_csrf):
    for url in ("/compras/nova", "/fornecedores/novo", "/fornecedores/1/alternar"):
        assert client_csrf.post(url, data={}).status_code == 400


def test_fluxo_completo_com_csrf_ligado(client_csrf):
    f = fornecedor_service.criar("Bom Preço")
    cat = categoria_service.criar("Bebidas")
    p = produto_service.criar(
        {"categoria_id": cat.id, "nome": "Suco", "codigo": "S1", "unidade_medida": "UN",
         "preco_custo": "2", "preco_venda": "4", "estoque_minimo": "1"}
    )
    pagina = html(client_csrf.get("/compras/nova"))
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', pagina).group(1)
    token = re.search(r'name="token" value="([^"]+)"', pagina).group(1)
    r = client_csrf.post(
        "/compras/nova",
        data={"csrf_token": csrf, "token": token, "fornecedor_id": str(f.id),
              "produto_id": [str(p.id)], "quantidade": ["3"], "custo_unitario": ["2,50"]},
        follow_redirects=True,
    )
    assert "registrada" in html(r)
    db.session.refresh(p)
    assert p.quantidade_estoque == Decimal("3")
