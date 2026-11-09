"""Testes das regras do Controle de Estoque (service).

Foco nos casos de erro e na consistência: o saldo e o histórico precisam
sempre contar a mesma história.
"""
from datetime import date, datetime
from decimal import Decimal
from itertools import count

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import MovimentacaoEstoque, Produto
from app.services import categoria_service, estoque_service as service, produto_service
from app.utils.erros import ErroDeNegocio

_codigos = count(1)


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


@pytest.fixture
def produto_kg(categoria):
    return novo_produto(categoria, unidade="KG", nome="Tomate")


def saldo(produto_id):
    db.session.expire_all()
    return db.session.get(Produto, produto_id).quantidade_estoque


def total_movimentacoes(produto_id=None):
    consulta = db.session.query(MovimentacaoEstoque)
    if produto_id:
        consulta = consulta.filter_by(produto_id=produto_id)
    return consulta.count()


# ---------------------------------------------------------------- entrada
def test_entrada_aumenta_o_saldo_e_registra_a_movimentacao(produto):
    mov = service.entrada(produto.id, "24", "Compra de fornecedor")

    assert saldo(produto.id) == Decimal("24")
    assert mov.tipo == "ENTRADA"
    assert mov.quantidade == Decimal("24")
    assert mov.saldo_anterior == Decimal("0")
    assert mov.saldo_posterior == Decimal("24")
    assert mov.motivo == "Compra de fornecedor"
    assert mov.data_hora is not None
    assert mov.variacao == Decimal("24")


def test_entradas_sucessivas_acumulam(produto):
    service.entrada(produto.id, "10", "Compra")
    mov = service.entrada(produto.id, "5", "Compra")
    assert mov.saldo_anterior == Decimal("10")
    assert saldo(produto.id) == Decimal("15")


def test_entrada_aceita_virgula_em_produto_vendido_por_peso(produto_kg):
    service.entrada(produto_kg.id, "2,5", "Compra")
    assert saldo(produto_kg.id) == Decimal("2.5")


@pytest.mark.parametrize("unidade", ["UN", "CX", "PCT"])
def test_unidades_contaveis_so_aceitam_quantidade_inteira(categoria, unidade):  # RN14
    p = novo_produto(categoria, unidade=unidade)
    with pytest.raises(ErroDeNegocio, match="quantidades inteiras"):
        service.entrada(p.id, "2,5", "Compra")
    assert total_movimentacoes() == 0


def test_unidade_contavel_aceita_inteiro_escrito_com_casas(produto):
    service.entrada(produto.id, "3,000", "Compra")
    assert saldo(produto.id) == Decimal("3")


@pytest.mark.parametrize(
    "quantidade, trecho",
    [
        ("0", "maior que zero"),
        ("-1", "não pode ser negativo"),
        ("abc", "Valor inválido"),
        ("NaN", "Valor inválido"),
        ("Infinity", "Valor inválido"),
        ("", "Informe um valor"),
        (None, "Informe um valor"),
        ("1,2345", "no máximo 3 casas"),
        ("10000000", "grande demais"),
    ],
)
def test_entrada_com_quantidade_invalida_e_recusada_sem_gravar_nada(produto_kg, quantidade, trecho):
    with pytest.raises(ErroDeNegocio, match=trecho):
        service.entrada(produto_kg.id, quantidade, "Compra")
    assert saldo(produto_kg.id) == Decimal("0")
    assert total_movimentacoes() == 0


def test_entrada_que_estoura_o_limite_do_saldo_e_recusada(produto_kg):
    service.entrada(produto_kg.id, "9999999", "Compra")
    with pytest.raises(ErroDeNegocio, match="limite"):
        service.entrada(produto_kg.id, "1", "Compra")
    assert saldo(produto_kg.id) == Decimal("9999999")


# ------------------------------------------------------------------ saída
def test_saida_diminui_o_saldo(produto):
    service.entrada(produto.id, "10", "Compra")
    mov = service.saida(produto.id, "3", "Produto vencido")

    assert saldo(produto.id) == Decimal("7")
    assert mov.tipo == "SAIDA"
    assert mov.quantidade == Decimal("3")
    assert mov.saldo_anterior == Decimal("10")
    assert mov.saldo_posterior == Decimal("7")
    assert mov.variacao == Decimal("-3")


