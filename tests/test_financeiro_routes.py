"""Testes das telas do Financeiro e da condição de pagamento na compra."""
import re
import uuid
from datetime import timedelta
from decimal import Decimal
from itertools import count

import pytest

from app import create_app
from app.extensions import db
from app.models import Compra, Lancamento
from app.services import categoria_service, fornecedor_service, produto_service
from app.services import financeiro_service as fin
from app.utils.hoje import hoje_local
from tests.conftest import entrar
from config import TestConfig

_n = count(1)


def html(r):
    return r.get_data(as_text=True)


def despesa(descricao="Aluguel", valor="1800", venc=None, **kw):
    return fin.criar("DESPESA", "ALUGUEL", descricao, valor, venc or hoje_local(), **kw)


def test_paginas_abrem(client):
    for url in ("/financeiro/", "/financeiro/novo", "/financeiro/novo?tipo=RECEITA", "/financeiro/resumo"):
        assert client.get(url).status_code == 200


def test_lista_mostra_pendente_vencida_e_totais(client):
    despesa("Luz", "100", hoje_local() - timedelta(days=3))
    despesa("Água", "50", hoje_local() + timedelta(days=3))
    corpo = html(client.get("/financeiro/"))
    assert "Luz" in corpo and "Água" in corpo
    assert "Vencida" in corpo and "R$ 150,00" in corpo and "R$ 100,00" in corpo


def test_filtros_invalidos_nao_quebram(client):
    assert client.get("/financeiro/?status=xx&tipo=yy&de=lixo&ate=lixo").status_code == 200
    assert "data inicial" in html(client.get("/financeiro/?de=2026-05-02&ate=2026-05-01"))


def test_cria_despesa_e_receita_pela_tela(client):
    r = client.post(
        "/financeiro/novo",
        data={"tipo": "DESPESA", "categoria": "ALUGUEL", "descricao": "Aluguel", "valor": "1.800,00",
              "data": "2026-11-10"},
        follow_redirects=True,
    )
    assert "Despesa lançada" in html(r) and "R$ 1.800,00" in html(r)
    r = client.post(
        "/financeiro/novo",
        data={"tipo": "RECEITA", "categoria": "OUTRAS_RECEITAS", "descricao": "Comissão", "valor": "20",
              "data": "2026-11-11"},
        follow_redirects=True,
    )
    assert "Receita lançada" in html(r) and "Comissão" in html(r)


def test_erro_reexibe_formulario_com_valores(client):
    r = client.post("/financeiro/novo", data={"tipo": "DESPESA", "categoria": "ALUGUEL",
                                              "descricao": "Aluguel", "valor": "0", "data": "2026-11-10"})
    corpo = html(r)
    assert "maior que zero" in corpo and 'value="Aluguel"' in corpo
    assert Lancamento.query.count() == 0


def test_categoria_mercadoria_nao_aparece_nem_e_aceita(client):
    assert "Compra de mercadoria" not in html(client.get("/financeiro/novo"))
    r = client.post("/financeiro/novo", data={"tipo": "DESPESA", "categoria": "MERCADORIA",
                                              "descricao": "x", "valor": "1", "data": "2026-11-10"})
    assert "Compras" in html(r) and Lancamento.query.count() == 0


def test_tipo_invalido_vira_despesa(client):
    assert "Nova despesa" in html(client.get("/financeiro/novo?tipo=XYZ"))


def test_pagar_desfazer_cancelar_so_post_e_funcionam(client):
    l = despesa()
    for acao in ("pagar", "desfazer", "cancelar"):
        assert client.get(f"/financeiro/{l.id}/{acao}").status_code == 405
    assert "Pagamento registrado" in html(client.post(f"/financeiro/{l.id}/pagar", follow_redirects=True))
    assert Lancamento.query.one().pago_em == hoje_local()
    assert "Pagamento desfeito" in html(client.post(f"/financeiro/{l.id}/desfazer", follow_redirects=True))
    assert "cancelado" in html(client.post(f"/financeiro/{l.id}/cancelar", follow_redirects=True))
    assert Lancamento.query.one().cancelado is True


def test_pagar_com_data_futura_mostra_erro(client):
    l = despesa()
    futuro = (hoje_local() + timedelta(days=2)).isoformat()
    r = client.post(f"/financeiro/{l.id}/pagar", data={"data_pagamento": futuro}, follow_redirects=True)
    assert "futura" in html(r) and Lancamento.query.one().pago_em is None


def test_acao_em_inexistente(client):
    assert "não encontrado" in html(client.post("/financeiro/999/pagar", follow_redirects=True))


@pytest.mark.parametrize("voltar, destino", [
    ("/financeiro/?status=todos", "/financeiro/?status=todos"),
    ("https://evil.com/", "/financeiro/"),
    ("//evil.com", "/financeiro/"),
    ("/outra/pagina", "/financeiro/"),
    ("", "/financeiro/"),
])
def test_redirecionamento_so_para_caminho_interno(client, voltar, destino):
    l = despesa()
    r = client.post(f"/financeiro/{l.id}/pagar", data={"voltar": voltar})
    assert r.status_code == 302 and r.headers["Location"] == destino


