"""Testes das telas do PDV, do comprovante e da lista de vendas."""
import re
from datetime import datetime
from decimal import Decimal
from itertools import count

import pytest

from app import create_app
from app.extensions import db
from app.models import MovimentacaoEstoque, Produto, Venda
from app.services import categoria_service, estoque_service, produto_service
from tests.conftest import entrar
from config import TestConfig

_codigos = count(1)


def _html(resposta):
    return resposta.get_data(as_text=True)


@pytest.fixture
def categoria(app):
    return categoria_service.criar("Mercearia")


def novo_produto(categoria, unidade="UN", saldo="20", venda="6,99", custo="4,50", **extras):
    dados = {
        "categoria_id": categoria.id,
        "nome": f"Produto {next(_codigos)}",
        "codigo": f"P{next(_codigos)}",
        "unidade_medida": unidade,
        "preco_custo": custo,
        "preco_venda": venda,
        "estoque_minimo": "5",
    }
    dados.update(extras)
    produto = produto_service.criar(dados)
    if Decimal(saldo) > 0:
        estoque_service.entrada(produto.id, saldo, "Estoque inicial")
    return produto


@pytest.fixture
def leite(categoria):
    return novo_produto(categoria, nome="Leite 1L", codigo="LEITE1", saldo="20", venda="6,99")


@pytest.fixture
def tomate(categoria):
    return novo_produto(categoria, unidade="KG", nome="Tomate", codigo="TOM", saldo="10", venda="8,90")


def saldo(produto):
    db.session.expire_all()
    return db.session.get(Produto, produto.id).quantidade_estoque


def total_vendas():
    return db.session.query(Venda).count()


def adicionar(client, produto, quantidade="1"):
    return client.post(
        "/pdv/adicionar",
        data={"produto_id": str(produto.id), "quantidade": quantidade},
        follow_redirects=True,
    )


def token_do_formulario(client):
    html = _html(client.get("/pdv/"))
    return re.search(r'name="token" value="([0-9a-f-]{36})"', html).group(1)


def finalizar(client, forma="PIX", recebido="", token=None, **extras):
    dados = {"forma": forma, "valor_recebido": recebido, "token": token or token_do_formulario(client)}
    dados.update(extras)
    return client.post("/pdv/finalizar", data=dados, follow_redirects=True)


# --------------------------------------------------------------------- tela
def test_tela_do_pdv_abre_com_carrinho_vazio(client):
    resposta = client.get("/pdv/")
    assert resposta.status_code == 200
    assert "Carrinho vazio" in _html(resposta)


def test_menu_lateral_tem_pdv_e_vendas(client):
    html = _html(client.get("/"))
    assert 'href="/pdv/"' in html
    assert 'href="/pdv/vendas"' in html


def test_formulario_traz_token_de_envio_e_cada_venda_recebe_um_novo(client, leite):
    adicionar(client, leite, "2")  # o formulário de pagamento só aparece com itens no carrinho
    primeiro = token_do_formulario(client)
    assert token_do_formulario(client) == primeiro  # estável enquanto a venda não acaba
    finalizar(client, token=primeiro)
    adicionar(client, leite, "1")
    assert token_do_formulario(client) != primeiro


# ------------------------------------------------------------------- busca
def test_busca_mostra_produtos_com_preco_e_saldo(client, leite):
    html = _html(client.get("/pdv/?q=leite"))
    assert "Leite 1L" in html
    assert "R$ 6,99/UN" in html
    assert "20 UN" in html


def test_busca_sem_resultado_e_sem_termo(client, leite):
    assert "Nenhum produto ativo encontrado" in _html(client.get("/pdv/?q=zzz"))
    assert "Digite parte do nome" in _html(client.get("/pdv/"))


def test_busca_nao_mostra_produto_inativo(client, leite):
    produto_service.alternar_ativo(leite.id)
    assert "Leite 1L" not in _html(client.get("/pdv/?q=leite"))


def test_busca_marca_produto_sem_estoque_e_bloqueia_o_botao(client, categoria):
    novo_produto(categoria, nome="Esgotado", saldo="0")
    html = _html(client.get("/pdv/?q=esgotado"))
    assert "Sem estoque" in html
    assert re.search(r'<button class="btn btn-sm btn-success" type="submit"\s+disabled', html)