def test_saida_pode_zerar_o_estoque(produto):
    service.entrada(produto.id, "4", "Compra")
    service.saida(produto.id, "4", "Doação")
    assert saldo(produto.id) == Decimal("0")


def test_saida_maior_que_o_saldo_e_bloqueada_sem_gravar_nada(produto):  # RN06
    service.entrada(produto.id, "10", "Compra")
    with pytest.raises(ErroDeNegocio, match="Saldo insuficiente: há 10 UN"):
        service.saida(produto.id, "11", "Perda")
    assert saldo(produto.id) == Decimal("10")
    assert total_movimentacoes(produto.id) == 1  # só a entrada


def test_saida_de_produto_sem_estoque_e_bloqueada(produto):
    with pytest.raises(ErroDeNegocio, match="Saldo insuficiente"):
        service.saida(produto.id, "1", "Perda")
    assert total_movimentacoes() == 0


@pytest.mark.parametrize("quantidade", ["0", "-2", "abc"])
def test_saida_com_quantidade_invalida_e_recusada(produto, quantidade):
    service.entrada(produto.id, "10", "Compra")
    with pytest.raises(ErroDeNegocio):
        service.saida(produto.id, quantidade, "Perda")
    assert saldo(produto.id) == Decimal("10")


def test_saida_fracionada_em_unidade_contavel_e_recusada(produto):
    service.entrada(produto.id, "10", "Compra")
    with pytest.raises(ErroDeNegocio, match="quantidades inteiras"):
        service.saida(produto.id, "0,5", "Perda")


# ----------------------------------------------------------------- ajuste
def test_ajuste_para_baixo_registra_a_diferenca(produto):
    service.entrada(produto.id, "24", "Compra")
    mov = service.ajuste(produto.id, "22", "Contagem de inventário")

    assert saldo(produto.id) == Decimal("22")
    assert mov.tipo == "AJUSTE"
    assert mov.quantidade == Decimal("2")  # a diferença, sempre positiva
    assert mov.saldo_anterior == Decimal("24")
    assert mov.saldo_posterior == Decimal("22")
    assert mov.variacao == Decimal("-2")


def test_ajuste_para_cima(produto):
    service.entrada(produto.id, "10", "Compra")
    mov = service.ajuste(produto.id, "13", "Contagem de inventário")
    assert saldo(produto.id) == Decimal("13")
    assert mov.quantidade == Decimal("3")
    assert mov.variacao == Decimal("3")


def test_ajuste_para_zero_e_permitido(produto):
    service.entrada(produto.id, "10", "Compra")
    service.ajuste(produto.id, "0", "Contagem de inventário")
    assert saldo(produto.id) == Decimal("0")


def test_ajuste_para_o_mesmo_saldo_e_recusado(produto):  # RN16
    service.entrada(produto.id, "10", "Compra")
    with pytest.raises(ErroDeNegocio, match="igual ao saldo atual"):
        service.ajuste(produto.id, "10", "Contagem")
    assert total_movimentacoes() == 1


@pytest.mark.parametrize("contado", ["-1", "abc", "", "1,2345"])
def test_ajuste_com_saldo_invalido_e_recusado(produto_kg, contado):
    service.entrada(produto_kg.id, "10", "Compra")
    with pytest.raises(ErroDeNegocio):
        service.ajuste(produto_kg.id, contado, "Contagem")
    assert saldo(produto_kg.id) == Decimal("10")


def test_ajuste_fracionado_em_unidade_contavel_e_recusado(produto):
    with pytest.raises(ErroDeNegocio, match="quantidades inteiras"):
        service.ajuste(produto.id, "2,5", "Contagem")


# ----------------------------------------------------------------- motivo
@pytest.mark.parametrize("motivo", ["", "   ", None])
@pytest.mark.parametrize("operacao", ["entrada", "saida", "ajuste"])
def test_motivo_e_obrigatorio(produto, operacao, motivo):  # RN05
    service.entrada(produto.id, "10", "Compra")
    with pytest.raises(ErroDeNegocio, match="Informe o motivo"):
        getattr(service, operacao)(produto.id, "1", motivo)
    assert total_movimentacoes() == 1


