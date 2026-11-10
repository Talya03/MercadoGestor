"""Testes das telas de relatórios, do CSV e da página inicial (painel)."""
import csv
import io
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import count

import pytest

from app.extensions import db
from app.services import categoria_service, estoque_service, financeiro_service, produto_service, venda_service
from app.utils.csv_export import gerar_csv
from app.utils.hoje import hoje_local

D = Decimal
_n = count(1)
PERIODO = "de=2026-11-01&ate=2026-11-30"


def html(r):
    return r.get_data(as_text=True)


def linhas_csv(resposta):
    texto = resposta.get_data(as_text=True)
    assert texto.startswith("﻿")  # BOM para o Excel acertar os acentos
    return list(csv.reader(io.StringIO(texto.lstrip("﻿")), delimiter=";"))


@pytest.fixture
def vendas(app):
    cat = categoria_service.criar("Mercearia")
    criados = []
    for nome, venda, custo in (("Leite 1L", "6,99", "4,50"), ("=CMD|calc", "10", "4")):
        p = produto_service.criar({"categoria_id": cat.id, "nome": nome, "codigo": f"R{next(_n)}",
                                   "unidade_medida": "UN", "preco_custo": custo, "preco_venda": venda,
                                   "estoque_minimo": "5"})
        estoque_service.entrada(p.id, "500", "Estoque inicial")
        criados.append(p)
    leite, esquisito = criados
    for itens, quando, forma, desc in (
        ({leite: 10, esquisito: 2}, datetime(2026, 11, 10, 15), "PIX", ("PERCENTUAL", "10")),
        ({leite: 5}, datetime(2026, 11, 12, 15), "DINHEIRO", None),
    ):
        v = venda_service.finalizar({p.id: D(q) for p, q in itens.items()}, desc, forma,
                                    "100" if forma == "DINHEIRO" else None, str(uuid.uuid4()))
        v.data_hora = quando
        db.session.commit()
    return leite, esquisito


def test_indice_e_paginas_abrem_sem_dados(client):
    for url in ("/relatorios/", "/relatorios/produtos", "/relatorios/pagamentos", "/relatorios/dias"):
        r = client.get(url)
        assert r.status_code == 200
    assert "Nenhuma venda neste período" in html(client.get("/relatorios/dias"))


def test_produtos_mostra_valores_formatados(client, vendas):
    corpo = html(client.get(f"/relatorios/produtos?{PERIODO}"))
    assert "Leite 1L" in corpo and "15 UN" in corpo
    assert "R$ 104,85" in corpo and "R$ 67,50" in corpo and "R$ 37,35" in corpo and "35,6%" in corpo


def test_ordem_invalida_e_ignorada(client, vendas):
    assert client.get(f"/relatorios/produtos?{PERIODO}&ordem=hack").status_code == 200
    corpo = html(client.get(f"/relatorios/produtos?{PERIODO}&ordem=lucro"))
    assert 'value="lucro" selected' in corpo


def test_pagamentos_e_dias(client, vendas):
    corpo = html(client.get(f"/relatorios/pagamentos?{PERIODO}"))
    assert "Pix" in corpo and "Dinheiro" in corpo
    corpo = html(client.get(f"/relatorios/dias?{PERIODO}"))
    assert "10/11/2026" in corpo and "12/11/2026" in corpo


def test_periodo_invalido_mostra_aviso_e_usa_mes_atual(client):
    for url in ("/relatorios/dias?de=lixo&ate=2026-01-01", "/relatorios/dias?de=2026-02-01&ate=2026-01-01",
                "/relatorios/dias?de=2020-01-01&ate=2026-01-01", "/relatorios/dias?de=2026-01-01"):
        r = client.get(url)
        assert r.status_code == 200 and "Mostrando o mês atual" in html(r)


def test_periodo_ausente_nao_gera_aviso(client):
    assert "Mostrando o mês atual" not in html(client.get("/relatorios/dias"))


def test_texto_do_produto_e_escapado_na_tela(client, vendas):
    corpo = html(client.get(f"/relatorios/produtos?{PERIODO}"))
    assert "=CMD|calc" in corpo  # na tela é só texto; o perigo é no CSV


# ------------------------------------------------------------------- CSV
def test_csv_produtos_formato_brasileiro(client, vendas):
    r = client.get(f"/relatorios/produtos?{PERIODO}&formato=csv")
    assert r.mimetype == "text/csv"
    assert 'attachment; filename="produtos-vendidos_2026-11-01_2026-11-30.csv"' in r.headers["Content-Disposition"]
    linhas = linhas_csv(r)
    assert linhas[0] == ["Código", "Produto", "Unidade", "Quantidade", "Receita", "Custo", "Lucro", "Margem %"]
    leite = next(l for l in linhas if l[1] == "Leite 1L")
    assert leite[3:] == ["15", "104,85", "67,50", "37,35", "35,6"]  # vírgula decimal, sem milhar


def test_csv_neutraliza_formula_em_texto(client, vendas):
    linhas = linhas_csv(client.get(f"/relatorios/produtos?{PERIODO}&formato=csv"))
    nomes = [l[1] for l in linhas[1:]]
    assert "'=CMD|calc" in nomes and "=CMD|calc" not in nomes