# --------------------------------------------------------------- adicionar
def test_adiciona_produto_ao_carrinho(client, leite):
    html = _html(adicionar(client, leite, "2"))
    assert "Leite 1L" in html
    assert "R$ 13,98" in html
    assert "Carrinho vazio" not in html


def test_adiciona_produto_por_peso_com_virgula(client, tomate):
    html = _html(adicionar(client, tomate, "0,350"))
    assert "R$ 3,12" in html  # 0,350 x 8,90 = 3,115 arredondado ao centavo
    assert 'value="0,35"' in html


def test_adicionar_o_mesmo_produto_soma_as_quantidades(client, leite):
    adicionar(client, leite, "2")
    html = _html(adicionar(client, leite, "3"))
    assert "R$ 34,95" in html  # 5 x 6,99


def test_quantidade_em_branco_vira_um(client, leite):
    html = _html(adicionar(client, leite, ""))
    assert "R$ 6,99" in html


@pytest.mark.parametrize(
    "quantidade, mensagem",
    [("0", "maior que zero"), ("-1", "negativ"), ("abc", "Valor inválido"), ("1,5", "quantidades inteiras"), ("21", "Saldo insuficiente")],
)
def test_adicionar_quantidade_invalida_mostra_erro_e_nao_mexe_no_carrinho(client, leite, quantidade, mensagem):
    html = _html(adicionar(client, leite, quantidade))
    assert mensagem in html
    assert "Carrinho vazio" in html


def test_adicionar_produto_inexistente_ou_id_invalido(client):
    assert "Produto não encontrado" in _html(client.post("/pdv/adicionar", data={"produto_id": "999"}, follow_redirects=True))
    assert "Produto inválido" in _html(client.post("/pdv/adicionar", data={"produto_id": "abc"}, follow_redirects=True))
    assert "Produto inválido" in _html(client.post("/pdv/adicionar", data={}, follow_redirects=True))


# ------------------------------------------------------- adicionar por código
def test_adiciona_por_codigo_ignorando_maiusculas(client, leite):
    resposta = client.post(
        "/pdv/adicionar-por-codigo", data={"codigo": "leite1", "quantidade": "2"}, follow_redirects=True
    )
    html = _html(resposta)
    assert "Leite 1L" in html and "R$ 13,98" in html


def test_codigo_exato_nao_confunde_com_codigo_parecido(client, categoria):
    novo_produto(categoria, nome="Arroz curto", codigo="ARR")
    novo_produto(categoria, nome="Arroz longo", codigo="ARR2")
    html = _html(client.post("/pdv/adicionar-por-codigo", data={"codigo": "ARR"}, follow_redirects=True))
    assert "Arroz curto" in html and "Arroz longo" not in html.split("<tbody>")[-1]


def test_codigo_inexistente_ou_vazio(client, leite):
    html = _html(client.post("/pdv/adicionar-por-codigo", data={"codigo": "XYZ"}, follow_redirects=True))
    assert "Nenhum produto ativo com o código" in html and "XYZ" in html
    html = _html(client.post("/pdv/adicionar-por-codigo", data={"codigo": "  "}, follow_redirects=True))
    assert "Informe o código do produto" in html


def test_codigo_de_produto_inativo_nao_e_aceito(client, leite):
    produto_service.alternar_ativo(leite.id)
    html = _html(client.post("/pdv/adicionar-por-codigo", data={"codigo": "LEITE1"}, follow_redirects=True))
    assert "Nenhum produto ativo com o código" in html


# ------------------------------------------------------- alterar e remover
def test_altera_quantidade_de_um_item(client, leite):
    adicionar(client, leite, "2")
    resposta = client.post(f"/pdv/item/{leite.id}/quantidade", data={"quantidade": "5"}, follow_redirects=True)
    assert "R$ 34,95" in _html(resposta)


def test_quantidade_zero_remove_o_item(client, leite):
    adicionar(client, leite, "2")
    resposta = client.post(f"/pdv/item/{leite.id}/quantidade", data={"quantidade": "0"}, follow_redirects=True)
    assert "Carrinho vazio" in _html(resposta)


