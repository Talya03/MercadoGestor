"""Testes das regras de Compra (RN33 a RN39)."""
import uuid
from decimal import Decimal
from itertools import count

import pytest
from sqlalchemy import func, select

from app.extensions import db
from app.models import Compra, ItemCompra, MovimentacaoEstoque
from app.services import categoria_service, compra_service as svc, estoque_service
from app.services import fornecedor_service, produto_service
from app.utils.erros import ErroDeNegocio

_n = count(1)


@pytest.fixture
def fornecedor(app):
    return fornecedor_service.criar("Distribuidora Bom Preço")


@pytest.fixture
def categoria(app):
    return categoria_service.criar("Laticínios")


def produto(categoria, unidade="UN", **extras):
    dados = {
        "categoria_id": categoria.id,
        "nome": f"Produto {next(_n)}",
        "codigo": f"C{next(_n)}",
        "unidade_medida": unidade,
        "preco_custo": "4,50",
        "preco_venda": "6,99",
        "estoque_minimo": "5",
    }
    dados.update(extras)
    return produto_service.criar(dados)


def item(p, qtd, custo):
    return {"produto_id": p.id, "quantidade": qtd, "custo_unitario": custo}


def total_registros():
    return (
        db.session.scalar(select(func.count(Compra.id))),
        db.session.scalar(select(func.count(ItemCompra.id))),
        db.session.scalar(select(func.count(MovimentacaoEstoque.id))),
    )


def test_compra_feliz_atualiza_estoque_custo_e_total(fornecedor, categoria):
    leite = produto(categoria)
    tomate = produto(categoria, "KG", preco_venda="8,90")
    compra = svc.registrar(
        fornecedor.id,
        [item(leite, "24", "4,80"), item(tomate, "10", "6,20")],
        numero_documento=" NF 123 ",
        observacao="entrega de segunda",
    )
    assert compra.total == Decimal("177.20")  # 24*4,80 + 10*6,20 = 115,20 + 62,00
    assert compra.numero_documento == "NF 123"
    assert [i.subtotal for i in compra.itens] == [Decimal("115.20"), Decimal("62.00")]

    db.session.refresh(leite)
    db.session.refresh(tomate)
    assert leite.quantidade_estoque == Decimal("24")
    assert tomate.quantidade_estoque == Decimal("10")
    assert leite.preco_custo == Decimal("4.80")  # RN37
    assert tomate.preco_custo == Decimal("6.20")
    assert leite.preco_venda == Decimal("6.99")  # preço de venda não muda

    movs = db.session.execute(select(MovimentacaoEstoque).order_by(MovimentacaoEstoque.id)).scalars().all()
    assert [(m.tipo, m.motivo) for m in movs] == [("ENTRADA", f"Compra #{compra.id}")] * 2
    assert estoque_service.conferir_saldos() == []


def test_soma_ao_saldo_existente(fornecedor, categoria):
    p = produto(categoria)
    estoque_service.entrada(p.id, "10", "Saldo inicial")
    svc.registrar(fornecedor.id, [item(p, "5", "5")])
    db.session.refresh(p)
    assert p.quantidade_estoque == Decimal("15")


def test_subtotal_arredonda_meio_para_cima(fornecedor, categoria):
    p = produto(categoria, "KG")
    compra = svc.registrar(fornecedor.id, [item(p, "0,5", "0,05")])  # 0,025 -> 0,03
    assert compra.itens[0].subtotal == Decimal("0.03")
    assert compra.total == Decimal("0.03")


def test_aceita_virgula_e_milhar(fornecedor, categoria):
    p = produto(categoria)
    compra = svc.registrar(fornecedor.id, [item(p, "1", "1.234,56")])
    assert compra.total == Decimal("1234.56")


@pytest.mark.parametrize("fornecedor_id", [None, 0, 999])
def test_fornecedor_obrigatorio_e_existente(categoria, fornecedor_id):
    p = produto(categoria)
    with pytest.raises(ErroDeNegocio, match="fornecedor"):
        svc.registrar(fornecedor_id, [item(p, "1", "1")])
    assert total_registros() == (0, 0, 0)


def test_fornecedor_inativo_recusado(fornecedor, categoria):
    p = produto(categoria)
    fornecedor_service.alternar_ativo(fornecedor.id)
    with pytest.raises(ErroDeNegocio, match="inativo"):
        svc.registrar(fornecedor.id, [item(p, "1", "1")])


def test_sem_itens(fornecedor):
    with pytest.raises(ErroDeNegocio, match="ao menos um item"):
        svc.registrar(fornecedor.id, [])


