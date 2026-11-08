"""Testes das telas de produto (requisições HTTP simuladas)."""
from decimal import Decimal

import pytest

from app import create_app
from app.extensions import db
from app.services import categoria_service, produto_service
from config import TestConfig


def _html(resposta):
    return resposta.get_data(as_text=True)


@pytest.fixture
def categoria(app):
    return categoria_service.criar("Laticínios")


def form_valido(categoria, **extras):
    dados = {
        "categoria_id": str(categoria.id),
        "nome": "Leite Integral 1L",
        "codigo": "789100",
        "unidade_medida": "UN",
        "preco_custo": "4,50",
        "preco_venda": "6,99",
        "estoque_minimo": "5",
    }
    dados.update(extras)
    return dados


def test_lista_vazia_mostra_orientacao(client):
    resposta = client.get("/produtos/")
    assert resposta.status_code == 200
    assert "Nenhum produto cadastrado" in _html(resposta)


def test_novo_produto_sem_categoria_redireciona_com_aviso(client):
    resposta = client.get("/produtos/novo", follow_redirects=True)
    html = _html(resposta)
    assert "Cadastre ao menos uma categoria" in html
    assert "Nova categoria" in html


def test_formulario_de_novo_produto_abre_com_categorias_ativas(client, categoria):
    outra = categoria_service.criar("Antigos")
    categoria_service.alternar_ativo(outra.id)
    html = _html(client.get("/produtos/novo"))
    assert "Novo produto" in html
    assert "Laticínios" in html
    assert "Antigos" not in html


def test_cadastra_produto_pela_tela_com_virgula(client, categoria):
    resposta = client.post("/produtos/novo", data=form_valido(categoria), follow_redirects=True)
    html = _html(resposta)
    assert "Produto cadastrado com sucesso." in html
    assert "Leite Integral 1L" in html
    assert "R$ 6,99" in html
    assert "R$ 4,50" in html
    assert "Sem estoque" in html  # começa com saldo 0 (RN12)


def test_cadastro_aceita_preco_zero_no_formulario(client, categoria):
    # Garante que usamos InputRequired (e não DataRequired, que recusaria o 0).
    resposta = client.post(
        "/produtos/novo",
        data=form_valido(categoria, preco_custo="0", preco_venda="0", estoque_minimo="0"),
        follow_redirects=True,
    )
    html = _html(resposta)
    assert "Produto cadastrado com sucesso." in html
    assert "o preço de venda está zerado" in html


def test_cadastro_com_venda_abaixo_do_custo_mostra_aviso(client, categoria):
    resposta = client.post(
        "/produtos/novo",
        data=form_valido(categoria, preco_custo="5", preco_venda="4"),
        follow_redirects=True,
    )
    html = _html(resposta)
    assert "Produto cadastrado com sucesso." in html
    assert "abaixo do preço de custo" in html


@pytest.mark.parametrize(
    "campo, valor, mensagem",
    [
        ("nome", "", "Informe o nome do produto."),
        ("codigo", "", "Informe o código do produto."),
        ("preco_custo", "", "Informe o preço de custo."),
        ("preco_venda", "abc", "Valor inválido"),
        ("preco_venda", "-2", "O valor não pode ser negativo."),
        ("estoque_minimo", "NaN", "Valor inválido"),
        ("categoria_id", "0", "Selecione uma categoria."),
    ],
)
def test_erros_de_validacao_aparecem_no_formulario_e_nada_e_gravado(
    client, categoria, campo, valor, mensagem
):
    resposta = client.post("/produtos/novo", data=form_valido(categoria, **{campo: valor}))
    assert resposta.status_code == 200
    assert mensagem in _html(resposta)
    assert produto_service.listar(incluir_inativos=True) == []


def test_formulario_com_erro_preserva_o_que_foi_digitado(client, categoria):
    resposta = client.post(
        "/produtos/novo", data=form_valido(categoria, nome="Leite", preco_venda="abc")
    )
    html = _html(resposta)
    assert 'value="Leite"' in html
    assert 'value="abc"' in html


def test_codigo_duplicado_mostra_erro(client, categoria):
    client.post("/produtos/novo", data=form_valido(categoria))
    resposta = client.post("/produtos/novo", data=form_valido(categoria, nome="Outro"))
    assert "Já existe um produto com o código" in _html(resposta)
    assert len(produto_service.listar()) == 1


def test_edicao_exibe_valores_formatados_e_estoque_somente_leitura(client, categoria):
    produto = produto_service.criar(
        {**form_valido(categoria), "categoria_id": categoria.id}
    )
    produto.quantidade_estoque = Decimal("12.350")
    db.session.commit()

    html = _html(client.get(f"/produtos/{produto.id}/editar"))
    assert 'value="4,50"' in html
    assert 'value="6,99"' in html
    assert 'value="5"' in html  # estoque mínimo sem zeros à direita
    assert "12,35 UN" in html  # saldo só exibido
    assert 'name="quantidade_estoque"' not in html  # RN12: não existe campo para editar o saldo


def test_edita_produto_pela_tela(client, categoria):
    produto = produto_service.criar({**form_valido(categoria), "categoria_id": categoria.id})
    resposta = client.post(
        f"/produtos/{produto.id}/editar",
        data=form_valido(categoria, nome="Leite Desnatado 1L", preco_venda="7,50"),
        follow_redirects=True,
    )
    html = _html(resposta)
    assert "Produto atualizado com sucesso." in html
    assert "Leite Desnatado 1L" in html
    assert "R$ 7,50" in html