def test_alterar_quantidade_para_valor_invalido_mantem_o_item(client, leite):
    adicionar(client, leite, "2")
    resposta = client.post(f"/pdv/item/{leite.id}/quantidade", data={"quantidade": "99"}, follow_redirects=True)
    html = _html(resposta)
    assert "Saldo insuficiente" in html
    assert "R$ 13,98" in html


def test_remove_item(client, leite, tomate):
    adicionar(client, leite, "1")
    adicionar(client, tomate, "1")
    html = _html(client.post(f"/pdv/item/{leite.id}/remover", follow_redirects=True))
    assert "Tomate" in html
    assert "Leite 1L" not in html.split("Carrinho")[-1]


def test_cancelar_venda_esvazia_o_carrinho_sem_mexer_no_estoque(client, leite):
    adicionar(client, leite, "3")
    html = _html(client.post("/pdv/cancelar", follow_redirects=True))
    assert "Venda cancelada" in html
    assert "Carrinho vazio" in html
    assert saldo(leite) == Decimal("20")
    assert total_vendas() == 0


# ---------------------------------------------------------------- desconto
def test_aplica_desconto_percentual(client, leite):
    adicionar(client, leite, "2")
    resposta = client.post("/pdv/desconto", data={"tipo": "PERCENTUAL", "valor": "10"}, follow_redirects=True)
    html = _html(resposta)
    assert "Desconto aplicado" in html
    assert "− R$ 1,39" in html
    assert "R$ 12,59" in html


def test_aplica_desconto_em_reais(client, leite):
    adicionar(client, leite, "2")
    html = _html(client.post("/pdv/desconto", data={"tipo": "VALOR", "valor": "1,00"}, follow_redirects=True))
    assert "− R$ 1,00" in html and "R$ 12,98" in html


@pytest.mark.parametrize(
    "tipo, valor, mensagem",
    [("PERCENTUAL", "30", "máximo permitido é 10%"), ("VALOR", "5", "máximo permitido"), ("PERCENTUAL", "abc", "Valor inválido"), ("PERCENTUAL", "", "Informe um valor")],
)
def test_desconto_invalido_ou_acima_do_limite_nao_e_aplicado(client, leite, tipo, valor, mensagem):
    adicionar(client, leite, "2")
    html = _html(client.post("/pdv/desconto", data={"tipo": tipo, "valor": valor}, follow_redirects=True))
    assert mensagem in html
    assert "− R$" not in html
    assert "R$ 13,98" in html


def test_desconto_em_carrinho_vazio_e_recusado(client):
    html = _html(client.post("/pdv/desconto", data={"tipo": "VALOR", "valor": "1"}, follow_redirects=True))
    assert "carrinho está vazio" in html


def test_desconto_zero_nao_aplica_nada(client, leite):
    adicionar(client, leite, "2")
    html = _html(client.post("/pdv/desconto", data={"tipo": "VALOR", "valor": "0"}, follow_redirects=True))
    assert "Desconto aplicado" not in html
    assert "− R$" not in html


def test_remove_desconto(client, leite):
    adicionar(client, leite, "2")
    client.post("/pdv/desconto", data={"tipo": "PERCENTUAL", "valor": "10"})
    html = _html(client.post("/pdv/desconto/remover", follow_redirects=True))
    assert "− R$" not in html
    assert "R$ 13,98" in html


def test_desconto_que_deixa_de_valer_quando_o_carrinho_diminui_e_removido_com_aviso(client, leite):
    adicionar(client, leite, "2")
    client.post("/pdv/desconto", data={"tipo": "VALOR", "valor": "1,39"})  # válido em R$ 13,98
    resposta = client.post(f"/pdv/item/{leite.id}/quantidade", data={"quantidade": "1"}, follow_redirects=True)
    html = _html(resposta)
    assert "Desconto removido" in html
    assert "− R$" not in html
    assert "R$ 6,99" in html


# --------------------------------------------------------------- finalizar
def test_finalizar_em_dinheiro_mostra_comprovante_com_troco_e_baixa_o_estoque(client, leite):
    adicionar(client, leite, "2")
    html = _html(finalizar(client, "DINHEIRO", "20"))

    assert "registrada com sucesso" in html
    assert "Comprovante de venda" in html and "não é documento fiscal" in html
    assert "Dinheiro" in html
    assert "R$ 20,00" in html  # recebido
    assert "R$ 6,02" in html  # troco
    assert saldo(leite) == Decimal("18")
    assert total_vendas() == 1