def test_motivo_muito_longo_e_recusado(produto):
    with pytest.raises(ErroDeNegocio, match="no máximo 255"):
        service.entrada(produto.id, "1", "x" * 256)


def test_motivo_tem_os_espacos_normalizados(produto):
    mov = service.entrada(produto.id, "1", "  Compra   de   fornecedor ")
    assert mov.motivo == "Compra de fornecedor"


# ------------------------------------------------------- produto inválido
@pytest.mark.parametrize("operacao", ["entrada", "saida", "ajuste"])
def test_produto_inexistente(app, operacao):
    with pytest.raises(ErroDeNegocio, match="Produto não encontrado"):
        getattr(service, operacao)(999, "1", "Teste")


@pytest.mark.parametrize("operacao", ["entrada", "saida", "ajuste"])
def test_produto_inativo_nao_pode_ser_movimentado(produto, operacao):  # RN15
    produto_service.alternar_ativo(produto.id)
    with pytest.raises(ErroDeNegocio, match="inativo"):
        getattr(service, operacao)(produto.id, "1", "Teste")
    assert total_movimentacoes() == 0


# ------------------------------------------- transação e consistência (RN17)
def test_falha_no_commit_desfaz_saldo_e_movimentacao(produto, monkeypatch):
    service.entrada(produto.id, "10", "Compra")

    def commit_que_falha():
        raise IntegrityError("INSERT", {}, Exception("falha simulada"))

    monkeypatch.setattr(db.session, "commit", commit_que_falha)
    with pytest.raises(ErroDeNegocio, match="Nada foi alterado"):
        service.saida(produto.id, "3", "Perda")
    monkeypatch.undo()

    assert saldo(produto.id) == Decimal("10")  # o saldo NÃO mudou
    assert total_movimentacoes(produto.id) == 1  # e nenhuma movimentação "órfã"
    assert service.conferir_saldos() == []


def test_operacao_concorrente_e_recusada_em_vez_de_vender_estoque_que_nao_existe(
    produto, monkeypatch
):
    """Simula outro caixa alterando o saldo entre a leitura e a gravação."""
    service.entrada(produto.id, "10", "Compra")
    validar_original = service._validar_motivo

    def validar_e_outro_caixa_mexe_no_saldo(motivo):
        db.session.connection().exec_driver_sql(
            "UPDATE produto SET quantidade_estoque = 3 WHERE id = ?", (produto.id,)
        )
        return validar_original(motivo)

    monkeypatch.setattr(service, "_validar_motivo", validar_e_outro_caixa_mexe_no_saldo)
    with pytest.raises(ErroDeNegocio, match="alterado por outra operação"):
        service.saida(produto.id, "8", "Perda")
    monkeypatch.undo()

    assert total_movimentacoes(produto.id) == 1  # nenhuma saída foi registrada
    assert service.conferir_saldos() == []


def test_decimais_nao_acumulam_erro_de_arredondamento(produto_kg):
    for _ in range(10):
        service.entrada(produto_kg.id, "0,1", "Compra")
    assert saldo(produto_kg.id) == Decimal("1.000")  # em float seria 0.9999999999999999
    service.saida(produto_kg.id, "1", "Venda")
    assert saldo(produto_kg.id) == Decimal("0.000")
    assert service.conferir_saldos() == []


def test_a_cadeia_de_movimentacoes_sempre_explica_o_saldo(produto, produto_kg):
    service.entrada(produto.id, "24", "Compra")
    service.saida(produto.id, "1", "Produto vencido")
    service.ajuste(produto.id, "22", "Contagem")
    service.entrada(produto_kg.id, "7,5", "Compra")
    service.saida(produto_kg.id, "2,25", "Perda")
    with pytest.raises(ErroDeNegocio):
        service.saida(produto.id, "100", "Erro")  # recusada: não entra na cadeia

    assert service.conferir_saldos() == []
    movs = service.historico(produto_id=produto.id)[::-1]  # do mais antigo ao mais novo
    for anterior, atual in zip(movs, movs[1:]):
        assert atual.saldo_anterior == anterior.saldo_posterior
    assert movs[-1].saldo_posterior == saldo(produto.id)


