"""Fase 9 — recuperação de desastre, do jeito que acontece de verdade.

Cenários: o banco some, o banco corrompe, o banco fica errado (apagaram dados). Em todos, o caminho é o
mesmo: restaurar.py a partir do último backup, e o sistema volta com login e dados.
"""
import os
import sqlite3
from datetime import date
from decimal import Decimal

import pytest

import restaurar
from app import create_app, migracoes
from app.extensions import db
from app.models import Lancamento, Produto, Usuario, Venda
from app.services import (backup_service, categoria_service, estoque_service, financeiro_service,
                          produto_service, usuario_service, venda_service)
from config import TestConfig

SENHA = "senha-segura-123"


class _Cfg(TestConfig):
    pass


def _config(tmp_path):
    _Cfg.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'mg.db'}"
    _Cfg.BACKUP_DIR = str(tmp_path / "backups")
    return _Cfg


def _abrir(tmp_path):
    app = create_app(_config(tmp_path))
    ctx = app.app_context()
    ctx.push()
    db.create_all()
    migracoes.aplicar()
    return app, ctx


def _fechar(ctx):
    db.session.remove()
    db.engine.dispose()
    ctx.pop()


def _popular():
    usuario_service.criar_primeiro_dono("Dona Talya", "talya", SENHA)
    cat = categoria_service.criar("Mercearia")
    p = produto_service.criar({"categoria_id": cat.id, "nome": "Arroz 5kg", "codigo": "A1", "unidade_medida": "UN",
                               "preco_custo": "20", "preco_venda": "29,90", "estoque_minimo": "2"})
    estoque_service.entrada(p.id, "10", "Inicial")
    venda_service.finalizar({p.id: Decimal("3")}, None, "PIX")
    financeiro_service.criar("DESPESA", "ALUGUEL", "Aluguel", "1800", date(2026, 11, 10))


def _conferir_dados(app):
    """O sistema voltou: login funciona e os dados estão lá."""
    assert Usuario.query.count() == 1 and Produto.query.one().quantidade_estoque == Decimal("7")
    assert Venda.query.count() == 1 and Lancamento.query.count() == 1
    c = app.test_client()
    r = c.post("/login", data={"login": "talya", "senha": SENHA}, follow_redirects=True)
    assert r.status_code == 200 and "Arroz" in c.get("/produtos/").get_data(as_text=True)
    assert "Aluguel" in c.get("/financeiro/").get_data(as_text=True)


def _caminho_banco(tmp_path):
    return str(tmp_path / "mg.db")


def test_banco_apagado_volta_pelo_ultimo_backup(tmp_path):
    app, ctx = _abrir(tmp_path)
    _popular()
    nome = backup_service.criar_backup()
    _fechar(ctx)

    os.remove(_caminho_banco(tmp_path))                                   # desastre: o arquivo sumiu
    backup = os.path.join(str(tmp_path / "backups"), nome)
    assert restaurar.main([backup], _config(tmp_path)) == 0

    app, ctx = _abrir(tmp_path)                                           # reinicia o sistema
    try:
        _conferir_dados(app)
    finally:
        _fechar(ctx)


def test_banco_corrompido_volta_e_o_corrompido_fica_guardado(tmp_path):
    app, ctx = _abrir(tmp_path)
    _popular()
    nome = backup_service.criar_backup()
    _fechar(ctx)

    banco = _caminho_banco(tmp_path)
    with open(banco, "r+b") as f:                                         # desastre: bytes estragados no meio
        f.seek(2048)
        f.write(b"\x00LIXO" * 400)
    assert restaurar.main([os.path.join(str(tmp_path / "backups"), nome)], _config(tmp_path)) == 0

    guardados = [n for n in os.listdir(tmp_path) if "antes-da-restauracao" in n]
    assert len(guardados) == 1                                            # nada foi apagado às cegas
    app, ctx = _abrir(tmp_path)
    try:
        _conferir_dados(app)
    finally:
        _fechar(ctx)