def test_descricao_com_html_e_escapada(client):
    despesa('<script>alert(1)</script>')
    corpo = html(client.get("/financeiro/"))
    assert "<script>alert(1)" not in corpo and "&lt;script&gt;" in corpo


def test_resumo_navegacao_e_mes_invalido(client):
    corpo = html(client.get("/financeiro/resumo?mes=2026-11"))
    assert "novembro de 2026" in corpo and "mes=2026-10" in corpo and "mes=2026-12" in corpo
    assert "mes=2027-01" in html(client.get("/financeiro/resumo?mes=2026-12"))  # dezembro -> janeiro
    assert "mes=2026-12" in html(client.get("/financeiro/resumo?mes=2027-01"))  # janeiro -> dezembro
    # nos limites do sistema (ano 2000 e 2100) o botão que sairia do intervalo não aparece
    assert "‹" not in html(client.get("/financeiro/resumo?mes=2000-01"))
    assert "›" not in html(client.get("/financeiro/resumo?mes=2100-12"))
    assert "Mês inválido" in html(client.get("/financeiro/resumo?mes=lixo"))
    assert "Mês inválido" in html(client.get("/financeiro/resumo?mes=2026-13"))
    assert "Mês inválido" in html(client.get("/financeiro/resumo?mes=1900-01"))


def test_resumo_mostra_valores(client):
    fin.criar("DESPESA", "ALUGUEL", "Aluguel", "1800", "2026-11-10")
    corpo = html(client.get("/financeiro/resumo?mes=2026-11"))
    assert "R$ 1.800,00" in corpo and "Aluguel" in corpo and "−R$ 1.800,00" in corpo


# ----------------------------------------------------- condição na compra (tela)
@pytest.fixture
def base(app):
    cat = categoria_service.criar("Laticínios")
    forn = fornecedor_service.criar("Bom Preço")
    prod = produto_service.criar(
        {"categoria_id": cat.id, "nome": "Leite", "codigo": f"R{next(_n)}", "unidade_medida": "UN",
         "preco_custo": "4,50", "preco_venda": "6,99", "estoque_minimo": "5"}
    )
    return forn, prod


def dados(forn, prod, **extra):
    d = {"token": str(uuid.uuid4()), "fornecedor_id": str(forn.id), "produto_id": [str(prod.id)],
         "quantidade": ["10"], "custo_unitario": ["4,80"]}
    d.update(extra)
    return d


def test_compra_a_vista_por_padrao(client, base):
    r = client.post("/compras/nova", data=dados(*base), follow_redirects=True)
    assert "Pago em" in html(r)
    assert Lancamento.query.one().pago_em == hoje_local()


def test_compra_a_prazo_pela_tela(client, base):
    venc = (hoje_local() + timedelta(days=15)).isoformat()
    r = client.post("/compras/nova", data=dados(*base, condicao="A_PRAZO", vencimento=venc), follow_redirects=True)
    assert "A pagar" in html(r) and "Ver no Financeiro" in html(r)
    assert "Compra #1" in html(client.get("/financeiro/"))


def test_compra_a_prazo_sem_vencimento_reexibe_form(client, base):
    r = client.post("/compras/nova", data=dados(*base, condicao="A_PRAZO", vencimento=""))
    corpo = html(r)
    assert "Informe o vencimento" in corpo and re.search(r'value="A_PRAZO"\s+selected', corpo)
    assert Compra.query.count() == 0


# ----------------------------------------------------------------------- CSRF
@pytest.fixture
def client_csrf(app):
    class Cfg(TestConfig):
        WTF_CSRF_ENABLED = True

    app2 = create_app(Cfg)
    with app2.app_context():
        db.create_all()
        cliente = app2.test_client()
        entrar(cliente)
        yield cliente
        db.session.remove()
        db.drop_all()


def test_post_sem_csrf_e_recusado(client_csrf):
    for url in ("/financeiro/novo", "/financeiro/1/pagar", "/financeiro/1/desfazer", "/financeiro/1/cancelar"):
        assert client_csrf.post(url, data={}).status_code == 400


def test_fluxo_com_csrf_ligado(client_csrf):
    pagina = html(client_csrf.get("/financeiro/novo"))
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', pagina).group(1)
    r = client_csrf.post("/financeiro/novo", data={
        "csrf_token": csrf, "tipo": "DESPESA", "categoria": "ENERGIA", "descricao": "Luz",
        "valor": "120,50", "data": "2026-11-20"}, follow_redirects=True)
    assert "Despesa lançada" in html(r)
    lista = html(client_csrf.get("/financeiro/"))
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', lista).group(1)
    lid = Lancamento.query.one().id
    r = client_csrf.post(f"/financeiro/{lid}/pagar", data={"csrf_token": csrf}, follow_redirects=True)
    assert "Pagamento registrado" in html(r)
