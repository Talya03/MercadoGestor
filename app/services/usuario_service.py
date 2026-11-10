"""Regras de negócio de Usuário e autenticação (RN56 a RN66).

Numeração continua a de docs/05-relatorios-dashboard.md (detalhes em docs/06-usuarios-seguranca.md):
- RN56: login: 3 a 30 caracteres (letras minúsculas, números, ponto, hífen e sublinhado), único.
        Maiúsculas digitadas são convertidas para minúsculas.
- RN57: senha: 8 a 128 caracteres; não pode ser igual ao login, repetir um só caractere nem estar
        na lista de senhas óbvias. Só o hash é guardado.
- RN58: perfis: DONO, GERENTE, CAIXA (o que cada um acessa está em app/permissoes.py).
- RN59: a mensagem de falha no login é SEMPRE a mesma (não revela se o login existe, se a senha
        errou, se a conta está bloqueada ou desativada) e o tempo gasto é parecido.
- RN60: após LOGIN_MAX_TENTATIVAS erros seguidos a conta fica bloqueada por LOGIN_BLOQUEIO_MINUTOS.
- RN61: usuário desativado não entra, e a sessão dele é derrubada na próxima requisição.
- RN62: o sistema nunca fica sem DONO ativo; ninguém desativa ou muda o perfil de si mesmo.
- RN63: senha temporária (conta nova ou redefinida pelo dono) obriga a troca no primeiro acesso.
- RN64: trocar ou redefinir a senha derruba as demais sessões da pessoa.
- RN65: o primeiro acesso (sistema sem nenhum usuário) cria o DONO; depois disso a tela some.
- RN66: trocar a própria senha exige a senha atual; a nova precisa ser diferente da atual.
"""
import re
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import PERFIS, Usuario
from app.utils.erros import ErroDeNegocio

MSG_LOGIN_FALHOU = "Login ou senha incorretos, ou acesso temporariamente bloqueado."
_LOGIN = re.compile(r"[a-z0-9._-]{3,30}")
SENHA_TAMANHO_MAX = 128  # limita o custo de calcular o hash de uma senha gigante
TAMANHO_MAX_NOME = 80
_SENHAS_OBVIAS = {
    "12345678", "123456789", "1234567890", "87654321", "11111111", "00000000", "qwertyui",
    "qwerty123", "password", "password1", "senha123", "senha1234", "mudar123", "abc12345",
    "admin123", "mercado123", "iloveyou", "12341234",
}
# Sem 0/O/1/l/I para a senha temporária ser fácil de ler e ditar.
_ALFABETO_TEMP = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_hash_falso = None


def _agora():
    return datetime.now(timezone.utc).replace(tzinfo=None)  # UTC naive, como no resto do banco


def _gerar_hash(senha):
    return generate_password_hash(senha, method=current_app.config["PASSWORD_HASH_METHOD"])


def _hash_para_tempo_igual():
    """Hash de uma senha qualquer, para gastar o mesmo tempo quando o login não existe (RN59)."""
    global _hash_falso
    chave = current_app.config["PASSWORD_HASH_METHOD"]
    if _hash_falso is None or _hash_falso[0] != chave:
        _hash_falso = (chave, _gerar_hash(secrets.token_hex(16)))
    return _hash_falso[1]


# ---------------------------------------------------------------- validações
def normalizar_login(login):
    return (login or "").strip().lower()


def validar_login(login):
    login = normalizar_login(login)
    if not _LOGIN.fullmatch(login):
        raise ErroDeNegocio(
            "O login deve ter de 3 a 30 caracteres: letras, números, ponto, hífen ou sublinhado."
        )
    return login


def validar_nome(nome):
    nome = " ".join((nome or "").split())
    if not nome:
        raise ErroDeNegocio("Informe o nome.")
    if len(nome) > TAMANHO_MAX_NOME:
        raise ErroDeNegocio(f"O nome pode ter no máximo {TAMANHO_MAX_NOME} caracteres.")
    return nome


def validar_perfil(perfil):
    if perfil not in PERFIS:
        raise ErroDeNegocio("Escolha um perfil válido.")
    return perfil


