"""Testes das telas de gestão de usuários (somente dono)."""
import re

import pytest

from app.extensions import db
from app.models import Usuario
from app.services import usuario_service as svc
from tests.conftest import SENHA_TESTE, criar_usuario


def html(r):
    return r.get_data(as_text=True)


def usuario(login):
    db.session.expire_all()
    return db.session.query(Usuario).filter_by(login=login).one()


def senha_mostrada(r):
    return re.search(r"<code class=\"fs-5\">([^<]+)</code>", html(r)).group(1)


def test_lista_mostra_usuarios_com_status(client):
    criar_usuario("CAIXA", login="ana", nome="Ana Souza", trocar_senha=True, ativo=True)
    criar_usuario("GERENTE", login="bia", nome="Bia", ativo=False)
    corpo = html(client.get("/usuarios/"))
    assert "Ana Souza" in corpo and "Senha temporária" in corpo and "Inativo" in corpo and "você" in corpo
    assert "senha_hash" not in corpo and "pbkdf2" not in corpo  # nunca expõe hashes


def test_cria_usuario_com_senha_gerada_e_ela_aparece_so_na_resposta(client):
    r = client.post("/usuarios/novo", data={"nome": "Ana", "login": "ana", "perfil": "CAIXA", "senha": ""})
    assert r.status_code == 200 and "Usuário criado" in html(r)
    senha = senha_mostrada(r)
    assert "Set-Cookie" not in r.headers or senha not in r.headers.get("Set-Cookie", "")
    novo = usuario("ana")
    assert (novo.perfil, novo.trocar_senha) == ("CAIXA", True)
    assert senha not in html(client.get("/usuarios/"))  # a lista não repete a senha
    novo_cliente = client.application.test_client()
    assert novo_cliente.post("/login", data={"login": "ana", "senha": senha}).status_code == 302
    assert novo_cliente.get("/pdv/").headers["Location"].endswith("/conta/senha")  # troca obrigatória


def test_cria_usuario_com_senha_escolhida(client):
    r = client.post("/usuarios/novo", data={"nome": "Bia", "login": "bia", "perfil": "GERENTE", "senha": "minha-senha-inicial-8"})
    assert senha_mostrada(r) == "minha-senha-inicial-8"
    assert usuario("bia").perfil == "GERENTE"


@pytest.mark.parametrize("dados, msg", [
    ({"nome": "", "login": "x1x", "perfil": "CAIXA"}, "nome"),
    ({"nome": "A", "login": "a", "perfil": "CAIXA"}, "login"),
    ({"nome": "A", "login": "aaa", "perfil": "ROOT"}, "perfil"),
    ({"nome": "A", "login": "aaa", "perfil": "CAIXA", "senha": "123"}, "pelo menos 8"),
    ({"nome": "A", "login": "chefe", "perfil": "CAIXA"}, "Já existe"),
])
def test_criacao_invalida_mostra_erro_e_nao_cria(client, dados, msg):
    dados = {**dados, "login": "dono" if dados["login"] == "chefe" else dados["login"]}
    antes = db.session.query(Usuario).count()
    r = client.post("/usuarios/novo", data=dados)
    assert r.status_code == 200 and msg in html(r)
    assert db.session.query(Usuario).count() == antes
    assert f'value="{dados["nome"]}"' in html(r) or not dados["nome"]  # preserva o que foi digitado


def test_editar_nome_e_perfil(client):
    ana = criar_usuario("CAIXA", login="ana", nome="Ana")
    r = client.post(f"/usuarios/{ana.id}/editar", data={"nome": "Ana Maria", "perfil": "GERENTE"}, follow_redirects=True)
    assert "Usuário atualizado" in html(r)
    assert (usuario("ana").nome, usuario("ana").perfil) == ("Ana Maria", "GERENTE")


def test_dono_nao_muda_o_proprio_perfil_pela_tela(client):
    eu = usuario("dono")
    corpo = html(client.get(f"/usuarios/{eu.id}/editar"))
    assert "disabled" in corpo and "não pode mudar o seu próprio perfil" in corpo
    r = client.post(f"/usuarios/{eu.id}/editar", data={"nome": eu.nome, "perfil": "CAIXA"})
    assert "seu próprio perfil" in html(r) and usuario("dono").perfil == "DONO"


def test_editar_inexistente(client):
    assert "não encontrado" in html(client.get("/usuarios/999/editar", follow_redirects=True))


def test_desativar_e_reativar_so_por_post(client):
    ana = criar_usuario("CAIXA", login="ana")
    assert client.get(f"/usuarios/{ana.id}/alternar").status_code == 405
    assert client.get(f"/usuarios/{ana.id}/redefinir-senha").status_code == 405
    assert "desativado" in html(client.post(f"/usuarios/{ana.id}/alternar", follow_redirects=True))
    assert usuario("ana").ativo is False
    assert "ativado" in html(client.post(f"/usuarios/{ana.id}/alternar", follow_redirects=True))
    assert usuario("ana").ativo is True


def test_dono_nao_se_desativa_e_lista_nao_oferece_o_botao(client):
    eu = usuario("dono")
    assert "seu próprio usuário" in html(client.post(f"/usuarios/{eu.id}/alternar", follow_redirects=True))
    assert usuario("dono").ativo
    corpo = html(client.get("/usuarios/"))
    assert f"/usuarios/{eu.id}/alternar" not in corpo


def test_redefinir_senha_mostra_nova_temporaria_e_invalida_a_antiga(client):
    ana = criar_usuario("CAIXA", login="ana")
    r = client.post(f"/usuarios/{ana.id}/redefinir-senha")
    assert "Senha redefinida" in html(r)
    nova = senha_mostrada(r)
    c = client.application.test_client()
    assert c.post("/login", data={"login": "ana", "senha": SENHA_TESTE}).status_code == 401
    assert c.post("/login", data={"login": "ana", "senha": nova}).status_code == 302
    assert usuario("ana").trocar_senha is True


def test_redefinir_inexistente(client):
    assert "não encontrado" in html(client.post("/usuarios/999/redefinir-senha", follow_redirects=True))


def test_nome_com_html_e_escapado(client):
    criar_usuario("CAIXA", login="xss", nome='<script>alert("x")</script>')
    corpo = html(client.get("/usuarios/"))
    assert "<script>alert" not in corpo and "&lt;script&gt;" in corpo


def test_desativar_derruba_o_usuario_logado_em_outro_navegador(client):
    ana = criar_usuario("CAIXA", login="ana")
    outro = client.application.test_client()
    outro.post("/login", data={"login": "ana", "senha": SENHA_TESTE})
    assert outro.get("/pdv/").status_code == 200
    client.post(f"/usuarios/{ana.id}/alternar")
    assert outro.get("/pdv/").status_code == 302


def test_acoes_de_usuario_exigem_csrf():
    from app import create_app
    from config import TestConfig
    from tests.conftest import entrar

    class Cfg(TestConfig):
        WTF_CSRF_ENABLED = True

    app = create_app(Cfg)
    with app.app_context():
        db.create_all()
        c = app.test_client()
        entrar(c)
        for url in ("/usuarios/novo", "/usuarios/1/editar", "/usuarios/1/alternar", "/usuarios/1/redefinir-senha"):
            assert c.post(url, data={}).status_code == 400
        db.session.remove()
        db.drop_all()