def test_conferir_saldos_detecta_saldo_adulterado_fora_do_sistema(produto):
    service.entrada(produto.id, "10", "Compra")
    db.session.connection().exec_driver_sql(
        "UPDATE produto SET quantidade_estoque = 99 WHERE id = ?", (produto.id,)
    )
    db.session.commit()

    divergentes = service.conferir_saldos()
    assert len(divergentes) == 1
    produto_divergente, esperado = divergentes[0]
    assert produto_divergente.id == produto.id
    assert esperado == Decimal("10")


# ------------------------------------------------------------- histórico
def test_historico_vem_do_mais_recente_para_o_mais_antigo(produto):
    service.entrada(produto.id, "10", "Primeira")
    service.saida(produto.id, "2", "Segunda")
    service.ajuste(produto.id, "5", "Terceira")
    assert [m.motivo for m in service.historico()] == ["Terceira", "Segunda", "Primeira"]


def test_historico_filtra_por_produto_e_por_tipo(produto, produto_kg):
    service.entrada(produto.id, "10", "Compra A")
    service.saida(produto.id, "2", "Perda A")
    service.entrada(produto_kg.id, "5", "Compra B")

    assert {m.motivo for m in service.historico(produto_id=produto.id)} == {"Compra A", "Perda A"}
    assert [m.motivo for m in service.historico(tipo="ENTRADA", produto_id=produto_kg.id)] == ["Compra B"]
    assert len(service.historico(tipo="SAIDA")) == 1


def test_historico_com_tipo_invalido_da_erro(app):
    with pytest.raises(ErroDeNegocio, match="Tipo de movimentação inválido"):
        service.historico(tipo="ROUBO")


def test_historico_com_datas_invertidas_da_erro(app):
    with pytest.raises(ErroDeNegocio, match="não pode ser posterior"):
        service.historico(data_inicio=date(2026, 11, 10), data_fim=date(2026, 11, 1))


def test_filtro_de_data_usa_o_dia_do_mercado_e_nao_o_dia_utc(produto):
    # 01:30 UTC de 09/11 = 22:30 de 08/11 em São Paulo (UTC-3).
    mov = service.entrada(produto.id, "10", "Compra à noite")
    mov.data_hora = datetime(2026, 11, 9, 1, 30)
    db.session.commit()

    dia_8 = service.historico(data_inicio=date(2026, 11, 8), data_fim=date(2026, 11, 8))
    dia_9 = service.historico(data_inicio=date(2026, 11, 9), data_fim=date(2026, 11, 9))
    assert [m.motivo for m in dia_8] == ["Compra à noite"]
    assert dia_9 == []


def test_filtro_de_data_inclui_o_dia_final_inteiro_e_aceita_ponta_aberta(produto):
    antes = service.entrada(produto.id, "1", "Dia 1 de manhã")
    antes.data_hora = datetime(2026, 11, 1, 12, 0)  # 09:00 local
    depois = service.entrada(produto.id, "1", "Dia 3 de noite")
    depois.data_hora = datetime(2026, 11, 4, 2, 59)  # 23:59 local do dia 3
    fora = service.entrada(produto.id, "1", "Dia 4")
    fora.data_hora = datetime(2026, 11, 4, 3, 0)  # 00:00 local do dia 4
    db.session.commit()

    periodo = service.historico(data_inicio=date(2026, 11, 1), data_fim=date(2026, 11, 3))
    assert {m.motivo for m in periodo} == {"Dia 1 de manhã", "Dia 3 de noite"}
    assert len(service.historico(data_inicio=date(2026, 11, 2))) == 2  # sem data final
    assert len(service.historico(data_fim=date(2026, 11, 1))) == 1  # sem data inicial


def test_historico_respeita_o_limite(produto):
    for i in range(5):
        service.entrada(produto.id, "1", f"Compra {i}")
    assert len(service.historico(limite=3)) == 3