def validar_senha(senha, login=None):
    minimo = current_app.config["SENHA_TAMANHO_MIN"]
    if not isinstance(senha, str) or len(senha) < minimo:
        raise ErroDeNegocio(f"A senha deve ter pelo menos {minimo} caracteres.")
    if len(senha) > SENHA_TAMANHO_MAX:
        raise ErroDeNegocio(f"A senha pode ter no máximo {SENHA_TAMANHO_MAX} caracteres.")
    if senha.lower() in _SENHAS_OBVIAS or len(set(senha)) == 1:
        raise ErroDeNegocio("Essa senha é muito comum. Escolha outra, mais difícil de adivinhar.")
    if login and senha.lower() == normalizar_login(login):
        raise ErroDeNegocio("A senha não pode ser igual ao login.")
    return senha


def gerar_senha_temporaria(tamanho=10):
    """Senha aleatória (secrets = gerador criptográfico) que já cumpre as regras da RN57."""
    while True:
        senha = "".join(secrets.choice(_ALFABETO_TEMP) for _ in range(tamanho))
        if any(c.isdigit() for c in senha) and any(c.isalpha() for c in senha):
            return senha


# -------------------------------------------------------------------- consultas
def buscar(usuario_id):
    usuario = db.session.get(Usuario, usuario_id) if usuario_id else None
    if usuario is None:
        raise ErroDeNegocio("Usuário não encontrado.")
    return usuario


def obter(usuario_id):
    """Como `buscar`, mas devolve None em vez de erro (uso interno da sessão)."""
    return db.session.get(Usuario, usuario_id) if usuario_id else None


def listar():
    return db.session.execute(select(Usuario).order_by(Usuario.nome, Usuario.id)).scalars().all()


def contar():
    return db.session.scalar(select(func.count(Usuario.id)))


def contar_donos_ativos():
    return db.session.scalar(
        select(func.count(Usuario.id)).where(Usuario.perfil == "DONO", Usuario.ativo.is_(True))
    )


# ------------------------------------------------------------------- criação
def _gravar_novo(nome, login, senha, perfil, trocar_senha):
    nome = validar_nome(nome)
    login = validar_login(login)
    perfil = validar_perfil(perfil)
    validar_senha(senha, login)
    if db.session.scalar(select(func.count(Usuario.id)).where(Usuario.login == login)):
        raise ErroDeNegocio(f'Já existe um usuário com o login "{login}".')
    usuario = Usuario(
        nome=nome, login=login, senha_hash=_gerar_hash(senha), perfil=perfil,
        ativo=True, trocar_senha=trocar_senha,
    )
    db.session.add(usuario)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ErroDeNegocio(f'Já existe um usuário com o login "{login}".')
    return usuario


def criar(nome, login, senha, perfil):
    """Conta nova criada pelo dono: a senha é temporária (RN63)."""
    return _gravar_novo(nome, login, senha, perfil, trocar_senha=True)


def criar_primeiro_dono(nome, login, senha):
    """RN65: só funciona enquanto não existe NENHUM usuário."""
    if contar() > 0:
        raise ErroDeNegocio("O sistema já tem usuários. Entre com o seu login.")
    return _gravar_novo(nome, login, senha, "DONO", trocar_senha=False)


# ------------------------------------------------------------- autenticação
def _registrar_falha(usuario):
    config = current_app.config
    usuario.tentativas_falhas += 1
    if usuario.tentativas_falhas >= config["LOGIN_MAX_TENTATIVAS"]:
        usuario.bloqueado_ate = _agora() + timedelta(minutes=config["LOGIN_BLOQUEIO_MINUTOS"])
        usuario.tentativas_falhas = 0  # RN60: depois do bloqueio, recomeça a contagem
    db.session.commit()


def _bloqueado(usuario):
    return usuario.bloqueado_ate is not None and usuario.bloqueado_ate > _agora()


