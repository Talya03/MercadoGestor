"""v0.13 — Backup e restauração (RN72–RN76)."""
import os
import sqlite3
import stat
from datetime import date

import pytest

from app import create_app
from app.extensions import db
from app.models import Produto
from app.services import backup_service as svc
from app.services import categoria_service, estoque_service, financeiro_service, produto_service
from app.utils.erros import ErroDeNegocio
from config import TestConfig
from tests.conftest import criar_usuario, entrar


class _Arquivo(TestConfig):
    BACKUP_MANTER = 3


@pytest.fixture
def app_arquivo(tmp_path):
    """App com banco em ARQUIVO (backup não funciona com banco em memória)."""
    banco = tmp_path / "mg.db"
    _Arquivo.SQLALCHEMY_DATABASE_URI = f"sqlite:///{banco}"
    _Arquivo.BACKUP_DIR = str(tmp_path / "backups")
    app = create_app(_Arquivo)
    with app.app_context():
        db.create_all()
        cat = categoria_service.criar("Mercearia")
        produto_service.criar({"categoria_id": cat.id, "nome": "Feijão 1kg", "codigo": "F1",
                               "unidade_medida": "UN", "preco_custo": "5", "preco_venda": "8",
                               "estoque_minimo": "1"})
        yield app, str(banco)
        db.session.remove()
        db.engine.dispose()


def _nomes_de_produto(caminho):
    con = sqlite3.connect(caminho)
    try:
        return [r[0] for r in con.execute("SELECT nome FROM produto ORDER BY id")]
    finally:
        con.close()


def test_backup_cria_copia_fiel_verificada_e_privada(app_arquivo):
    app, banco = app_arquivo
    nome = svc.criar_backup()
    caminho = svc.caminho_do_backup(nome)
    assert _nomes_de_produto(caminho) == ["Feijão 1kg"]
    if os.name == "posix":  # permissões estilo Unix não existem no Windows
        assert stat.S_IMODE(os.stat(caminho).st_mode) == 0o600
    assert not [n for n in os.listdir(svc.pasta_de_backups()) if n.endswith(".tmp")]


def test_backup_nao_muda_o_banco_original(app_arquivo):
    app, banco = app_arquivo
    antes = _nomes_de_produto(banco)
    svc.criar_backup()
    assert _nomes_de_produto(banco) == antes


def test_dois_backups_no_mesmo_segundo_nao_se_sobrescrevem(app_arquivo, monkeypatch):
    from datetime import datetime

    class Fixo:
        @staticmethod
        def now():
            return datetime(2026, 11, 10, 12, 0, 0)
        strptime = staticmethod(datetime.strptime)
    monkeypatch.setattr(svc, "datetime", Fixo)
    a, b = svc.criar_backup(), svc.criar_backup()
    assert a != b and len(svc.listar()) == 2


def test_retencao_mantem_so_os_mais_recentes(app_arquivo, monkeypatch):
    from datetime import datetime
    nomes = []
    for minuto in range(5):
        class Fixo:
            @staticmethod
            def now(m=minuto):
                return datetime(2026, 11, 10, 12, m, 0)
            strptime = staticmethod(datetime.strptime)
        monkeypatch.setattr(svc, "datetime", Fixo)
        nomes.append(svc.criar_backup())
    restantes = [b["nome"] for b in svc.listar()]
    assert restantes == nomes[:1:-1] and len(restantes) == 3  # mais novo primeiro; 3 mais recentes


def test_retencao_nao_apaga_arquivos_que_nao_sao_backups(app_arquivo):
    pasta = svc.pasta_de_backups()
    estranho = os.path.join(pasta, "minhas-anotacoes.txt")
    open(estranho, "w").write("x")
    for _ in range(5):
        svc.criar_backup()
    assert os.path.exists(estranho) and len(svc.listar()) == 3


def test_banco_em_memoria_recusa_backup(app):
    with pytest.raises(ErroDeNegocio, match="SQLite em arquivo"):
        svc.criar_backup()


@pytest.mark.parametrize("nome", ["../mg.db", "..\\mg.db", "/etc/passwd", "mercadogestor-1.db",
                                  "mercadogestor-20261110-120000.db/../../x", "", None,
                                  "mercadogestor-20261110-120000.db.tmp"])
def test_nome_fora_do_padrao_e_recusado(app, nome):
    with pytest.raises(ErroDeNegocio, match="não encontrado"):
        svc.caminho_do_backup(nome)


def test_nome_valido_mas_inexistente_e_recusado(app):
    with pytest.raises(ErroDeNegocio, match="não encontrado"):
        svc.caminho_do_backup("mercadogestor-20261110-120000.db")


def test_verificar_recusa_arquivo_que_nao_e_banco(tmp_path):
    lixo = tmp_path / "lixo.db"
    lixo.write_bytes(b"isto nao e um banco sqlite" * 50)
    with pytest.raises(ErroDeNegocio):
        svc.verificar(str(lixo))


def test_verificar_recusa_banco_de_outro_sistema(tmp_path):
    outro = tmp_path / "outro.db"
    con = sqlite3.connect(outro)
    con.execute("CREATE TABLE coisa (id INTEGER)")
    con.commit()
    con.close()
    with pytest.raises(ErroDeNegocio, match="não parece"):
        svc.verificar(str(outro))