def test_finalizar_com_desconto_grava_os_valores_corretos(client, leite):
    adicionar(client, leite, "2")
    client.post("/pdv/desconto", data={"tipo": "PERCENTUAL", "valor": "10"})
    html = _html(finalizar(client, "PIX"))
    assert "− R$ 1,39" in html and "R$ 12,59" in html and "Pix" in html
    venda = db.session.query(Venda).one()
    assert (venda.subtotal, venda.desconto, venda.total) == (Decimal("13.98"), Decimal("1.39"), Decimal("12.59"))


def test_carrinho_fica_vazio_depois_da_venda(client, leite):
    adicionar(client, leite, "2")
    finalizar(client)
    assert "Carrinho vazio" in _html(client.get("/pdv/"))


def test_a_baixa_aparece_no_historico_de_estoque_com_o_numero_da_venda(client, leite):
    adicionar(client, leite, "2")
    finalizar(client)
    venda = db.session.query(Venda).one()
    mov = db.session.query(MovimentacaoEstoque).filter_by(tipo="SAIDA").one()
    assert mov.motivo == f"Venda #{venda.id}"
    assert f"Venda #{venda.id}" in _html(client.get("/estoque/historico"))


def test_finalizar_com_carrinho_vazio(client):
    html = _html(finalizar(client, token="3f0c1a52-8a0b-4d0e-9d57-0a1f2b3c4d5e"))
    assert "carrinho está vazio" in html
    assert total_vendas() == 0


def test_finalizar_sem_forma_de_pagamento_mantem_o_carrinho(client, leite):
    adicionar(client, leite, "2")
    html = _html(finalizar(client, forma=""))
    assert "Selecione a forma de pagamento" in html
    assert "Leite 1L" in html
    assert total_vendas() == 0


def test_dinheiro_insuficiente_mantem_o_carrinho_e_nao_vende(client, leite):
    adicionar(client, leite, "2")
    html = _html(finalizar(client, "DINHEIRO", "10"))
    assert "faltam R$ 3,98" in html
    assert "Leite 1L" in html
    assert total_vendas() == 0
    assert saldo(leite) == Decimal("20")


def test_saldo_que_diminui_depois_de_adicionar_bloqueia_a_finalizacao(client, leite):
    adicionar(client, leite, "5")
    estoque_service.saida(leite.id, "18", "Perda")  # sobram 2 enquanto o cliente passa as compras

    tela = _html(client.get("/pdv/"))
    assert "Saldo insuficiente (há 2 UN)" in tela
    assert "Resolva os avisos do carrinho" in tela

    html = _html(finalizar(client))
    assert "Saldo insuficiente" in html
    assert total_vendas() == 0
    assert saldo(leite) == Decimal("2")
    assert "Leite 1L" in html  # o carrinho continua lá para o caixa ajustar


def test_reenvio_do_mesmo_formulario_nao_vende_duas_vezes(client, leite):
    adicionar(client, leite, "2")
    token = token_do_formulario(client)
    primeira = finalizar(client, token=token)
    segunda = finalizar(client, token=token)  # clique duplo / botão "voltar" e reenviar

    assert "registrada com sucesso" in _html(primeira)
    html = _html(segunda)
    assert "já havia sido registrada" in html
    assert "Comprovante de venda" in html  # leva ao comprovante da venda original
    assert total_vendas() == 1
    assert saldo(leite) == Decimal("18")  # baixou uma vez só


def test_token_invalido_nao_impede_a_venda(client, leite):
    adicionar(client, leite, "1")
    html = _html(finalizar(client, token="isto-nao-e-um-uuid"))
    assert "registrada com sucesso" in html
    assert db.session.query(Venda).one().token_envio is None


def test_o_navegador_nao_consegue_alterar_preco_nem_total(client, leite):
    # Campos extras enviados à mão (como numa adulteração) são simplesmente ignorados.
    client.post(
        "/pdv/adicionar",
        data={"produto_id": str(leite.id), "quantidade": "1", "preco": "0,01", "preco_unitario": "0,01"},
    )
    assert "R$ 6,99" in _html(client.get("/pdv/"))

    finalizar(client, "PIX", total="0,01", subtotal="0,01", desconto="100", preco="0,01")
    venda = db.session.query(Venda).one()
    assert venda.total == Decimal("6.99")
    assert venda.desconto == Decimal("0.00")


