"""Fixtures compartilhadas pelos testes.

Conceito: uma fixture do pytest prepara algo que vários testes precisam.
Aqui criamos uma aplicação com banco em memória, nova a cada teste.

Desde a Fase 8 todo o sistema exige login. Por isso:
- `client` já vem logado como DONO (os testes de telas continuam focados na regra que testam);
- `client_anonimo` não tem login (para testar o próprio login e a proteção);
- `cliente_como("CAIXA")` entra com um perfil específico (para testar permissões)
"""
import pytest

from app import create_app
from app.extensions import db
from app.models import Usuario
from config import TestConfig

SENHA_TESTE = "senha-de-teste-123"


@pytest.fixture
def app(tmp_path):
    app = create_app(TestConfig)
    app.config["BACKUP_DIR"] = str(tmp_path / "backups")  # nunca tocar na pasta real instance/
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def criar_usuario(perfil="DONO", login=None, nome=None, senha=SENHA_TESTE, trocar_senha=False, ativo=True):
    """Cria um usuário direto no banco (sem passar pelas regras), para preparar cenários."""
    from app.services import usuario_service

    usuario = Usuario(
        nome=nome or f"Usuário {perfil.title()}",
        login=login or perfil.lower(),
        senha_hash=usuario_service._gerar_hash(senha),
        perfil=perfil,
        ativo=ativo,
        trocar_senha=trocar_senha,
    )
    db.session.add(usuario)
    db.session.commit()
    return usuario


def entrar(client, perfil="DONO", **extras):
    """Deixa o cliente de testes logado (grava a sessão como o login faria)."""
    usuario = criar_usuario(perfil, **extras)
    with client.session_transaction() as sessao:
        sessao["usuario_id"] = usuario.id
        sessao["sv"] = usuario.sessao_versao
        sessao.permanent = True
    return usuario


@pytest.fixture
def client(app):
    cliente = app.test_client()
    entrar(cliente, "DONO")
    return cliente


@pytest.fixture
def client_anonimo(app):
    return app.test_client()


@pytest.fixture
def cliente_como(app):
    """Uso: caixa = cliente_como("CAIXA")."""
    def criar(perfil):
        cliente = app.test_client()
        entrar(cliente, perfil, login=f"{perfil.lower()}-teste")
        return cliente
    return criar