def test_limite_de_itens(fornecedor, categoria):
    p = produto(categoria)
    with pytest.raises(ErroDeNegocio, match="no máximo"):
        svc.registrar(fornecedor.id, [item(p, "1", "1")] * (svc.MAX_ITENS + 1))


@pytest.mark.parametrize("produto_id", [None, "", "abc", 999])
def test_produto_invalido(fornecedor, produto_id):
    with pytest.raises(ErroDeNegocio, match="Item 1"):
        svc.registrar(fornecedor.id, [{"produto_id": produto_id, "quantidade": "1", "custo_unitario": "1"}])


def test_produto_inativo(fornecedor, categoria):
    p = produto(categoria)
    produto_service.alternar_ativo(p.id)
    with pytest.raises(ErroDeNegocio, match="inativo"):
        svc.registrar(fornecedor.id, [item(p, "1", "1")])


def test_produto_repetido(fornecedor, categoria):
    p = produto(categoria)
    with pytest.raises(ErroDeNegocio, match="já está na compra"):
        svc.registrar(fornecedor.id, [item(p, "1", "1"), item(p, "2", "1")])
    assert total_registros() == (0, 0, 0)


@pytest.mark.parametrize("qtd", ["", "0", "-1", "abc", "NaN", "1e3", "1,5", "10000000"])
def test_quantidade_invalida_para_unidade_inteira(fornecedor, categoria, qtd):
    p = produto(categoria)  # UN: só inteiros
    with pytest.raises(ErroDeNegocio):
        svc.registrar(fornecedor.id, [item(p, qtd, "1")])
    assert total_registros() == (0, 0, 0)


def test_quantidade_fracionada_ok_em_kg_mas_nao_com_4_casas(fornecedor, categoria):
    p = produto(categoria, "KG")
    svc.registrar(fornecedor.id, [item(p, "2,5", "1")])
    with pytest.raises(ErroDeNegocio, match="casas"):
        svc.registrar(fornecedor.id, [item(p, "1,2345", "1")])


@pytest.mark.parametrize("custo", ["", "0", "0,00", "-1", "abc", "1,234", "NaN", "100000000"])
def test_custo_invalido(fornecedor, categoria, custo):
    p = produto(categoria)
    with pytest.raises(ErroDeNegocio):
        svc.registrar(fornecedor.id, [item(p, "1", custo)])
    assert total_registros() == (0, 0, 0)


def test_subtotal_zerado_por_arredondamento(fornecedor, categoria):
    p = produto(categoria, "KG")
    with pytest.raises(ErroDeNegocio, match="zerado"):
        svc.registrar(fornecedor.id, [item(p, "0,001", "0,01")])  # 0,00001


def test_subtotal_e_total_grandes_demais(fornecedor, categoria):
    p = produto(categoria, "KG")
    with pytest.raises(ErroDeNegocio, match="grande demais"):
        svc.registrar(fornecedor.id, [item(p, "9999999,999", "99999999,99")])
    a = produto(categoria)
    b = produto(categoria)
    with pytest.raises(ErroDeNegocio, match="total da compra"):
        svc.registrar(fornecedor.id, [item(a, "1", "99999999,99"), item(b, "1", "1")])


def test_texto_opcional_longo_demais(fornecedor, categoria):
    p = produto(categoria)
    with pytest.raises(ErroDeNegocio, match="documento"):
        svc.registrar(fornecedor.id, [item(p, "1", "1")], numero_documento="n" * 31)
    with pytest.raises(ErroDeNegocio, match="observação"):
        svc.registrar(fornecedor.id, [item(p, "1", "1")], observacao="o" * 256)


def test_atomicidade_segundo_item_invalido_nao_altera_o_primeiro(fornecedor, categoria):
    a = produto(categoria)
    b = produto(categoria)
    with pytest.raises(ErroDeNegocio, match="Item 2"):
        svc.registrar(fornecedor.id, [item(a, "10", "3"), item(b, "0", "3")])
    db.session.refresh(a)
    assert a.quantidade_estoque == 0
    assert a.preco_custo == Decimal("4.50")
    assert total_registros() == (0, 0, 0)


def test_falha_no_meio_da_gravacao_desfaz_tudo(fornecedor, categoria, monkeypatch):
    """Se a entrada do 2º produto falhar já com o 1º gravado, nada pode ficar."""
    a = produto(categoria)
    b = produto(categoria)
    original = estoque_service.entrada

    def falha_no_segundo(produto_id, *args, **kwargs):
        if produto_id == b.id:
            raise ErroDeNegocio("falha simulada")
        return original(produto_id, *args, **kwargs)

    monkeypatch.setattr(estoque_service, "entrada", falha_no_segundo)
    with pytest.raises(ErroDeNegocio, match="falha simulada"):
        svc.registrar(fornecedor.id, [item(a, "10", "3"), item(b, "5", "3")])
    db.session.refresh(a)
    assert a.quantidade_estoque == 0 and a.preco_custo == Decimal("4.50")
    assert total_registros() == (0, 0, 0)