def test_edicao_deixa_a_categoria_e_a_unidade_atuais_selecionadas(client, categoria):
    categoria_service.criar("Bebidas")
    produto = produto_service.criar(
        {**form_valido(categoria), "categoria_id": categoria.id, "unidade_medida": "KG"}
    )
    html = _html(client.get(f"/produtos/{produto.id}/editar"))
    assert f'<option selected value="{categoria.id}">Laticínios</option>' in html
    assert '<option selected value="KG">' in html


def test_edicao_com_categoria_inativa_mantem_a_opcao_atual(client, categoria):
    produto = produto_service.criar({**form_valido(categoria), "categoria_id": categoria.id})
    produto_service.alternar_ativo(produto.id)
    categoria_service.alternar_ativo(categoria.id)
    html = _html(client.get(f"/produtos/{produto.id}/editar"))
    assert "Laticínios (inativa)" in html


def test_editar_produto_inexistente_volta_para_lista(client):
    resposta = client.get("/produtos/999/editar", follow_redirects=True)
    assert "Produto não encontrado." in _html(resposta)


def test_desativa_e_reativa_pela_tela(client, categoria):
    produto = produto_service.criar({**form_valido(categoria), "categoria_id": categoria.id})

    resposta = client.post(f"/produtos/{produto.id}/alternar", follow_redirects=True)
    assert "Produto desativado com sucesso." in _html(resposta)
    assert "Nenhum produto cadastrado" in _html(client.get("/produtos/"))

    com_inativos = _html(client.get("/produtos/?inativos=1"))
    assert "Leite Integral 1L" in com_inativos
    assert "Inativo" in com_inativos

    resposta = client.post(f"/produtos/{produto.id}/alternar", follow_redirects=True)
    assert "Produto ativado com sucesso." in _html(resposta)


def test_nao_reativa_produto_de_categoria_inativa_pela_tela(client, categoria):
    produto = produto_service.criar({**form_valido(categoria), "categoria_id": categoria.id})
    produto_service.alternar_ativo(produto.id)
    categoria_service.alternar_ativo(categoria.id)
    resposta = client.post(f"/produtos/{produto.id}/alternar", follow_redirects=True)
    assert "Reative primeiro a categoria" in _html(resposta)


def test_alternar_nao_aceita_get(client, categoria):
    produto = produto_service.criar({**form_valido(categoria), "categoria_id": categoria.id})
    assert client.get(f"/produtos/{produto.id}/alternar").status_code == 405


def test_busca_e_filtros_da_lista(client, categoria):
    bebidas = categoria_service.criar("Bebidas")
    produto_service.criar({**form_valido(categoria), "categoria_id": categoria.id, "nome": "Queijo", "codigo": "111"})
    produto_service.criar({**form_valido(bebidas), "categoria_id": bebidas.id, "nome": "Suco", "codigo": "222"})

    por_nome = _html(client.get("/produtos/?q=quei"))
    assert "Queijo" in por_nome and "Suco" not in por_nome

    por_codigo = _html(client.get("/produtos/?q=222"))
    assert "Suco" in por_codigo and "Queijo" not in por_codigo

    por_categoria = _html(client.get(f"/produtos/?categoria={bebidas.id}"))
    assert "Suco" in por_categoria and "Queijo" not in por_categoria

    sem_resultado = _html(client.get("/produtos/?q=zzz"))
    assert "Nenhum produto encontrado com esses filtros." in sem_resultado


def test_filtro_de_estoque_baixo_na_tela(client, categoria):
    ok = produto_service.criar({**form_valido(categoria), "categoria_id": categoria.id, "nome": "Cheio", "codigo": "1"})
    baixo = produto_service.criar({**form_valido(categoria), "categoria_id": categoria.id, "nome": "Acabando", "codigo": "2"})
    ok.quantidade_estoque = Decimal("50")
    baixo.quantidade_estoque = Decimal("2")
    db.session.commit()

    html = _html(client.get("/produtos/?baixo=1"))
    assert "Acabando" in html
    assert "Cheio" not in html
    assert "Baixo" in html


def test_nome_com_html_e_escapado(client, categoria):
    produto_service.criar(
        {**form_valido(categoria), "categoria_id": categoria.id, "nome": "<b>Negrito</b>"}
    )
    html = _html(client.get("/produtos/"))
    assert "<b>Negrito</b>" not in html
    assert "&lt;b&gt;Negrito&lt;/b&gt;" in html


def test_menu_lateral_tem_link_para_produtos(client):
    assert 'href="/produtos/"' in _html(client.get("/"))


# ---------- CSRF ----------
class _ConfigComCsrf(TestConfig):
    WTF_CSRF_ENABLED = True


@pytest.fixture
def client_com_csrf():
    app = create_app(_ConfigComCsrf)
    with app.app_context():
        db.create_all()
        categoria_service.criar("Laticínios")
        yield app.test_client()
        db.session.remove()
        db.drop_all()


def test_post_de_produto_sem_token_csrf_e_bloqueado(client_com_csrf):
    resposta = client_com_csrf.post("/produtos/novo", data={"nome": "Leite"})
    assert resposta.status_code == 400
    assert produto_service.listar() == []
