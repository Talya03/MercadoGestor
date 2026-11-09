"""Testes das regras da Venda (cálculos, desconto, pagamento e gravação atômica)."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from itertools import count

import pytest

from app.extensions import db
from app.models import ItemVenda, MovimentacaoEstoque, Pagamento, Produto, Venda
from app.services import categoria_service, estoque_service, produto_service
from app.services import venda_service as service
from app.utils.erros import ErroDeNegocio

_codigos = count(1)


@pytest.fixture
def categoria(app):
    return categoria_service.criar("Mercearia")


def novo_produto(categoria, unidade="UN", saldo="20", venda="6,99", custo="4,50", **extras):
    dados = {
        "categoria_id": categoria.id,
        "nome": f"Produto {next(_codigos)}",
        "codigo": f"V{next(_codigos)}",
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
    return novo_produto(categoria, nome="Leite 1L", saldo="20", venda="6,99", custo="4,50")


@pytest.fixture
def tomate(categoria):
    return novo_produto(categoria, unidade="KG", nome="Tomate", saldo="10", venda="8,90", custo="5,00")


@pytest.fixture
def arroz(categoria):
    return novo_produto(categoria, nome="Arroz 5kg", saldo="3", venda="25,00", custo="19,00")


def saldo(produto):
    db.session.expire_all()
    return db.session.get(Produto, produto.id).quantidade_estoque


def contar(modelo):
    return db.session.query(modelo).count()


# ------------------------------------------------------------------ resumo
def test_resumo_calcula_subtotais_e_total(leite, tomate):
    resumo = service.montar_resumo({leite.id: Decimal("2"), tomate.id: Decimal("0.350")})
    subtotais = {linha.produto.nome: linha.subtotal for linha in resumo.linhas}
    assert subtotais["Leite 1L"] == Decimal("13.98")
    assert subtotais["Tomate"] == Decimal("3.12")  # 0,350 x 8,90 = 3,115 -> arredonda para cima
    assert resumo.subtotal == Decimal("17.10")
    assert resumo.desconto == Decimal("0.00")
    assert resumo.total == Decimal("17.10")
    assert not resumo.vazio and not resumo.tem_problema


def test_resumo_de_carrinho_vazio(app):
    resumo = service.montar_resumo({})
    assert resumo.vazio
    assert resumo.total == Decimal("0.00")


def test_resumo_usa_sempre_o_preco_atual_do_banco(leite):
    itens = {leite.id: Decimal("2")}
    assert service.montar_resumo(itens).total == Decimal("13.98")
    produto_service.editar(
        leite.id,
        {
            "categoria_id": leite.categoria_id, "nome": leite.nome, "codigo": leite.codigo,
            "unidade_medida": "UN", "preco_custo": "4,50", "preco_venda": "7,50", "estoque_minimo": "5",
        },
    )
    assert service.montar_resumo(itens).total == Decimal("15.00")


def test_resumo_sinaliza_saldo_insuficiente_e_produto_inativo(leite, arroz):
    resumo = service.montar_resumo({leite.id: Decimal("2"), arroz.id: Decimal("5")})
    problemas = {linha.produto.nome: linha.problema for linha in resumo.linhas}
    assert problemas["Leite 1L"] is None
    assert "Saldo insuficiente (há 3 UN)" in problemas["Arroz 5kg"]
    assert resumo.tem_problema

    produto_service.alternar_ativo(leite.id)
    resumo = service.montar_resumo({leite.id: Decimal("2")})
    assert resumo.linhas[0].problema == "Produto inativo."


def test_resumo_aplica_desconto(leite):
    resumo = service.montar_resumo({leite.id: Decimal("2")}, ("PERCENTUAL", "10"))
    assert resumo.subtotal == Decimal("13.98")
    assert resumo.desconto == Decimal("1.39")
    assert resumo.total == Decimal("12.59")


# ---------------------------------------------------------------- desconto
def test_desconto_percentual_e_truncado_para_baixo_no_centavo(app):
    # 10% de 13,98 = 1,398 -> 1,39 (nunca passa do percentual digitado)
    assert service.calcular_desconto(Decimal("13.98"), "PERCENTUAL", "10") == Decimal("1.39")
    assert service.calcular_desconto(Decimal("100.00"), "PERCENTUAL", "5,5") == Decimal("5.50")


def test_desconto_em_reais(app):
    assert service.calcular_desconto(Decimal("13.98"), "VALOR", "1,39") == Decimal("1.39")
    assert service.calcular_desconto(Decimal("50.00"), "valor", "5") == Decimal("5.00")  # tipo em minúsculas


@pytest.mark.parametrize("valor", ["0", "0,00"])
def test_desconto_zero_nao_desconta_nada(app, valor):
    assert service.calcular_desconto(Decimal("13.98"), "VALOR", valor) == Decimal("0.00")


@pytest.mark.parametrize(
    "tipo, valor, trecho",
    [
        ("PERCENTUAL", "10,5", "máximo permitido é 10%"),
        ("PERCENTUAL", "50", "máximo permitido é 10%"),
        ("VALOR", "1,40", r"máximo permitido é 10% \(R\$ 1,39 nesta compra\)"),
        ("VALOR", "20", "maior que o total da compra"),
        ("VALOR", "-1", "não pode ser negativo"),
        ("PERCENTUAL", "abc", "Valor inválido"),
        ("PERCENTUAL", "NaN", "Valor inválido"),
        ("PERCENTUAL", "", "Informe um valor"),
        ("PERCENTUAL", "1,234", "no máximo 2 casas"),
        ("XX", "5", "em R\\$ ou em %"),
        ("", "5", "em R\\$ ou em %"),
        (None, "5", "em R\\$ ou em %"),
    ],
)
def test_descontos_invalidos_ou_acima_do_limite_sao_recusados(app, tipo, valor, trecho):
    with pytest.raises(ErroDeNegocio, match=trecho):
        service.calcular_desconto(Decimal("13.98"), tipo, valor)


def test_nao_ha_desconto_em_carrinho_vazio(app):
    with pytest.raises(ErroDeNegocio, match="carrinho está vazio"):
        service.calcular_desconto(Decimal("0.00"), "VALOR", "1")


def test_limite_de_desconto_e_configuravel(app):
    app.config["DESCONTO_MAXIMO_PERCENTUAL"] = Decimal("20")
    assert service.calcular_desconto(Decimal("100.00"), "PERCENTUAL", "15") == Decimal("15.00")
    with pytest.raises(ErroDeNegocio, match="máximo permitido é 20%"):
        service.calcular_desconto(Decimal("100.00"), "PERCENTUAL", "21")


# --------------------------------------------------------------- finalizar
def test_finalizar_grava_venda_itens_pagamento_e_baixa_o_estoque(leite, tomate):
    itens = {leite.id: Decimal("2"), tomate.id: Decimal("0.350")}
    venda = service.finalizar(itens, ("PERCENTUAL", "10"), "DINHEIRO", "20")

    assert venda.id is not None
    assert venda.subtotal == Decimal("17.10")
    assert venda.desconto == Decimal("1.71")
    assert venda.total == Decimal("15.39")
    assert len(venda.itens) == 2

    item_leite = next(i for i in venda.itens if i.produto_id == leite.id)
    assert item_leite.quantidade == Decimal("2")
    assert item_leite.preco_unitario == Decimal("6.99")
    assert item_leite.custo_unitario == Decimal("4.50")
    assert item_leite.subtotal == Decimal("13.98")

    assert len(venda.pagamentos) == 1
    pagamento = venda.pagamentos[0]
    assert pagamento.forma == "DINHEIRO"
    assert pagamento.valor == Decimal("15.39")
    assert pagamento.valor_recebido == Decimal("20.00")
    assert pagamento.troco == Decimal("4.61")

    assert saldo(leite) == Decimal("18")
    assert saldo(tomate) == Decimal("9.650")


def test_a_baixa_de_estoque_gera_movimentacao_com_o_numero_da_venda(leite):
    venda = service.finalizar({leite.id: Decimal("3")}, None, "PIX")
    mov = (
        db.session.query(MovimentacaoEstoque)
        .filter_by(produto_id=leite.id, tipo="SAIDA")
        .one()
    )
    assert mov.motivo == f"Venda #{venda.id}"
    assert mov.quantidade == Decimal("3")
    assert mov.saldo_anterior == Decimal("20")
    assert mov.saldo_posterior == Decimal("17")


def test_estoque_e_historico_continuam_consistentes_apos_varias_vendas(leite, tomate):
    service.finalizar({leite.id: Decimal("2")}, None, "PIX")
    service.finalizar({tomate.id: Decimal("1.5"), leite.id: Decimal("1")}, None, "DEBITO")
    with pytest.raises(ErroDeNegocio):
        service.finalizar({leite.id: Decimal("500")}, None, "PIX")
    assert estoque_service.conferir_saldos() == []


def test_o_item_guarda_o_preco_do_momento_da_venda(leite):
    venda = service.finalizar({leite.id: Decimal("1")}, None, "PIX")
    produto_service.editar(
        leite.id,
        {
            "categoria_id": leite.categoria_id, "nome": leite.nome, "codigo": leite.codigo,
            "unidade_medida": "UN", "preco_custo": "9,00", "preco_venda": "12,00", "estoque_minimo": "5",
        },
    )
    db.session.expire_all()
    item = service.buscar_venda(venda.id).itens[0]
    assert item.preco_unitario == Decimal("6.99")  # o comprovante antigo não muda
    assert item.custo_unitario == Decimal("4.50")
    assert service.buscar_venda(venda.id).total == Decimal("6.99")


# -------------------------------------------------------- atomicidade (RN25)
def test_venda_com_um_item_sem_saldo_nao_grava_nada(leite, arroz):
    """O leite é baixado ANTES de o arroz falhar; o rollback precisa desfazer o leite também."""
    movimentacoes_antes = contar(MovimentacaoEstoque)
    itens = {leite.id: Decimal("2"), arroz.id: Decimal("5")}  # arroz: só há 3

    with pytest.raises(ErroDeNegocio, match="Arroz 5kg: .*Saldo insuficiente"):
        service.finalizar(itens, None, "PIX")

    assert contar(Venda) == 0
    assert contar(ItemVenda) == 0
    assert contar(Pagamento) == 0
    assert contar(MovimentacaoEstoque) == movimentacoes_antes
    assert saldo(leite) == Decimal("20")
    assert saldo(arroz) == Decimal("3")
    assert estoque_service.conferir_saldos() == []


def test_falha_no_pagamento_tambem_desfaz_a_baixa_de_estoque(leite):
    with pytest.raises(ErroDeNegocio, match="Selecione a forma de pagamento"):
        service.finalizar({leite.id: Decimal("2")}, None, "CHEQUE")
    assert contar(Venda) == 0
    assert saldo(leite) == Decimal("20")


def test_falha_de_dinheiro_insuficiente_desfaz_tudo(leite):
    with pytest.raises(ErroDeNegocio, match="faltam R\\$ 3,98"):
        service.finalizar({leite.id: Decimal("2")}, None, "DINHEIRO", "10")
    assert contar(Venda) == 0
    assert saldo(leite) == Decimal("20")


# --------------------------------------------------------------- pagamento
def test_dinheiro_em_branco_significa_valor_exato(leite):
    venda = service.finalizar({leite.id: Decimal("2")}, None, "DINHEIRO", "")
    pagamento = venda.pagamentos[0]
    assert pagamento.valor_recebido == Decimal("13.98")
    assert pagamento.troco == Decimal("0.00")


def test_dinheiro_calcula_o_troco(leite):
    venda = service.finalizar({leite.id: Decimal("2")}, None, "DINHEIRO", "20,00")
    assert venda.pagamentos[0].troco == Decimal("6.02")


def test_dinheiro_aceita_recebimento_exato(leite):
    venda = service.finalizar({leite.id: Decimal("2")}, None, "DINHEIRO", "13,98")
    assert venda.pagamentos[0].troco == Decimal("0.00")


@pytest.mark.parametrize("forma", ["PIX", "DEBITO", "CREDITO", "pix", " credito "])
def test_pix_e_cartoes_cobram_exatamente_o_total(leite, forma):
    # Mesmo que alguém envie "valor recebido", ele é ignorado fora do dinheiro.
    venda = service.finalizar({leite.id: Decimal("2")}, None, forma, "100")
    pagamento = venda.pagamentos[0]
    assert pagamento.valor == Decimal("13.98")
    assert pagamento.valor_recebido is None
    assert pagamento.troco == Decimal("0.00")
    assert pagamento.forma == forma.strip().upper()


@pytest.mark.parametrize("forma", ["", None, "CHEQUE", "BOLETO"])
def test_forma_de_pagamento_invalida(leite, forma):
    with pytest.raises(ErroDeNegocio, match="Selecione a forma de pagamento"):
        service.finalizar({leite.id: Decimal("1")}, None, forma)


@pytest.mark.parametrize("recebido, trecho", [("abc", "Valor inválido"), ("-5", "negativo"), ("NaN", "Valor inválido")])
def test_valor_recebido_invalido(leite, recebido, trecho):
    with pytest.raises(ErroDeNegocio, match=trecho):
        service.finalizar({leite.id: Decimal("1")}, None, "DINHEIRO", recebido)
    assert contar(Venda) == 0


def test_o_desconto_e_conferido_de_novo_ao_finalizar(leite):
    # Mesmo que a tela tenha guardado um desconto antigo, o limite vale na gravação.
    with pytest.raises(ErroDeNegocio, match="máximo permitido é 10%"):
        service.finalizar({leite.id: Decimal("2")}, ("PERCENTUAL", "50"), "PIX")
    assert contar(Venda) == 0
    assert saldo(leite) == Decimal("20")


# ------------------------------------------------------ carrinho inválido
def test_carrinho_vazio_nao_gera_venda(app):
    with pytest.raises(ErroDeNegocio, match="carrinho está vazio"):
        service.finalizar({}, None, "PIX")


def test_produto_inexistente_no_carrinho(leite):
    with pytest.raises(ErroDeNegocio, match="não existe mais"):
        service.finalizar({leite.id: Decimal("1"), 999: Decimal("1")}, None, "PIX")
    assert contar(Venda) == 0


def test_produto_inativo_no_carrinho(leite):
    produto_service.alternar_ativo(leite.id)
    with pytest.raises(ErroDeNegocio, match="inativo"):
        service.finalizar({leite.id: Decimal("1")}, None, "PIX")
    assert contar(Venda) == 0


def test_venda_de_valor_zero_e_recusada(categoria):
    brinde = novo_produto(categoria, venda="0", nome="Brinde")
    with pytest.raises(ErroDeNegocio, match="maior que zero"):
        service.finalizar({brinde.id: Decimal("1")}, None, "PIX")
    assert contar(Venda) == 0
    assert saldo(brinde) == Decimal("20")


def test_quantidade_fracionada_de_unidade_contavel_e_recusada_na_gravacao(leite):
    with pytest.raises(ErroDeNegocio, match="quantidades inteiras"):
        service.finalizar({leite.id: Decimal("1.5")}, None, "PIX")
    assert contar(Venda) == 0


# ---------------------------------------------------- envio duplicado (RN27)
def test_mesmo_token_nao_gera_duas_vendas_nem_baixa_o_estoque_duas_vezes(leite):
    token = str(uuid.uuid4())
    primeira = service.finalizar({leite.id: Decimal("2")}, None, "PIX", token_envio=token)
    with pytest.raises(ErroDeNegocio, match="já foi registrada"):
        service.finalizar({leite.id: Decimal("2")}, None, "PIX", token_envio=token)

    assert contar(Venda) == 1
    assert saldo(leite) == Decimal("18")  # baixou uma vez só
    assert service.venda_por_token(token).id == primeira.id


def test_tokens_diferentes_geram_vendas_diferentes(leite):
    service.finalizar({leite.id: Decimal("1")}, None, "PIX", token_envio=str(uuid.uuid4()))
    service.finalizar({leite.id: Decimal("1")}, None, "PIX", token_envio=str(uuid.uuid4()))
    assert contar(Venda) == 2


def test_venda_sem_token_e_permitida_e_venda_por_token_ignora_vazio(leite):
    service.finalizar({leite.id: Decimal("1")}, None, "PIX")
    service.finalizar({leite.id: Decimal("1")}, None, "PIX", token_envio="")
    assert contar(Venda) == 2
    assert service.venda_por_token(None) is None
    assert service.venda_por_token("") is None
    assert service.venda_por_token(str(uuid.uuid4())) is None


# --------------------------------------------------------------- consultas
def test_buscar_venda_traz_itens_e_pagamentos(leite, tomate):
    criada = service.finalizar({leite.id: Decimal("1"), tomate.id: Decimal("1")}, None, "CREDITO")
    db.session.expire_all()
    venda = service.buscar_venda(criada.id)
    assert {i.produto.nome for i in venda.itens} == {"Leite 1L", "Tomate"}
    assert venda.pagamentos[0].forma_nome == "Cartão de crédito"


def test_buscar_venda_inexistente(app):
    with pytest.raises(ErroDeNegocio, match="Venda não encontrada"):
        service.buscar_venda(999)


def test_listagem_da_mais_recente_para_a_mais_antiga(leite):
    primeira = service.finalizar({leite.id: Decimal("1")}, None, "PIX")
    segunda = service.finalizar({leite.id: Decimal("1")}, None, "PIX")
    assert [v.id for v in service.listar_vendas()] == [segunda.id, primeira.id]


def test_listagem_filtra_pelo_dia_do_mercado_e_nao_pelo_dia_utc(leite):
    venda = service.finalizar({leite.id: Decimal("1")}, None, "PIX")
    venda.data_hora = datetime(2026, 11, 9, 1, 30)  # 22:30 de 08/11 em São Paulo
    db.session.commit()

    assert [v.id for v in service.listar_vendas(date(2026, 11, 8), date(2026, 11, 8))] == [venda.id]
    assert service.listar_vendas(date(2026, 11, 9), date(2026, 11, 9)) == []


def test_listagem_com_datas_invertidas(app):
    with pytest.raises(ErroDeNegocio, match="não pode ser posterior"):
        service.listar_vendas(date(2026, 11, 10), date(2026, 11, 1))


def test_listagem_respeita_o_limite(leite):
    for _ in range(4):
        service.finalizar({leite.id: Decimal("1")}, None, "PIX")
    assert len(service.listar_vendas(limite=2)) == 2
