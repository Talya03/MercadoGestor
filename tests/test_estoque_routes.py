"""Testes das telas de Estoque (requisições HTTP simuladas)."""
from datetime import datetime
from decimal import Decimal
from itertools import count

import pytest

from app import create_app
from app.extensions import db
from app.models import Produto
from app.services import categoria_service, estoque_service, produto_service
from config import TestConfig

_codigos = count(1)


def _html(resposta):
    return resposta.get_data(as_text=True)


@pytest.fixture
def categoria(app):
    return categoria_service.criar("Laticínios")


def novo_produto(categoria, unidade="UN", **extras):
    dados = {
        "categoria_id": categoria.id,
        "nome": f"Produto {next(_codigos)}",
        "codigo": f"COD{next(_codigos)}",
        "unidade_medida": unidade,
        "preco_custo": "4,50",
        "preco_venda": "6,99",
        "estoque_minimo": "5",
    }
    dados.update(extras)
    return produto_service.criar(dados)


@pytest.fixture
def produto(categoria):
    return novo_produto(categoria, nome="Leite Integral 1L")


def saldo(produto_id):
    db.session.expire_all()
    return db.session.get(Produto, produto_id).quantidade_estoque


def movimentar(client, operacao, produto_id, quantidade, motivo="Teste", **extras):
    dados = {"produto_id": str(produto_id), "quantidade": quantidade, "motivo": motivo}
    dados.update(extras)
    return client.post(f"/estoque/{operacao}", data=dados, follow_redirects=True)


# ------------------------------------------------------------ posição/lista
def test_lista_sem_produtos_mostra_orientacao(client):
    resposta = client.get("/estoque/")
    assert resposta.status_code == 200
    assert "Nenhum produto ativo" in _html(resposta)


def test_lista_mostra_saldo_e_situacao_de_cada_produto(client, categoria):
    zerado = novo_produto(categoria, nome="Zerado")
    baixo = novo_produto(categoria, nome="Baixinho")
    cheio = novo_produto(categoria, nome="Cheinho")
    estoque_service.entrada(baixo.id, "3", "Compra")
    estoque_service.entrada(cheio.id, "40", "Compra")

    html = _html(client.get("/estoque/"))
    assert "Sem estoque" in html and "Baixo" in html and "Ok" in html
    assert "40 UN" in html
    assert zerado.nome in html


def test_lista_avisa_quantos_produtos_estao_com_estoque_baixo(client, categoria):
    novo_produto(categoria, nome="A")
    novo_produto(categoria, nome="B")
    html = _html(client.get("/estoque/"))
    assert "<strong>2</strong>" in html
    assert "produtos com estoque baixo" in html


def test_lista_nao_mostra_o_aviso_quando_tudo_esta_ok(client, produto):
    estoque_service.entrada(produto.id, "40", "Compra")
    assert "com estoque baixo" not in _html(client.get("/estoque/"))


def test_lista_filtra_por_busca_e_por_estoque_baixo(client, categoria):
    queijo = novo_produto(categoria, nome="Queijo", codigo="111")
    suco = novo_produto(categoria, nome="Suco", codigo="222")
    estoque_service.entrada(queijo.id, "40", "Compra")

    assert "Suco" in _html(client.get("/estoque/?q=222"))
    assert "Queijo" not in _html(client.get("/estoque/?q=222"))
    so_baixo = _html(client.get("/estoque/?baixo=1"))
    assert "Suco" in so_baixo and "Queijo" not in so_baixo
    assert suco.nome in so_baixo


def test_lista_nao_mostra_produto_inativo(client, produto):
    produto_service.alternar_ativo(produto.id)
    assert "Leite Integral 1L" not in _html(client.get("/estoque/"))


def test_menu_lateral_tem_link_para_estoque(client):
    assert 'href="/estoque/"' in _html(client.get("/"))


# --------------------------------------------------------------- formulários
@pytest.mark.parametrize(
    "operacao, titulo",
    [("entrada", "Entrada de mercadoria"), ("saida", "Saída de mercadoria"), ("ajuste", "Ajuste de estoque")],
)
def test_formularios_abrem(client, produto, operacao, titulo):
    resposta = client.get(f"/estoque/{operacao}")
    assert resposta.status_code == 200
    assert titulo in _html(resposta)


def test_operacao_desconhecida_da_404(client, produto):
    assert client.get("/estoque/roubo").status_code == 404


def test_sem_produtos_redireciona_para_o_cadastro(client, categoria):
    resposta = client.get("/estoque/entrada", follow_redirects=True)
    html = _html(resposta)
    assert "Cadastre ao menos um produto" in html
    assert "Novo produto" in html