@pytest.mark.parametrize("texto", ["=1+1", "+1", "-1", "@SOMA(A1)", "\tx", "\rx"])
def test_csv_protege_todos_os_prefixos_perigosos(texto):
    saida = gerar_csv([("Nome", "texto")], [[texto]])
    assert saida.split("\r\n")[1].lstrip('"').startswith("'")


def test_csv_titulo_perigoso_tambem_e_neutralizado():
    assert gerar_csv([("=x", "texto")], []).lstrip("﻿").startswith("'=x")


def test_csv_texto_normal_e_aspas_e_separador_dentro_do_texto():
    saida = gerar_csv([("Nome", "texto")], [['Leite; "integral"'], ["Pão"], [None]])
    linhas = list(csv.reader(io.StringIO(saida.lstrip("﻿")), delimiter=";"))
    assert linhas == [["Nome"], ['Leite; "integral"'], ["Pão"], [""]]


def test_csv_tipos_numericos_e_vazios():
    cols = [("m", "moeda"), ("q", "qtd"), ("p", "pct"), ("i", "inteiro"), ("d", "data")]
    saida = gerar_csv(cols, [[D("1234.5"), D("2.500"), D("-12.34"), 3, datetime(2026, 11, 5).date()],
                              [None, None, None, None, None]])
    linhas = list(csv.reader(io.StringIO(saida.lstrip("﻿")), delimiter=";"))
    assert linhas[1] == ["1234,50", "2,5", "-12,3", "3", "05/11/2026"]
    assert linhas[2] == ["", "", "", "", ""]


def test_csv_tipo_desconhecido_e_erro_de_programacao():
    with pytest.raises(ValueError):
        gerar_csv([("x", "magia")], [[1]])


def test_csv_pagamentos_e_dias(client, vendas):
    pag = linhas_csv(client.get(f"/relatorios/pagamentos?{PERIODO}&formato=csv"))
    assert pag[0] == ["Forma de pagamento", "Pagamentos", "Valor"]
    assert {l[0]: l[2] for l in pag[1:]} == {"Pix": "80,91", "Dinheiro": "34,95"}  # 89,90 - 10% (8,99) ; 5 x 6,99
    dias = linhas_csv(client.get(f"/relatorios/dias?{PERIODO}&formato=csv"))
    assert dias[0] == ["Data", "Vendas", "Desconto", "Total", "Ticket médio"]
    assert dias[1][0] == "10/11/2026" and dias[2][0] == "12/11/2026"


def test_csv_vazio_so_tem_cabecalho(client):
    assert len(linhas_csv(client.get(f"/relatorios/dias?{PERIODO}&formato=csv"))) == 1


def test_csv_com_periodo_invalido_nao_deixa_aviso_preso(client):
    r = client.get("/relatorios/dias?de=lixo&ate=lixo&formato=csv")
    assert r.status_code == 200 and r.mimetype == "text/csv"
    assert "Mostrando o mês atual" not in html(client.get("/"))
    assert "Mostrando o mês atual" not in html(client.get("/relatorios/dias"))


def test_relatorios_so_leem_dados(client, vendas):
    for url in ("/relatorios/produtos", "/relatorios/pagamentos", "/relatorios/dias"):
        assert client.post(url, data={}).status_code == 405


# -------------------------------------------------------- página inicial
def test_inicio_vazio(client):
    corpo = html(client.get("/"))
    assert "Nenhuma venda ainda hoje" in corpo and "Nenhum produto com estoque baixo" in corpo
    assert "Nenhuma conta vencida" in corpo


def test_inicio_com_dados(client, app):
    cat = categoria_service.criar("X")
    p = produto_service.criar({"categoria_id": cat.id, "nome": "Sabão <b>", "codigo": "S1", "unidade_medida": "UN",
                               "preco_custo": "1", "preco_venda": "2", "estoque_minimo": "10"})
    estoque_service.entrada(p.id, "3", "Saldo")
    financeiro_service.criar("DESPESA", "ALUGUEL", "Aluguel <i>", "1800", hoje_local() - timedelta(days=1))
    corpo = html(client.get("/"))
    assert "1 produto" in corpo and "Sabão &lt;b&gt;" in corpo and "Sabão <b>" not in corpo
    assert "Aluguel &lt;i&gt;" in corpo and "Vencida" in corpo and "R$ 1.800,00" in corpo


def test_inicio_mostra_venda_de_hoje(client, app):
    cat = categoria_service.criar("X")
    p = produto_service.criar({"categoria_id": cat.id, "nome": "Leite", "codigo": "L1", "unidade_medida": "UN",
                               "preco_custo": "4", "preco_venda": "10", "estoque_minimo": "1"})
    estoque_service.entrada(p.id, "50", "Saldo")
    venda_service.finalizar({p.id: D("3")}, None, "PIX", None, str(uuid.uuid4()))
    corpo = html(client.get("/"))
    assert "R$ 30,00" in corpo and "1 venda" in corpo and "ticket médio R$ 30,00" in corpo
