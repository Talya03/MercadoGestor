"""v0.12 — Auditoria (quem fez) e migração segura do banco existente.

Regras testadas (RN67 em diante):
- o autor vem SEMPRE da sessão, nunca de campo do formulário (anti-falsificação);
- registros antigos (sem autor) continuam funcionando e aparecem com "—";
- a migração acrescenta as colunas sem perder dados, é idempotente e faz cópia de segurança.
"""
import glob
import re
import sqlite3
import uuid
from datetime import date
from decimal import Decimal
from itertools import count

import pytest

from app import create_app, migracoes
from app.extensions import db
from app.models import Compra, Lancamento, MovimentacaoEstoque, Venda
from app.services import (categoria_service, compra_service, estoque_service, financeiro_service,
                          fornecedor_service, produto_service, venda_service)
from config import TestConfig
from tests.conftest import criar_usuario, entrar

_n = count(1)


@pytest.fixture
def produto(app):
    cat = categoria_service.criar("Mercearia")
    p = produto_service.criar({
        "categoria_id": cat.id, "nome": "Arroz 5kg", "codigo": f"A{next(_n)}", "unidade_medida": "UN",
        "preco_custo": "20,00", "preco_venda": "29,90", "estoque_minimo": "2",
    })
    estoque_service.entrada(p.id, "50", "Estoque inicial")
    return p


@pytest.fixture
def fornecedor(app):
    return fornecedor_service.criar("Distribuidora Bom Preço", "12345678000190")


@pytest.fixture
def ana(app):
    return criar_usuario("CAIXA", login="ana", nome="Ana Caixa")


def _html(r):
    return r.get_data(as_text=True)


def _item(produto, qtd="5", custo="21"):
    return {"produto_id": produto.id, "quantidade": qtd, "custo_unitario": custo}


# ------------------------------------------------------------------ serviços
def test_venda_guarda_o_operador_e_a_baixa_de_estoque_tambem(produto, ana):
    venda = venda_service.finalizar({produto.id: Decimal("2")}, None, "PIX", usuario_id=ana.id)
    assert venda.usuario_id == ana.id and venda.usuario.nome == "Ana Caixa"
    baixa = MovimentacaoEstoque.query.filter_by(tipo="SAIDA").one()
    assert baixa.usuario_id == ana.id


def test_compra_guarda_autor_na_compra_na_entrada_e_no_lancamento(produto, fornecedor, ana):
    c = compra_service.registrar(fornecedor.id, [_item(produto)], usuario_id=ana.id)
    assert c.usuario_id == ana.id
    assert Lancamento.query.one().usuario_id == ana.id
    entrada = MovimentacaoEstoque.query.filter_by(tipo="ENTRADA").order_by(MovimentacaoEstoque.id.desc()).first()
    assert entrada.usuario_id == ana.id


def test_ajuste_e_lancamento_guardam_autor(produto, ana):
    m = estoque_service.ajuste(produto.id, "40", "Contagem", usuario_id=ana.id)
    assert m.usuario_id == ana.id
    l = financeiro_service.criar("DESPESA", "ALUGUEL", "Aluguel", "100", date(2026, 11, 10), usuario_id=ana.id)
    assert l.usuario_id == ana.id


def test_servicos_sem_usuario_continuam_funcionando(produto):
    """Compatibilidade: usuario_id é opcional (rotinas e dados antigos)."""
    assert estoque_service.entrada(produto.id, "3", "sem autor").usuario_id is None
    assert financeiro_service.criar("DESPESA", "ALUGUEL", "x", "10", date(2026, 11, 10)).usuario_id is None
    assert venda_service.finalizar({produto.id: Decimal("1")}, None, "PIX").usuario_id is None


def test_falha_na_venda_nao_deixa_rastro_de_autor(produto, ana):
    with pytest.raises(Exception):
        venda_service.finalizar({produto.id: Decimal("999")}, None, "PIX", usuario_id=ana.id)
    db.session.rollback()
    assert Venda.query.count() == 0
    assert MovimentacaoEstoque.query.filter(MovimentacaoEstoque.usuario_id == ana.id).count() == 0


# -------------------------------------------------------------------- rotas
def _token(client):
    return re.search(r'name="token" value="([0-9a-f-]{36})"', _html(client.get("/pdv/"))).group(1)