def autenticar(login, senha):
    """Confere login e senha (RN59, RN60, RN61). Falha = ErroDeNegocio com mensagem única."""
    usuario = db.session.execute(
        select(Usuario).where(Usuario.login == normalizar_login(login))
    ).scalar_one_or_none()
    senha = senha if isinstance(senha, str) else ""
    if len(senha) > SENHA_TAMANHO_MAX:
        senha = ""  # nem gasta tempo calculando hash de um texto gigante

    if usuario is None:
        check_password_hash(_hash_para_tempo_igual(), senha)
        raise ErroDeNegocio(MSG_LOGIN_FALHOU)

    senha_ok = check_password_hash(usuario.senha_hash, senha)  # sempre confere (tempo parecido)
    if _bloqueado(usuario) or not usuario.ativo:
        raise ErroDeNegocio(MSG_LOGIN_FALHOU)  # bloqueada/inativa: nem a senha certa entra
    if not senha_ok:
        _registrar_falha(usuario)
        raise ErroDeNegocio(MSG_LOGIN_FALHOU)

    usuario.tentativas_falhas = 0
    usuario.bloqueado_ate = None
    usuario.ultimo_acesso = _agora()
    db.session.commit()
    return usuario


# ----------------------------------------------------------- alterações
def _outro_dono_ativo_existe(usuario):
    return db.session.scalar(
        select(func.count(Usuario.id)).where(
            Usuario.perfil == "DONO", Usuario.ativo.is_(True), Usuario.id != usuario.id
        )
    ) > 0


def editar(usuario_id, nome, perfil, ator_id):
    usuario = buscar(usuario_id)
    nome = validar_nome(nome)
    perfil = validar_perfil(perfil)
    if perfil != usuario.perfil:
        if usuario.id == ator_id:
            raise ErroDeNegocio("Você não pode mudar o seu próprio perfil.")  # RN62
        if usuario.perfil == "DONO" and usuario.ativo and not _outro_dono_ativo_existe(usuario):
            raise ErroDeNegocio("O sistema precisa de ao menos um dono ativo.")  # RN62
        usuario.sessao_versao += 1  # a permissão mudou: força nova sessão
    usuario.nome = nome
    usuario.perfil = perfil
    db.session.commit()
    return usuario


def alternar_ativo(usuario_id, ator_id):
    usuario = buscar(usuario_id)
    if usuario.ativo:
        if usuario.id == ator_id:
            raise ErroDeNegocio("Você não pode desativar o seu próprio usuário.")  # RN62
        if usuario.perfil == "DONO" and not _outro_dono_ativo_existe(usuario):
            raise ErroDeNegocio("O sistema precisa de ao menos um dono ativo.")  # RN62
        usuario.ativo = False
        usuario.sessao_versao += 1  # RN61
    else:
        usuario.ativo = True
        usuario.tentativas_falhas = 0
        usuario.bloqueado_ate = None
    db.session.commit()
    return usuario


def redefinir_senha(usuario_id):
    """O dono gera uma nova senha temporária; devolve (usuário, senha) para mostrar UMA vez."""
    usuario = buscar(usuario_id)
    senha = gerar_senha_temporaria()
    usuario.senha_hash = _gerar_hash(senha)
    usuario.trocar_senha = True  # RN63
    usuario.sessao_versao += 1  # RN64
    usuario.tentativas_falhas = 0
    usuario.bloqueado_ate = None
    db.session.commit()
    return usuario, senha


def trocar_senha(usuario_id, senha_atual, nova_senha):
    """A própria pessoa troca a senha (RN66). Devolve o usuário com a nova versão de sessão."""
    usuario = buscar(usuario_id)
    if _bloqueado(usuario):
        raise ErroDeNegocio(MSG_LOGIN_FALHOU)
    if not isinstance(senha_atual, str) or len(senha_atual) > SENHA_TAMANHO_MAX \
            or not check_password_hash(usuario.senha_hash, senha_atual):
        _registrar_falha(usuario)
        raise ErroDeNegocio("A senha atual está incorreta.")
    validar_senha(nova_senha, usuario.login)
    if nova_senha == senha_atual:
        raise ErroDeNegocio("A nova senha deve ser diferente da atual.")
    usuario.senha_hash = _gerar_hash(nova_senha)
    usuario.trocar_senha = False
    usuario.sessao_versao += 1  # RN64
    usuario.tentativas_falhas = 0
    db.session.commit()
    return usuario