def test_sem_produtos_e_sem_categorias_a_orientacao_encadeia_ate_a_categoria(client):
    html = _html(client.get("/estoque/entrada", follow_redirects=True))
    assert "Cadastre ao menos um produto" in html
    assert "Cadastre ao menos uma categoria" in html
    assert "Nova categoria" in html


def test_formulario_vindo_da_lista_ja_traz_o_produto_escolhido(client, produto):
    html = _html(client.get(f"/estoque/saida?produto={produto.id}"))
    assert f'<option selected value="{produto.id}">' in html


def test_formulario_mostra_o_saldo_no_seletor_e_so_produtos_ativos(client, categoria):
    ativo = novo_produto(categoria, nome="Ativo")
    inativo = novo_produto(categoria, nome="Inativo")
    estoque_service.entrada(ativo.id, "12", "Compra")
    produto_service.alternar_ativo(inativo.id)
    html = _html(client.get("/estoque/entrada"))
    assert "Ativo" in html and "saldo: 12 UN" in html
    assert "Inativo" not in html


def test_formulario_tem_sugestoes_de_motivo(client, produto):
    assert "Compra de fornecedor" in _html(client.get("/estoque/entrada"))
    assert "Produto vencido" in _html(client.get("/estoque/saida"))
    assert "Contagem de inventário" in _html(client.get("/estoque/ajuste"))


# ---------------------------------------------------------------- operações
def test_entrada_pela_tela(client, produto):
    html = _html(movimentar(client, "entrada", produto.id, "24", "Compra de fornecedor"))
    assert "Entrada registrada" in html
    assert "agora tem 24 UN" in html
    assert saldo(produto.id) == Decimal("24")


def test_entrada_aceita_virgula(client, categoria):
    kg = novo_produto(categoria, unidade="KG", nome="Tomate")
    html = _html(movimentar(client, "entrada", kg.id, "2,5"))
    assert "agora tem 2,5 KG" in html


def test_saida_pela_tela_e_aviso_de_estoque_baixo(client, produto):
    estoque_service.entrada(produto.id, "10", "Compra")
    html = _html(movimentar(client, "saida", produto.id, "6", "Produto vencido"))
    assert "Saída registrada" in html
    assert "com estoque baixo (mínimo: 5 UN)" in html
    assert saldo(produto.id) == Decimal("4")


def test_saida_que_zera_o_estoque_avisa_que_acabou(client, produto):
    estoque_service.entrada(produto.id, "10", "Compra")
    html = _html(movimentar(client, "saida", produto.id, "10", "Doação"))
    assert "está sem estoque" in html


def test_saida_maior_que_o_saldo_mostra_erro_e_nao_altera(client, produto):
    estoque_service.entrada(produto.id, "10", "Compra")
    resposta = movimentar(client, "saida", produto.id, "11", "Perda")
    assert "Saldo insuficiente: há 10 UN" in _html(resposta)
    assert saldo(produto.id) == Decimal("10")


def test_ajuste_pela_tela(client, produto):
    estoque_service.entrada(produto.id, "24", "Compra")
    html = _html(movimentar(client, "ajuste", produto.id, "22", "Contagem de inventário"))
    assert "Ajuste registrado" in html
    assert saldo(produto.id) == Decimal("22")


def test_ajuste_para_o_mesmo_saldo_mostra_erro(client, produto):
    estoque_service.entrada(produto.id, "10", "Compra")
    assert "igual ao saldo atual" in _html(movimentar(client, "ajuste", produto.id, "10"))


@pytest.mark.parametrize(
    "ajuste_dados, mensagem",
    [
        ({"produto_id": "0"}, "Selecione um produto."),
        ({"quantidade": ""}, "Informe a quantidade."),
        ({"quantidade": "abc"}, "Valor inválido"),
        ({"quantidade": "-2"}, "O valor não pode ser negativo."),
        ({"motivo": ""}, "Informe o motivo da movimentação."),
        ({"quantidade": "0"}, "deve ser maior que zero"),
        ({"quantidade": "2,5"}, "quantidades inteiras"),
    ],
)
def test_erros_aparecem_no_formulario_e_nada_e_gravado(client, produto, ajuste_dados, mensagem):
    dados = {"produto_id": str(produto.id), "quantidade": "5", "motivo": "Compra"}
    dados.update(ajuste_dados)
    resposta = client.post("/estoque/entrada", data=dados)
    assert resposta.status_code == 200
    assert mensagem in _html(resposta)
    assert saldo(produto.id) == Decimal("0")
    assert estoque_service.historico() == []