def test_autor_vem_da_sessao_e_campo_usuario_id_do_formulario_e_ignorado(client, produto, ana):
    """RN67: quem está logado (DONO) é o autor, mesmo que o formulário tente indicar a Ana."""
    dono = db.session.query(Venda).count()  # 0, só para lembrar que parte vazio
    assert dono == 0
    client.post("/pdv/adicionar", data={"produto_id": str(produto.id), "quantidade": "1"})
    client.post("/pdv/finalizar", data={"forma": "PIX", "valor_recebido": "", "token": _token(client),
                                        "usuario_id": str(ana.id)}, follow_redirects=True)
    venda = Venda.query.one()
    assert venda.usuario_id is not None and venda.usuario_id != ana.id
    assert venda.usuario.perfil == "DONO"


def test_ajuste_pela_tela_usa_o_usuario_logado_e_ignora_o_formulario(client, produto, ana):
    client.post("/estoque/entrada", data={"produto_id": str(produto.id), "quantidade": "4",
                                          "motivo": "Reposição", "usuario_id": str(ana.id)})
    m = MovimentacaoEstoque.query.filter_by(motivo="Reposição").one()
    assert m.usuario_id != ana.id and m.usuario.perfil == "DONO"


def test_lancamento_e_compra_pela_tela_ignoram_usuario_id_forjado(client, produto, fornecedor, ana):
    client.post("/financeiro/novo", data={"tipo": "DESPESA", "categoria": "ALUGUEL", "descricao": "Aluguel",
                                          "valor": "100", "data": "2026-11-10", "usuario_id": str(ana.id)})
    assert Lancamento.query.one().usuario_id != ana.id
    client.post("/compras/nova", data={
        "token": str(uuid.uuid4()), "fornecedor_id": str(fornecedor.id), "numero_documento": "NF 9",
        "produto_id": [str(produto.id)], "quantidade": ["2"], "custo_unitario": ["21"],
        "usuario_id": str(ana.id)})
    assert Compra.query.one().usuario_id != ana.id


def test_caixa_logada_aparece_como_operadora_na_lista_e_no_comprovante(app, produto):
    from tests.conftest import entrar as _entrar
    caixa = app.test_client()
    _entrar(caixa, "CAIXA", login="maria", nome="Maria da Silva")
    caixa.post("/pdv/adicionar", data={"produto_id": str(produto.id), "quantidade": "1"})
    caixa.post("/pdv/finalizar", data={"forma": "PIX", "valor_recebido": "", "token": _token(caixa)})
    venda = Venda.query.one()
    assert "Operador: Maria da Silva" in _html(caixa.get(f"/pdv/vendas/{venda.id}"))


def test_registros_antigos_sem_autor_aparecem_com_travessao(client, produto):
    venda = venda_service.finalizar({produto.id: Decimal("1")}, None, "PIX")
    assert "Operador: —" in _html(client.get(f"/pdv/vendas/{venda.id}"))
    assert "<th>Operador</th>" in _html(client.get("/pdv/vendas"))
    assert "<th>Por</th>" in _html(client.get("/estoque/historico"))


def test_nome_do_autor_e_escapado(app, client, produto):
    outro = criar_usuario("CAIXA", login="xss", nome="<script>alert(1)</script>")
    venda_service.finalizar({produto.id: Decimal("1")}, None, "PIX", usuario_id=outro.id)
    corpo = _html(client.get("/pdv/vendas"))
    assert "<script>alert(1)" not in corpo and "&lt;script&gt;" in corpo


def test_listas_de_compras_e_financeiro_mostram_autor(client, produto, fornecedor, ana):
    compra_service.registrar(fornecedor.id, [_item(produto)], usuario_id=ana.id)
    financeiro_service.criar("DESPESA", "ALUGUEL", "Aluguel", "100", date(2026, 11, 10), usuario_id=ana.id)
    assert "Ana Caixa" in _html(client.get("/compras/"))
    assert "Ana Caixa" in _html(client.get(f"/compras/{Compra.query.one().id}"))
    assert "Ana Caixa" in _html(client.get("/financeiro/"))


# ----------------------------------------------------------------- migração
TABELAS_ALVO = ("venda", "movimentacao_estoque", "compra", "lancamento")