# ------------------------------------------------------------- comprovante
def test_comprovante_mostra_itens_e_valores_da_venda(client, leite, tomate):
    adicionar(client, leite, "2")
    adicionar(client, tomate, "0,350")
    finalizar(client, "CREDITO")
    venda = db.session.query(Venda).one()
    html = _html(client.get(f"/pdv/vendas/{venda.id}"))
    assert f"Venda #{venda.id}" in html
    assert "Leite 1L" in html and "Tomate" in html
    assert "0,35 KG" in html
    assert "R$ 17,10" in html
    assert "Cartão de crédito" in html


def test_comprovante_de_venda_inexistente_volta_para_a_lista(client):
    resposta = client.get("/pdv/vendas/999", follow_redirects=True)
    assert "Venda não encontrada" in _html(resposta)


# ---------------------------------------------------------- lista de vendas
def test_lista_de_vendas_mostra_as_de_hoje_por_padrao_com_total(client, leite):
    for _ in range(2):
        adicionar(client, leite, "1")
        finalizar(client)
    html = _html(client.get("/pdv/vendas"))
    assert "2 vendas no período" in html
    assert "R$ 13,98" in html
    assert "Pix" in html


def test_lista_de_vendas_vazia(client):
    assert "Nenhuma venda neste período" in _html(client.get("/pdv/vendas"))


def test_lista_padrao_nao_mostra_venda_de_outro_dia_mas_todas_mostra(client, leite):
    adicionar(client, leite, "1")
    finalizar(client)
    venda = db.session.query(Venda).one()
    venda.data_hora = datetime(2026, 1, 15, 15, 0)
    db.session.commit()

    assert "Nenhuma venda neste período" in _html(client.get("/pdv/vendas"))
    assert f"#{venda.id}" in _html(client.get("/pdv/vendas?de=&ate="))
    assert f"#{venda.id}" in _html(client.get("/pdv/vendas?de=2026-01-15&ate=2026-01-15"))
    assert "Nenhuma venda neste período" in _html(client.get("/pdv/vendas?de=2026-01-16&ate=2026-01-16"))


def test_lista_de_vendas_filtra_pelo_dia_do_mercado(client, leite):
    adicionar(client, leite, "1")
    finalizar(client)
    venda = db.session.query(Venda).one()
    venda.data_hora = datetime(2026, 11, 9, 1, 30)  # 22:30 de 08/11 no mercado
    db.session.commit()

    html = _html(client.get("/pdv/vendas?de=2026-11-08&ate=2026-11-08"))
    assert f"#{venda.id}" in html and "08/11/2026 22:30" in html
    assert "Nenhuma venda" in _html(client.get("/pdv/vendas?de=2026-11-09&ate=2026-11-09"))


def test_lista_de_vendas_ignora_data_invalida_e_avisa_datas_invertidas(client, leite):
    adicionar(client, leite, "1")
    finalizar(client)
    assert client.get("/pdv/vendas?de=ontem&ate=32/13/2026").status_code == 200
    html = _html(client.get("/pdv/vendas?de=2026-11-10&ate=2026-11-01"))
    assert "não pode ser posterior" in html


# ------------------------------------------------------------------ CSRF/HTTP
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


ROTAS_POST = [
    "/pdv/adicionar",
    "/pdv/adicionar-por-codigo",
    "/pdv/item/1/quantidade",
    "/pdv/item/1/remover",
    "/pdv/cancelar",
    "/pdv/desconto",
    "/pdv/desconto/remover",
    "/pdv/finalizar",
]


@pytest.mark.parametrize("rota", ROTAS_POST)
def test_toda_acao_do_pdv_exige_token_csrf(client_com_csrf, rota):
    assert client_com_csrf.post(rota, data={}).status_code == 400


@pytest.mark.parametrize("rota", ROTAS_POST)
def test_acoes_do_pdv_nao_aceitam_get(client, rota):
    assert client.get(rota).status_code == 405