def test_formulario_com_erro_preserva_o_que_foi_digitado(client, produto):
    resposta = client.post(
        "/estoque/entrada",
        data={"produto_id": str(produto.id), "quantidade": "abc", "motivo": "Compra Boa"},
    )
    html = _html(resposta)
    assert 'value="abc"' in html
    assert 'value="Compra Boa"' in html


def test_produto_inativo_nao_pode_ser_movimentado_nem_por_post_direto(client, categoria, produto):
    novo_produto(categoria, nome="Outro ativo")  # garante que a rota não redirecione antes
    produto_service.alternar_ativo(produto.id)
    resposta = client.post(
        "/estoque/entrada",
        data={"produto_id": str(produto.id), "quantidade": "5", "motivo": "Compra"},
    )
    assert "está inativo" in _html(resposta)
    assert saldo(produto.id) == Decimal("0")


# ----------------------------------------------------------------- histórico
def test_historico_vazio(client):
    resposta = client.get("/estoque/historico")
    assert resposta.status_code == 200
    assert "Nenhuma movimentação encontrada" in _html(resposta)


def test_historico_mostra_variacao_com_sinal_saldos_e_motivo(client, produto):
    estoque_service.entrada(produto.id, "10", "Compra de fornecedor")
    estoque_service.saida(produto.id, "3", "Produto vencido")
    html = _html(client.get("/estoque/historico"))
    assert "+10 UN" in html and "-3 UN" in html
    assert "0 → 10" in html and "10 → 7" in html
    assert "Compra de fornecedor" in html and "Produto vencido" in html
    assert "Entrada" in html and "Saída" in html


def test_historico_mostra_data_e_hora_no_horario_local(client, produto):
    mov = estoque_service.entrada(produto.id, "10", "Compra")
    mov.data_hora = datetime(2026, 11, 9, 1, 30)  # UTC
    db.session.commit()
    assert "08/11/2026 22:30" in _html(client.get("/estoque/historico"))


def test_historico_filtra_por_produto_e_tipo(client, categoria):
    a = novo_produto(categoria, nome="Alfa")
    b = novo_produto(categoria, nome="Beta")
    estoque_service.entrada(a.id, "10", "Compra do Alfa")
    estoque_service.entrada(b.id, "10", "Compra do Beta")
    estoque_service.saida(b.id, "2", "Perda do Beta")

    por_produto = _html(client.get(f"/estoque/historico?produto={a.id}"))
    assert "Compra do Alfa" in por_produto and "Beta" not in por_produto.split("<tbody>")[1]

    por_tipo = _html(client.get("/estoque/historico?tipo=SAIDA"))
    assert "Perda do Beta" in por_tipo and "Compra do Beta" not in por_tipo


def test_historico_filtra_por_data_local(client, produto):
    mov = estoque_service.entrada(produto.id, "10", "Compra à noite")
    mov.data_hora = datetime(2026, 11, 9, 1, 30)  # 22:30 do dia 8 no mercado
    db.session.commit()

    assert "Compra à noite" in _html(client.get("/estoque/historico?de=2026-11-08&ate=2026-11-08"))
    assert "Compra à noite" not in _html(client.get("/estoque/historico?de=2026-11-09&ate=2026-11-09"))


def test_historico_ignora_data_invalida_na_url(client, produto):
    estoque_service.entrada(produto.id, "10", "Compra")
    resposta = client.get("/estoque/historico?de=ontem&ate=32/13/2026")
    assert resposta.status_code == 200
    assert "Compra" in _html(resposta)


def test_historico_com_datas_invertidas_avisa(client, produto):
    estoque_service.entrada(produto.id, "10", "Compra")
    html = _html(client.get("/estoque/historico?de=2026-11-10&ate=2026-11-01"))
    assert "não pode ser posterior" in html


def test_historico_com_tipo_invalido_avisa_sem_quebrar(client):
    resposta = client.get("/estoque/historico?tipo=ROUBO")
    assert resposta.status_code == 200
    assert "Tipo de movimentação inválido" in _html(resposta)


# --------------------------------------------------------------------- CSRF
class _ConfigComCsrf(TestConfig):
    WTF_CSRF_ENABLED = True


@pytest.fixture
def client_com_csrf():
    app = create_app(_ConfigComCsrf)
    with app.app_context():
        db.create_all()
        cat = categoria_service.criar("Laticínios")
        novo_produto(cat)
        yield app.test_client()
        db.session.remove()
        db.drop_all()


def test_movimentacao_sem_token_csrf_e_bloqueada(client_com_csrf):
    resposta = client_com_csrf.post(
        "/estoque/entrada", data={"produto_id": "1", "quantidade": "5", "motivo": "Compra"}
    )
    assert resposta.status_code == 400
    assert estoque_service.historico() == []
