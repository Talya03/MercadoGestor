"""v0.14 — telas de precificação."""
import re
from decimal import Decimal as D
from itertools import count

import pytest

from app import create_app
from app.extensions import db
from app.models import Produto
from app.services import categoria_service, produto_service
from config import TestConfig
from tests.conftest import entrar

_n = count(1)


def html(r):
    return r.get_data(as_text=True)


def novo(nome="Arroz 5kg", custo="7,00", venda="8,00"):
    cat = categoria_service.listar()[0] if categoria_service.listar() else categoria_service.criar("Mercearia")
    return produto_service.criar({"categoria_id": cat.id, "nome": nome, "codigo": f"R{next(_n)}",
                                  "unidade_medida": "UN", "preco_custo": custo, "preco_venda": venda,
                                  "estoque_minimo": "1"})


def preco(p):
    db.session.expire_all()
    return db.session.get(Produto, p.id).preco_venda


def test_tela_mostra_conta_e_situacao(client):
    novo(custo="7,00", venda="8,00")
    corpo = html(client.get("/precificacao/"))
    assert "R$ 10,00" in corpo and "Abaixo da meta" in corpo
    assert "12,50%" in corpo            # margem atual: (8-7)/8
    assert "+14,29%" in corpo           # markup atual: 1/7


def test_simular_nao_grava(client):
    p = novo()
    client.get("/precificacao/?margem=50&despesas=5")
    assert preco(p) == D("8.00")


def test_parametros_pela_url_mudam_o_sugerido(client):
    novo(custo="10,00", venda="1,00")
    assert "R$ 13,34" in html(client.get("/precificacao/?margem=20&despesas=5"))


def test_parametros_invalidos_voltam_ao_padrao_com_aviso(client):
    novo(custo="7,00", venda="8,00")
    corpo = html(client.get("/precificacao/?margem=60&despesas=40"))
    assert "menores que 100%" in corpo and "R$ 10,00" in corpo  # padrão 30% -> 10,00
    assert "grande demais" in html(client.get("/precificacao/?margem=100"))
    assert "Valor inválido" in html(client.get("/precificacao/?margem=abc"))


def test_filtros_busca_categoria_e_abaixo(client):
    novo("Arroz", custo="7", venda="8")
    novo("Feijão", custo="5", venda="20")
    assert "Feijão" not in html(client.get("/precificacao/?q=arroz"))
    corpo = html(client.get("/precificacao/?abaixo=1"))
    assert "Arroz" in corpo and "Feijão" not in corpo


def test_aplicar_muda_preco_mostra_mensagem_e_mantem_filtros(client):
    p = novo(custo="7,00", venda="8,00")
    r = client.post(f"/precificacao/{p.id}/aplicar", data={"margem": "30", "despesas": "0", "q": "arroz"})
    assert r.status_code == 302 and "q=arroz" in r.headers["Location"]
    assert preco(p) == D("10.00")
    corpo = html(client.get(r.headers["Location"]))
    assert 'alterado de R$ 8,00 para R$ 10,00' in corpo


def test_preco_enviado_pelo_formulario_e_ignorado(client):  # RN80
    p = novo(custo="7,00", venda="8,00")
    client.post(f"/precificacao/{p.id}/aplicar",
                data={"margem": "30", "despesas": "0", "preco_venda": "0,01", "sugerido": "0,01", "preco": "0,01"})
    assert preco(p) == D("10.00")


def test_aplicar_com_erro_nao_grava_e_avisa(client):
    p = novo(custo="7,00", venda="8,00")
    r = client.post(f"/precificacao/{p.id}/aplicar", data={"margem": "60", "despesas": "40"}, follow_redirects=True)
    assert "menores que 100%" in html(r) and preco(p) == D("8.00")
    r = client.post(f"/precificacao/{p.id}/aplicar", data={"margem": "abc", "despesas": "0"}, follow_redirects=True)
    assert "Valor inválido" in html(r) and preco(p) == D("8.00")
    sem_custo = novo("Sem custo", custo="0", venda="3,00")
    r = client.post(f"/precificacao/{sem_custo.id}/aplicar", data={"margem": "30", "despesas": "0"}, follow_redirects=True)
    assert "sem preço de custo" in html(r) and preco(sem_custo) == D("3.00")
    assert "não encontrado" in html(client.post("/precificacao/9999/aplicar", data={"margem": "30", "despesas": "0"}, follow_redirects=True)).lower()


def test_aplicar_so_aceita_post(client):
    p = novo()
    assert client.get(f"/precificacao/{p.id}/aplicar").status_code == 405


def test_botao_aplicar_so_quando_ha_diferenca(client):
    novo("Já no preço", custo="7,00", venda="10,00")
    novo("Para ajustar", custo="7,00", venda="8,00")
    corpo = html(client.get("/precificacao/"))
    assert corpo.count(">Aplicar</button>") == 1


def test_valores_do_formulario_sao_escapados(client):
    corpo = html(client.get('/precificacao/?q="><script>alert(1)</script>'))
    assert "<script>alert(1)" not in corpo


def test_filtro_malicioso_nao_vira_redirecionamento_externo(client):
    p = novo()
    r = client.post(f"/precificacao/{p.id}/aplicar",
                    data={"margem": "30", "despesas": "0", "voltar": "https://evil.example", "next": "//evil.example"})
    assert r.headers["Location"].startswith("/precificacao/") and "evil" not in r.headers["Location"]


@pytest.mark.parametrize("perfil,ok", [("DONO", True), ("GERENTE", True), ("CAIXA", False)])
def test_permissao_do_modulo(cliente_como, perfil, ok):
    c = cliente_como(perfil)
    p = novo()
    assert (c.get("/precificacao/").status_code == 200) is ok
    r = c.post(f"/precificacao/{p.id}/aplicar", data={"margem": "30", "despesas": "0"})
    assert (r.status_code == 302) is ok and (preco(p) == D("10.00")) is ok
    if not ok:
        assert r.status_code == 403


def test_anonimo_vai_para_login(client_anonimo):
    assert client_anonimo.get("/precificacao/").status_code == 302
    assert client_anonimo.post("/precificacao/1/aplicar").status_code in (302, 400)


class _Csrf(TestConfig):
    WTF_CSRF_ENABLED = True


def test_aplicar_exige_csrf():
    app = create_app(_Csrf)
    with app.app_context():
        db.create_all()
        c = app.test_client()
        entrar(c, "DONO")
        p = novo()
        assert c.post(f"/precificacao/{p.id}/aplicar", data={"margem": "30", "despesas": "0"}).status_code == 400
        assert preco(p) == D("8.00")
        corpo = html(c.get("/precificacao/"))
        token = re.search(r'name="csrf_token" value="([^"]+)"', corpo).group(1)
        r = c.post(f"/precificacao/{p.id}/aplicar", data={"margem": "30", "despesas": "0", "csrf_token": token})
        assert r.status_code == 302 and preco(p) == D("10.00")
        db.session.remove()
        db.drop_all()