def test_erro_inesperado_tambem_faz_rollback(fornecedor, categoria, monkeypatch):
    a = produto(categoria)

    def explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(estoque_service, "entrada", explode)
    with pytest.raises(RuntimeError):
        svc.registrar(fornecedor.id, [item(a, "10", "3")])
    assert total_registros() == (0, 0, 0)


def test_saldo_alem_do_limite_recusa_e_desfaz(fornecedor, categoria):
    p = produto(categoria, "KG")
    estoque_service.entrada(p.id, "9999999", "Saldo")
    with pytest.raises(ErroDeNegocio, match="limite"):
        svc.registrar(fornecedor.id, [item(p, "5", "1")])
    db.session.refresh(p)
    assert p.quantidade_estoque == Decimal("9999999")
    assert total_registros() == (0, 0, 1)  # só a entrada de "Saldo"


def test_token_repetido_nao_duplica(fornecedor, categoria):
    p = produto(categoria)
    token = str(uuid.uuid4())
    primeira = svc.registrar(fornecedor.id, [item(p, "10", "3")], token_envio=token)
    with pytest.raises(ErroDeNegocio, match="já foi registrada"):
        svc.registrar(fornecedor.id, [item(p, "10", "3")], token_envio=token)
    db.session.refresh(p)
    assert p.quantidade_estoque == Decimal("10")  # entrou uma vez só
    assert svc.compra_por_token(token).id == primeira.id
    assert total_registros() == (1, 1, 1)


def test_corrida_de_token_vira_erro_amigavel_e_desfaz(fornecedor, categoria, monkeypatch):
    """Duas requisições passam pela checagem prévia; o UNIQUE do banco barra a segunda."""
    p = produto(categoria)
    token = str(uuid.uuid4())
    svc.registrar(fornecedor.id, [item(p, "10", "3")], token_envio=token)
    consultas = iter([None, None])  # a checagem prévia "não enxerga" a 1ª compra
    real = svc.compra_por_token
    monkeypatch.setattr(svc, "compra_por_token", lambda t: next(consultas, None) or real(t))
    with pytest.raises(ErroDeNegocio, match="já foi registrada"):
        svc.registrar(fornecedor.id, [item(p, "10", "3")], token_envio=token)
    db.session.refresh(p)
    assert p.quantidade_estoque == Decimal("10")
    assert total_registros() == (1, 1, 1)


def test_compra_por_token_sem_token(app):
    assert svc.compra_por_token(None) is None
    assert svc.compra_por_token("") is None


def test_buscar_e_listar_com_filtros(fornecedor, categoria):
    outro = fornecedor_service.criar("Padaria")
    p = produto(categoria)
    c1 = svc.registrar(fornecedor.id, [item(p, "1", "2")])
    c2 = svc.registrar(outro.id, [item(p, "1", "3")])
    assert svc.buscar(c1.id).fornecedor.nome == "Distribuidora Bom Preço"
    assert [c.id for c in svc.listar()] == [c2.id, c1.id]  # mais recente primeiro
    assert [c.id for c in svc.listar(fornecedor_id=outro.id)] == [c2.id]
    hoje = c1.data_hora.date()
    assert len(svc.listar(hoje, hoje)) == 2
    from datetime import timedelta

    assert svc.listar(hoje + timedelta(days=2), hoje + timedelta(days=3)) == []
    with pytest.raises(ErroDeNegocio, match="data inicial"):
        svc.listar(hoje + timedelta(days=1), hoje)
    with pytest.raises(ErroDeNegocio, match="não encontrada"):
        svc.buscar(999)


def test_banco_barra_item_invalido_sem_passar_pelo_service(fornecedor, categoria):
    from sqlalchemy.exc import IntegrityError

    p = produto(categoria)
    c = svc.registrar(fornecedor.id, [item(p, "1", "1")])
    db.session.add(ItemCompra(compra_id=c.id, produto_id=p.id, quantidade=1, custo_unitario=1, subtotal=1))
    with pytest.raises(IntegrityError):  # produto repetido na mesma compra
        db.session.commit()
    db.session.rollback()
    db.session.add(Compra(fornecedor_id=fornecedor.id, total=0))
    with pytest.raises(IntegrityError):  # total deve ser > 0
        db.session.commit()
    db.session.rollback()
