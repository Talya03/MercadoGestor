"""Regras de negócio de Categoria.

Conceito: o service concentra as regras. A rota só recebe o pedido HTTP e
chama o service; o modelo só descreve a tabela. Assim, as regras podem ser
testadas sem abrir navegador e reaproveitadas por outras telas.
"""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Categoria
from app.utils.erros import ErroDeNegocio

TAMANHO_MAX_NOME = 80
TAMANHO_MAX_DESCRICAO = 255


def _normalizar(texto):
    """Tira espaços das pontas e colapsa espaços repetidos no meio."""
    return " ".join((texto or "").split())


def _validar_nome(nome):
    nome = _normalizar(nome)
    if not nome:
        raise ErroDeNegocio("Informe o nome da categoria.")
    if len(nome) > TAMANHO_MAX_NOME:
        raise ErroDeNegocio(f"O nome pode ter no máximo {TAMANHO_MAX_NOME} caracteres.")
    return nome


def _validar_descricao(descricao):
    descricao = _normalizar(descricao)
    if len(descricao) > TAMANHO_MAX_DESCRICAO:
        raise ErroDeNegocio(
            f"A descrição pode ter no máximo {TAMANHO_MAX_DESCRICAO} caracteres."
        )
    return descricao or None


def _nome_em_uso(nome, ignorar_id=None):
    """RN01: nome único, sem diferenciar maiúsculas/minúsculas.

    A comparação é feita em Python com casefold() porque o lower() do SQLite
    não trata letras acentuadas ("LATICÍNIOS" x "Laticínios").
    """
    alvo = nome.casefold()
    linhas = db.session.execute(select(Categoria.id, Categoria.nome)).all()
    return any(i != ignorar_id and n.casefold() == alvo for i, n in linhas)


def _mensagem_duplicada(nome):
    return f'Já existe uma categoria chamada "{nome}".'


def buscar(categoria_id):
    categoria = db.session.get(Categoria, categoria_id)
    if categoria is None:
        raise ErroDeNegocio("Categoria não encontrada.")
    return categoria


def listar(busca="", incluir_inativas=False):
    """Lista categorias em ordem alfabética, com busca opcional pelo nome."""
    consulta = select(Categoria).order_by(Categoria.nome)
    if not incluir_inativas:
        consulta = consulta.where(Categoria.ativo.is_(True))
    categorias = db.session.execute(consulta).scalars().all()

    termo = _normalizar(busca).casefold()
    if termo:
        categorias = [c for c in categorias if termo in c.nome.casefold()]
    return categorias


def criar(nome, descricao=None):
    nome = _validar_nome(nome)
    descricao = _validar_descricao(descricao)
    if _nome_em_uso(nome):
        raise ErroDeNegocio(_mensagem_duplicada(nome))

    categoria = Categoria(nome=nome, descricao=descricao)
    db.session.add(categoria)
    try:
        db.session.commit()
    except IntegrityError:
        # Rede de segurança: o banco (UNIQUE) barrou algo que passou pela checagem.
        db.session.rollback()
        raise ErroDeNegocio(_mensagem_duplicada(nome))
    return categoria


def editar(categoria_id, nome, descricao=None):
    categoria = buscar(categoria_id)
    nome = _validar_nome(nome)
    descricao = _validar_descricao(descricao)
    if _nome_em_uso(nome, ignorar_id=categoria.id):
        raise ErroDeNegocio(_mensagem_duplicada(nome))

    categoria.nome = nome
    categoria.descricao = descricao
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ErroDeNegocio(_mensagem_duplicada(nome))
    return categoria


def alternar_ativo(categoria_id):
    """Ativa ou desativa a categoria (RN08: nunca excluímos).

    RN09: não é possível desativar uma categoria que ainda tem produtos ativos.
    """
    categoria = buscar(categoria_id)
    if categoria.ativo and any(p.ativo for p in categoria.produtos):
        raise ErroDeNegocio(
            "Não é possível desativar: esta categoria ainda tem produtos ativos."
        )
    categoria.ativo = not categoria.ativo
    db.session.commit()
    return categoria