def _criar_banco_antigo(caminho):
    """Gera um banco no formato da v0.10: tabelas SEM usuario_id, com dados reais dentro."""
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        cat = categoria_service.criar("Bebidas")
        p = produto_service.criar({"categoria_id": cat.id, "nome": "Guaraná 2L", "codigo": "G2",
                                  "unidade_medida": "UN", "preco_custo": "5", "preco_venda": "9",
                                  "estoque_minimo": "1"})
        estoque_service.entrada(p.id, "10", "Inicial")
        venda_service.finalizar({p.id: Decimal("2")}, None, "PIX")
        financeiro_service.criar("DESPESA", "ALUGUEL", "Aluguel", "100", date(2026, 11, 10))
        compra_service.registrar(fornecedor_service.criar("Forn", "12345678000190").id,
                                 [{"produto_id": p.id, "quantidade": "3", "custo_unitario": "5"}])
        origem = db.engine.raw_connection()
        destino = sqlite3.connect(caminho)
        origem.driver_connection.backup(destino)  # copia o banco em memória para arquivo
        destino.close()
        db.session.remove()
        db.drop_all()
    con = sqlite3.connect(caminho)
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute("PRAGMA legacy_alter_table=ON")  # RENAME não deve reescrever as FKs das tabelas filhas
    for t in TABELAS_ALVO:  # reconstrói a tabela sem a coluna nova, como era na versão antiga
        ddl = con.execute("SELECT sql FROM sqlite_master WHERE name=?", (t,)).fetchone()[0]
        ddl = re.sub(r"\n\s*usuario_id INTEGER,", "", ddl)
        ddl = re.sub(r",\s*FOREIGN KEY\(usuario_id\) REFERENCES usuario \(id\)", "", ddl)
        assert "usuario_id" not in ddl
        antigas = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")') if r[1] != "usuario_id"]
        lista = ", ".join(antigas)
        con.execute(f'ALTER TABLE "{t}" RENAME TO "{t}_velha"')
        con.execute(ddl)
        con.execute(f'INSERT INTO "{t}" ({lista}) SELECT {lista} FROM "{t}_velha"')
        con.execute(f'DROP TABLE "{t}_velha"')
    con.execute("DROP TABLE usuario")
    con.commit()
    con.close()


class _ConfigArquivo(TestConfig):
    pass


@pytest.fixture
def app_antigo(tmp_path):
    caminho = str(tmp_path / "antigo.db")
    _criar_banco_antigo(caminho)
    _ConfigArquivo.SQLALCHEMY_DATABASE_URI = f"sqlite:///{caminho}"
    app = create_app(_ConfigArquivo)
    with app.app_context():
        yield app, caminho
        db.session.remove()
        db.engine.dispose()


def _cols(caminho, tabela):
    con = sqlite3.connect(caminho)
    try:
        return {r[1] for r in con.execute(f'PRAGMA table_info("{tabela}")')}
    finally:
        con.close()


def test_migracao_acrescenta_colunas_preserva_dados_e_cria_copia(app_antigo):
    app, caminho = app_antigo
    db.create_all()  # como o run.py: cria só a tabela usuario que faltava
    assert {t for t, _, _ in migracoes.pendentes()} == set(TABELAS_ALVO)
    feitas = migracoes.aplicar()
    assert sorted(t for t, _ in feitas) == sorted(TABELAS_ALVO)
    for t in TABELAS_ALVO:
        assert "usuario_id" in _cols(caminho, t)
    # dados antigos intactos, sem autor inventado
    assert Venda.query.count() == 1 and Venda.query.one().usuario_id is None
    assert Lancamento.query.count() >= 1 and Compra.query.count() == 1
    assert len(glob.glob(caminho + ".antes-da-migracao-*")) == 1


def test_migracao_e_idempotente_e_nao_refaz_copia(app_antigo):
    app, caminho = app_antigo
    db.create_all()
    migracoes.aplicar()
    assert migracoes.pendentes() == []
    assert migracoes.aplicar() == []
    assert len(glob.glob(caminho + ".antes-da-migracao-*")) == 1


def test_sistema_funciona_com_autor_depois_de_migrar(app_antigo):
    app, caminho = app_antigo
    db.create_all()
    migracoes.aplicar()
    cliente = app.test_client()
    usuario = entrar(cliente, "DONO")
    assert cliente.get("/pdv/vendas").status_code == 200
    assert "Operador" in _html(cliente.get("/pdv/vendas"))
    p = produto_service.listar()[0] if hasattr(produto_service, "listar") else None
    assert p is not None
    venda = venda_service.finalizar({p.id: Decimal("1")}, None, "PIX", usuario_id=usuario.id)
    assert venda.usuario_id == usuario.id


def test_sem_migrar_o_banco_antigo_falha_e_por_isso_a_migracao_existe(app_antigo):
    app, _ = app_antigo
    db.create_all()
    with pytest.raises(Exception):
        Venda.query.all()
    db.session.rollback()


def test_banco_em_memoria_nao_gera_copia_e_banco_atualizado_nao_tem_pendencias(app):
    assert migracoes.pendentes() == []
    assert migracoes._caminho_do_banco() is None
    assert migracoes.aplicar() == []