def test_dados_apagados_por_engano_voltam_e_o_estado_errado_fica_guardado(tmp_path):
    app, ctx = _abrir(tmp_path)
    _popular()
    nome = backup_service.criar_backup()
    Lancamento.query.delete()                                             # "apaguei o financeiro sem querer"
    db.session.commit()
    _fechar(ctx)

    assert restaurar.main([os.path.join(str(tmp_path / "backups"), nome)], _config(tmp_path)) == 0
    app, ctx = _abrir(tmp_path)
    try:
        _conferir_dados(app)
    finally:
        _fechar(ctx)
    guardado = next(n for n in os.listdir(tmp_path) if "antes-da-restauracao" in n)
    con = sqlite3.connect(tmp_path / guardado)
    assert con.execute("SELECT COUNT(*) FROM lancamento").fetchone()[0] == 0  # o estado "errado" não se perdeu
    con.close()


def test_backup_feito_antes_da_v012_e_restaurado_e_migrado(tmp_path):
    """Backup de uma versão antiga (sem usuario_id nas tabelas) restaura e o sistema o atualiza sozinho."""
    app, ctx = _abrir(tmp_path)
    _popular()
    nome = backup_service.criar_backup()
    _fechar(ctx)
    backup = os.path.join(str(tmp_path / "backups"), nome)

    from tests.test_auditoria import TABELAS_ALVO
    con = sqlite3.connect(backup)                                         # envelhece o backup: tira usuario_id
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute("PRAGMA legacy_alter_table=ON")
    import re
    for t in TABELAS_ALVO:
        ddl = con.execute("SELECT sql FROM sqlite_master WHERE name=?", (t,)).fetchone()[0]
        ddl = re.sub(r"\n\s*usuario_id INTEGER,", "", ddl)
        ddl = re.sub(r",\s*FOREIGN KEY\(usuario_id\) REFERENCES usuario \(id\)", "", ddl)
        cols = ", ".join(r[1] for r in con.execute(f'PRAGMA table_info("{t}")') if r[1] != "usuario_id")
        con.execute(f'ALTER TABLE "{t}" RENAME TO "{t}_velha"')
        con.execute(ddl)
        con.execute(f'INSERT INTO "{t}" ({cols}) SELECT {cols} FROM "{t}_velha"')
        con.execute(f'DROP TABLE "{t}_velha"')
    con.commit()
    con.close()

    os.remove(_caminho_banco(tmp_path))
    assert restaurar.main([backup], _config(tmp_path)) == 0
    app, ctx = _abrir(tmp_path)                                           # o arranque migra o que faltava
    try:
        assert migracoes.pendentes() == []
        _conferir_dados(app)
    finally:
        _fechar(ctx)


def test_restaurar_com_arquivo_ruim_nao_destroi_o_banco_que_funciona(tmp_path):
    app, ctx = _abrir(tmp_path)
    _popular()
    _fechar(ctx)
    ruim = tmp_path / "pendrive-lixo.db"
    ruim.write_bytes(b"isto nao e um banco" * 200)
    antes = open(_caminho_banco(tmp_path), "rb").read()
    assert restaurar.main([str(ruim)], _config(tmp_path)) == 1
    assert open(_caminho_banco(tmp_path), "rb").read() == antes           # o banco bom continua intacto
    app, ctx = _abrir(tmp_path)
    try:
        _conferir_dados(app)
    finally:
        _fechar(ctx)


def test_backup_baixado_de_outro_lugar_serve_para_restaurar(tmp_path):
    """O fluxo do pen drive: backup copiado para fora de instance/ e restaurado de lá."""
    import shutil
    app, ctx = _abrir(tmp_path)
    _popular()
    nome = backup_service.criar_backup()
    _fechar(ctx)
    pendrive = tmp_path / "pendrive"
    pendrive.mkdir()
    copia = pendrive / nome
    shutil.copy2(os.path.join(str(tmp_path / "backups"), nome), copia)
    os.remove(_caminho_banco(tmp_path))
    assert restaurar.main([str(copia)], _config(tmp_path)) == 0
    app, ctx = _abrir(tmp_path)
    try:
        _conferir_dados(app)
    finally:
        _fechar(ctx)