# ----------------------------------------------------------------- restaurar
def test_restaurar_volta_ao_estado_do_backup_e_guarda_o_banco_atual(app_arquivo):
    app, banco = app_arquivo
    nome = svc.criar_backup()
    cat = categoria_service.criar("Limpeza")
    produto_service.criar({"categoria_id": cat.id, "nome": "Sabão", "codigo": "S1", "unidade_medida": "UN",
                           "preco_custo": "2", "preco_venda": "4", "estoque_minimo": "1"})
    assert _nomes_de_produto(banco) == ["Feijão 1kg", "Sabão"]
    db.session.remove()
    db.engine.dispose()
    seguranca = svc.restaurar(svc.caminho_do_backup(nome), banco)
    assert _nomes_de_produto(banco) == ["Feijão 1kg"]            # voltou ao backup
    assert _nomes_de_produto(seguranca) == ["Feijão 1kg", "Sabão"]  # o estado "ruim" não se perdeu
    assert not os.path.exists(banco + ".restaurando")


def test_restaurar_arquivo_invalido_nao_toca_no_banco(app_arquivo, tmp_path):
    app, banco = app_arquivo
    lixo = tmp_path / "lixo.db"
    lixo.write_bytes(b"nao sou um banco" * 100)
    antes = open(banco, "rb").read()
    with pytest.raises(ErroDeNegocio):
        svc.restaurar(str(lixo), banco)
    assert open(banco, "rb").read() == antes
    assert not [n for n in os.listdir(os.path.dirname(banco)) if "antes-da-restauracao" in n]


def test_restaurar_arquivo_inexistente(app_arquivo, tmp_path):
    app, banco = app_arquivo
    with pytest.raises(ErroDeNegocio, match="não encontrado"):
        svc.restaurar(str(tmp_path / "nao-existe.db"), banco)


def test_restaurar_sem_banco_atual_funciona(app_arquivo, tmp_path):
    app, banco = app_arquivo
    nome = svc.criar_backup()
    novo = str(tmp_path / "novo.db")
    assert svc.restaurar(svc.caminho_do_backup(nome), novo) is None
    assert _nomes_de_produto(novo) == ["Feijão 1kg"]


def test_script_restaurar_usa_servico_e_trata_erro(tmp_path, capsys):
    import restaurar
    assert restaurar.main([]) == 2
    assert restaurar.main([str(tmp_path / "nada.db")]) == 1
    assert "Não foi possível restaurar" in capsys.readouterr().out


# -------------------------------------------------------------------- rotas
def _html(r):
    return r.get_data(as_text=True)


def test_tela_lista_e_cria_backup(app_arquivo):
    app, _ = app_arquivo
    c = app.test_client()
    entrar(c, "DONO")
    assert "Nenhum backup ainda" in _html(c.get("/backup/"))
    r = c.post("/backup/criar", follow_redirects=True)
    assert "Backup criado: mercadogestor-" in _html(r)
    assert len(svc.listar()) == 1


def test_criar_so_aceita_post(app_arquivo):
    app, _ = app_arquivo
    c = app.test_client()
    entrar(c, "DONO")
    assert c.get("/backup/criar").status_code == 405


def test_download_entrega_um_banco_valido_como_anexo(app_arquivo, tmp_path):
    app, _ = app_arquivo
    c = app.test_client()
    entrar(c, "DONO")
    nome = svc.criar_backup()
    r = c.get(f"/backup/baixar/{nome}")
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]
    saida = tmp_path / "baixado.db"
    saida.write_bytes(r.data)
    svc.verificar(str(saida))
    assert "no-store" in r.headers["Cache-Control"]


def test_download_com_nome_malicioso_nao_vaza_arquivo(app_arquivo):
    app, banco = app_arquivo
    c = app.test_client()
    entrar(c, "DONO")
    for nome in ("..%2Fmg.db", "%2Fetc%2Fpasswd", "mercadogestor-20261110-120000.db.tmp"):
        r = c.get(f"/backup/baixar/{nome}", follow_redirects=True)
        assert r.status_code in (200, 404) and b"SQLite format 3" not in r.data


def test_banco_em_memoria_mostra_erro_na_tela_e_nao_quebra(client):
    r = client.post("/backup/criar", follow_redirects=True)
    assert r.status_code == 200 and "SQLite em arquivo" in _html(r)


@pytest.mark.parametrize("perfil", ["GERENTE", "CAIXA"])
def test_so_o_dono_acessa_backup(cliente_como, perfil):
    c = cliente_como(perfil)
    nome = "mercadogestor-20261110-120000.db"
    assert c.get("/backup/").status_code == 403
    assert c.post("/backup/criar").status_code == 403
    assert c.get(f"/backup/baixar/{nome}").status_code == 403


def test_anonimo_vai_para_o_login(client_anonimo):
    assert client_anonimo.get("/backup/").status_code == 302
    assert client_anonimo.get("/backup/baixar/mercadogestor-20261110-120000.db").status_code == 302
