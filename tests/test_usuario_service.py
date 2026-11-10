"""Testes de usuários e autenticação (RN56 a RN66)."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Usuario
from app.services import usuario_service as svc
from app.utils.erros import ErroDeNegocio
from config import Config
from tests.conftest import criar_usuario

SENHA = "uma-senha-boa-42"


def agora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def dono(login="maria", senha=SENHA):
    return svc.criar_primeiro_dono("Maria", login, senha)


# ------------------------------------------------------------------- criação
def test_cria_usuario_normaliza_login_e_marca_senha_temporaria(app):
    u = svc.criar("  Ana   Souza ", "  ANA.Souza  ", SENHA, "CAIXA")
    assert (u.nome, u.login, u.perfil) == ("Ana Souza", "ana.souza", "CAIXA")
    assert u.trocar_senha is True and u.ativo is True and u.sessao_versao == 1  # RN63


def test_senha_nunca_e_guardada_em_texto(app):
    u = svc.criar("Ana", "ana", SENHA, "CAIXA")
    assert SENHA not in u.senha_hash and u.senha_hash != SENHA
    assert db.session.execute(db.text("select senha_hash from usuario")).scalar() == u.senha_hash


def test_mesma_senha_gera_hashes_diferentes_por_causa_do_sal(app):
    a = svc.criar("A", "aaa", SENHA, "CAIXA")
    b = svc.criar("B", "bbb", SENHA, "CAIXA")
    assert a.senha_hash != b.senha_hash


def test_hash_padrao_de_producao_e_forte(app):
    """Nos testes o hash é barato; aqui confirmo que a configuração REAL usa scrypt/PBKDF2 forte."""
    app.config["PASSWORD_HASH_METHOD"] = Config.PASSWORD_HASH_METHOD
    u = svc.criar("Ana", "ana", SENHA, "CAIXA")
    assert u.senha_hash.startswith(("scrypt:", "pbkdf2:sha256:600000"))
    assert svc.autenticar("ana", SENHA).id == u.id


@pytest.mark.parametrize("login", ["", "  ", "ab", "a" * 31, "ana souza", "ana@x", "ação", "a/b", None, "ana;drop"])
def test_login_invalido(app, login):
    with pytest.raises(ErroDeNegocio, match="login"):
        svc.criar("Ana", login, SENHA, "CAIXA")
    assert svc.contar() == 0


@pytest.mark.parametrize("login", ["abc", "a.b-c_d", "caixa01", "a" * 30])
def test_login_valido(app, login):
    assert svc.criar("Ana", login, SENHA, "CAIXA").login == login


@pytest.mark.parametrize("nome", ["", "   ", None, "x" * 81])
def test_nome_invalido(app, nome):
    with pytest.raises(ErroDeNegocio):
        svc.criar(nome, "ana", SENHA, "CAIXA")


@pytest.mark.parametrize("perfil", ["", "ADMIN", "dono", None, "DONO ", "root"])
def test_perfil_invalido(app, perfil):
    with pytest.raises(ErroDeNegocio, match="perfil"):
        svc.criar("Ana", "ana", SENHA, perfil)


@pytest.mark.parametrize("senha, msg", [
    ("", "pelo menos 8"), ("1234567", "pelo menos 8"), (None, "pelo menos 8"),
    ("x" * 129, "no máximo 128"),
    ("12345678", "muito comum"), ("PASSWORD", "muito comum"), ("Senha123", "muito comum"),
    ("aaaaaaaaaa", "muito comum"),
    ("Mariazinha", "igual ao login"),
])
def test_senha_invalida(app, senha, msg):
    with pytest.raises(ErroDeNegocio, match=msg):
        svc.criar("Maria", "mariazinha", senha, "CAIXA")
    assert svc.contar() == 0


def test_senha_com_espacos_e_acentos_e_valida(app):
    assert svc.criar("Ana", "ana", "  frase longa com açúcar  ", "CAIXA")  # espaços não são cortados
    assert svc.autenticar("ana", "  frase longa com açúcar  ")
    with pytest.raises(ErroDeNegocio):
        svc.autenticar("ana", "frase longa com açúcar")


def test_login_duplicado_sem_diferenciar_caixa(app):
    svc.criar("Ana", "ana", SENHA, "CAIXA")
    with pytest.raises(ErroDeNegocio, match="Já existe"):
        svc.criar("Outra", "ANA", SENHA, "GERENTE")


def test_banco_barra_perfil_e_login_invalidos_sem_passar_pelo_service(app):
    db.session.add(Usuario(nome="x", login="x1x", senha_hash="h", perfil="ROOT"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
    criar_usuario("CAIXA", login="dup")
    db.session.add(Usuario(nome="y", login="dup", senha_hash="h", perfil="CAIXA"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


# ----------------------------------------------------------- primeiro dono
def test_primeiro_dono_so_com_banco_vazio(app):
    u = dono()
    assert u.perfil == "DONO" and u.trocar_senha is False  # escolheu a própria senha
    with pytest.raises(ErroDeNegocio, match="já tem usuários"):  # RN65
        svc.criar_primeiro_dono("Invasor", "invasor", SENHA)
    assert svc.contar() == 1


def test_primeiro_dono_com_dados_invalidos_nao_cria(app):
    with pytest.raises(ErroDeNegocio):
        svc.criar_primeiro_dono("Maria", "maria", "123")
    assert svc.contar() == 0


# --------------------------------------------------------------- autenticar
def test_login_correto_zera_contadores_e_registra_acesso(app):
    u = dono()
    u.tentativas_falhas = 3
    db.session.commit()
    logado = svc.autenticar("  MARIA ", SENHA)  # login sem diferenciar caixa
    assert logado.id == u.id and logado.tentativas_falhas == 0
    assert logado.ultimo_acesso is not None and logado.bloqueado_ate is None


@pytest.mark.parametrize("login, senha", [
    ("maria", "errada-errada"), ("ninguem", SENHA), ("", ""), (None, None), ("maria", None),
    ("maria", "x" * 5000),
])
def test_falha_de_login_tem_sempre_a_mesma_mensagem(app, login, senha):
    dono()
    with pytest.raises(ErroDeNegocio) as erro:
        svc.autenticar(login, senha)
    assert str(erro.value) == svc.MSG_LOGIN_FALHOU  # RN59


def test_usuario_inativo_nao_entra_nem_com_senha_certa(app):
    dono()
    ana = svc.criar("Ana", "ana", SENHA, "CAIXA")
    svc.alternar_ativo(ana.id, ator_id=1)
    with pytest.raises(ErroDeNegocio) as erro:
        svc.autenticar("ana", SENHA)
    assert str(erro.value) == svc.MSG_LOGIN_FALHOU  # RN61


def test_bloqueio_apos_5_erros_e_senha_certa_nao_entra_bloqueado(app):
    u = dono()
    for _ in range(5):
        with pytest.raises(ErroDeNegocio):
            svc.autenticar("maria", "errada-errada")
    db.session.refresh(u)
    assert u.bloqueado_ate is not None and u.bloqueado_ate > agora()
    assert u.tentativas_falhas == 0  # RN60: nova contagem após o bloqueio
    with pytest.raises(ErroDeNegocio) as erro:
        svc.autenticar("maria", SENHA)  # senha CERTA, mas bloqueada
    assert str(erro.value) == svc.MSG_LOGIN_FALHOU


def test_quatro_erros_ainda_nao_bloqueiam(app):
    u = dono()
    for _ in range(4):
        with pytest.raises(ErroDeNegocio):
            svc.autenticar("maria", "errada-errada")
    assert u.bloqueado_ate is None and u.tentativas_falhas == 4
    assert svc.autenticar("maria", SENHA)  # acertou: zera
    assert u.tentativas_falhas == 0


def test_bloqueio_expira(app):
    u = dono()
    u.bloqueado_ate = agora() - timedelta(seconds=1)
    db.session.commit()
    assert svc.autenticar("maria", SENHA)
    assert u.bloqueado_ate is None


def test_tentar_durante_o_bloqueio_nao_o_prolonga(app):
    u = dono()
    limite = agora() + timedelta(minutes=2)
    u.bloqueado_ate = limite
    db.session.commit()
    with pytest.raises(ErroDeNegocio):
        svc.autenticar("maria", "errada-errada")
    assert u.bloqueado_ate == limite


def test_login_inexistente_tambem_gasta_o_calculo_do_hash(app, monkeypatch):
    """RN59: sem isso, o tempo de resposta revelaria se o login existe."""
    dono()
    chamadas = []
    real = svc.check_password_hash
    monkeypatch.setattr(svc, "check_password_hash", lambda h, s: chamadas.append(h) or real(h, s))
    for login in ("maria", "ninguem"):
        with pytest.raises(ErroDeNegocio):
            svc.autenticar(login, "errada-errada")
    assert len(chamadas) == 2


def test_senha_gigante_nao_e_enviada_ao_hash(app, monkeypatch):
    dono()
    textos = []
    real = svc.check_password_hash
    monkeypatch.setattr(svc, "check_password_hash", lambda h, s: textos.append(s) or real(h, s))
    with pytest.raises(ErroDeNegocio):
        svc.autenticar("maria", "x" * 100_000)
    assert textos == [""]


# --------------------------------------------------------------- alterações
def test_editar_nome_e_perfil(app):
    dono()
    ana = svc.criar("Ana", "ana", SENHA, "CAIXA")
    svc.editar(ana.id, "Ana Maria", "GERENTE", ator_id=1)
    assert (ana.nome, ana.perfil, ana.sessao_versao) == ("Ana Maria", "GERENTE", 2)  # perfil mudou: nova sessão


def test_editar_so_o_nome_nao_derruba_sessao(app):
    dono()
    ana = svc.criar("Ana", "ana", SENHA, "CAIXA")
    svc.editar(ana.id, "Ana Maria", "CAIXA", ator_id=1)
    assert ana.sessao_versao == 1


def test_nao_muda_o_proprio_perfil(app):
    m = dono()
    with pytest.raises(ErroDeNegocio, match="seu próprio perfil"):
        svc.editar(m.id, "Maria", "CAIXA", ator_id=m.id)  # RN62
    assert m.perfil == "DONO"


def test_ultimo_dono_nao_perde_o_perfil_nem_a_conta(app):
    m = dono()
    gerente = criar_usuario("GERENTE", login="ger")
    with pytest.raises(ErroDeNegocio, match="ao menos um dono"):
        svc.editar(m.id, "Maria", "CAIXA", ator_id=gerente.id)  # gerente tentando rebaixar (defesa em camadas)
    with pytest.raises(ErroDeNegocio, match="ao menos um dono"):
        svc.alternar_ativo(m.id, ator_id=gerente.id)
    assert m.perfil == "DONO" and m.ativo


def test_com_dois_donos_um_pode_ser_desativado(app):
    a = dono()
    b = criar_usuario("DONO", login="outro-dono")
    svc.alternar_ativo(b.id, ator_id=a.id)
    assert b.ativo is False and svc.contar_donos_ativos() == 1


def test_nao_desativa_a_si_mesmo(app):
    m = dono()
    criar_usuario("DONO", login="outro-dono")
    with pytest.raises(ErroDeNegocio, match="seu próprio usuário"):
        svc.alternar_ativo(m.id, ator_id=m.id)


def test_desativar_derruba_sessoes_e_reativar_limpa_bloqueio(app):
    dono()
    ana = svc.criar("Ana", "ana", SENHA, "CAIXA")
    svc.alternar_ativo(ana.id, 1)
    assert ana.ativo is False and ana.sessao_versao == 2  # RN61
    ana.tentativas_falhas, ana.bloqueado_ate = 3, agora() + timedelta(minutes=5)
    svc.alternar_ativo(ana.id, 1)
    assert ana.ativo and ana.tentativas_falhas == 0 and ana.bloqueado_ate is None


def test_usuario_inexistente(app):
    for chamada in (lambda: svc.buscar(999), lambda: svc.editar(999, "x", "CAIXA", 1),
                    lambda: svc.alternar_ativo(999, 1), lambda: svc.redefinir_senha(999),
                    lambda: svc.trocar_senha(999, "a", "b")):
        with pytest.raises(ErroDeNegocio, match="não encontrado"):
            chamada()
    assert svc.obter(None) is None and svc.obter(999) is None


# ---------------------------------------------------------------- redefinir
def test_redefinir_senha_gera_temporaria_valida_e_derruba_sessoes(app):
    dono()
    ana = svc.criar("Ana", "ana", SENHA, "CAIXA")
    svc.trocar_senha(ana.id, SENHA, "senha-propria-99")
    ana.tentativas_falhas, ana.bloqueado_ate = 2, agora() + timedelta(minutes=5)
    versao = ana.sessao_versao
    _, temporaria = svc.redefinir_senha(ana.id)
    assert ana.trocar_senha is True and ana.sessao_versao == versao + 1  # RN63, RN64
    assert ana.tentativas_falhas == 0 and ana.bloqueado_ate is None
    assert svc.autenticar("ana", temporaria)
    with pytest.raises(ErroDeNegocio):
        svc.autenticar("ana", "senha-propria-99")  # a antiga deixou de valer


def test_senha_temporaria_cumpre_as_regras_e_nao_usa_caracteres_ambiguos(app):
    vistas = set()
    for _ in range(200):
        s = svc.gerar_senha_temporaria()
        assert len(s) == 10 and any(c.isdigit() for c in s) and any(c.isalpha() for c in s)
        assert not set(s) & set("0O1lI")
        svc.validar_senha(s)
        vistas.add(s)
    assert len(vistas) == 200  # aleatória, sem repetição na prática


# ------------------------------------------------------------- trocar senha
def test_trocar_senha_com_sucesso(app):
    dono()
    ana = svc.criar("Ana", "ana", SENHA, "CAIXA")
    versao = ana.sessao_versao
    svc.trocar_senha(ana.id, SENHA, "nova-senha-forte-7")
    assert ana.trocar_senha is False and ana.sessao_versao == versao + 1  # RN64
    assert svc.autenticar("ana", "nova-senha-forte-7")
    with pytest.raises(ErroDeNegocio):
        svc.autenticar("ana", SENHA)


def test_trocar_senha_exige_a_atual_correta_e_conta_como_tentativa(app):
    ana = svc.criar("Ana", "ana", SENHA, "CAIXA")
    for _ in range(5):
        with pytest.raises(ErroDeNegocio, match="atual está incorreta"):
            svc.trocar_senha(ana.id, "chute-errado-1", "nova-senha-forte-7")
    with pytest.raises(ErroDeNegocio) as erro:  # bloqueada: nem a atual certa é aceita
        svc.trocar_senha(ana.id, SENHA, "nova-senha-forte-7")
    assert str(erro.value) == svc.MSG_LOGIN_FALHOU
    assert ana.senha_hash and check(ana, SENHA)  # a senha continuou a mesma


def check(usuario, senha):
    from werkzeug.security import check_password_hash
    return check_password_hash(usuario.senha_hash, senha)


@pytest.mark.parametrize("nova, msg", [
    (SENHA, "diferente da atual"), ("curta", "pelo menos 8"), ("12345678", "muito comum"), ("ana", "pelo menos 8"),
])
def test_trocar_senha_nova_invalida(app, nova, msg):
    ana = svc.criar("Ana", "ana", SENHA, "CAIXA")
    with pytest.raises(ErroDeNegocio, match=msg):
        svc.trocar_senha(ana.id, SENHA, nova)
    assert check(ana, SENHA) and ana.trocar_senha is True


def test_trocar_senha_com_atual_gigante_ou_nula(app):
    ana = svc.criar("Ana", "ana", SENHA, "CAIXA")
    for atual in (None, "x" * 5000):
        with pytest.raises(ErroDeNegocio, match="atual está incorreta"):
            svc.trocar_senha(ana.id, atual, "nova-senha-forte-7")
