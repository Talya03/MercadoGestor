"""Regras de negócio de Fornecedor.

- RN31: o nome é único (sem diferenciar maiúsculas/minúsculas ou acentos de caixa);
        o documento (CPF/CNPJ), quando informado, também é único e tem só números
        (11 ou 14 dígitos). Os dígitos verificadores NÃO são conferidos (limitação).
- RN32: fornecedor não é excluído, só desativado; fornecedor inativo não recebe compras.

Exemplo de mercado: "Distribuidora Bom Preço", CNPJ 12.345.678/0001-90, vendedor João.
"""
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Fornecedor
from app.utils.erros import ErroDeNegocio

TAMANHO_MAX_NOME = 120
TAMANHO_MAX_CONTATO = 80
_TELEFONE = re.compile(r"[\d\s()+\-]{8,20}")


def _normalizar(texto):
    return " ".join((texto or "").split())


def _validar_nome(nome):
    nome = _normalizar(nome)
    if not nome:
        raise ErroDeNegocio("Informe o nome do fornecedor.")
    if len(nome) > TAMANHO_MAX_NOME:
        raise ErroDeNegocio(f"O nome pode ter no máximo {TAMANHO_MAX_NOME} caracteres.")
    return nome


def _validar_documento(documento):
    """Aceita com ou sem pontuação ("12.345.678/0001-90"); guarda só os dígitos."""
    bruto = _normalizar(documento)
    if not bruto:
        return None
    if re.search(r"[^\d.\-/\s]", bruto):
        raise ErroDeNegocio("O CPF/CNPJ deve conter apenas números.")
    digitos = re.sub(r"\D", "", bruto)
    if len(digitos) not in (11, 14):
        raise ErroDeNegocio("O CPF deve ter 11 dígitos e o CNPJ, 14.")
    return digitos


def _validar_telefone(telefone):
    telefone = _normalizar(telefone)
    if not telefone:
        return None
    if not _TELEFONE.fullmatch(telefone) or len(re.sub(r"\D", "", telefone)) < 8:
        raise ErroDeNegocio("Telefone inválido. Use, por exemplo, (11) 98765-4321.")
    return telefone


def _validar_contato(contato):
    contato = _normalizar(contato)
    if len(contato) > TAMANHO_MAX_CONTATO:
        raise ErroDeNegocio(f"O contato pode ter no máximo {TAMANHO_MAX_CONTATO} caracteres.")
    return contato or None


def _nome_em_uso(nome, ignorar_id=None):
    alvo = nome.casefold()
    linhas = db.session.execute(select(Fornecedor.id, Fornecedor.nome)).all()
    return any(i != ignorar_id and n.casefold() == alvo for i, n in linhas)


def _documento_em_uso(documento, ignorar_id=None):
    if not documento:
        return False
    consulta = select(Fornecedor.id).where(Fornecedor.documento == documento)
    return any(i != ignorar_id for (i,) in db.session.execute(consulta).all())


def _checar_duplicidade(nome, documento, ignorar_id=None):
    if _nome_em_uso(nome, ignorar_id):
        raise ErroDeNegocio(f'Já existe um fornecedor chamado "{nome}".')
    if _documento_em_uso(documento, ignorar_id):
        raise ErroDeNegocio("Já existe um fornecedor com este CPF/CNPJ.")


def _dados_validados(nome, documento, telefone, contato):
    return (
        _validar_nome(nome),
        _validar_documento(documento),
        _validar_telefone(telefone),
        _validar_contato(contato),
    )


def _confirmar():
    try:
        db.session.commit()
    except IntegrityError:
        # Rede de segurança: o banco (UNIQUE) barrou algo que passou pelas checagens.
        db.session.rollback()
        raise ErroDeNegocio("Já existe um fornecedor com este nome ou CPF/CNPJ.")


def buscar(fornecedor_id):
    fornecedor = db.session.get(Fornecedor, fornecedor_id)
    if fornecedor is None:
        raise ErroDeNegocio("Fornecedor não encontrado.")
    return fornecedor


def listar(busca="", incluir_inativos=False):
    """Por nome; a busca procura no nome, no documento (só dígitos) e no contato."""
    consulta = select(Fornecedor).order_by(Fornecedor.nome)
    if not incluir_inativos:
        consulta = consulta.where(Fornecedor.ativo.is_(True))
    fornecedores = db.session.execute(consulta).scalars().all()

    termo = _normalizar(busca).casefold()
    if termo:
        termo_digitos = re.sub(r"\D", "", termo)

        def combina(f):
            if termo in f.nome.casefold() or termo in (f.contato or "").casefold():
                return True
            return bool(termo_digitos) and termo_digitos in (f.documento or "")

        fornecedores = [f for f in fornecedores if combina(f)]
    return fornecedores


def criar(nome, documento=None, telefone=None, contato=None):
    nome, documento, telefone, contato = _dados_validados(nome, documento, telefone, contato)
    _checar_duplicidade(nome, documento)
    fornecedor = Fornecedor(nome=nome, documento=documento, telefone=telefone, contato=contato)
    db.session.add(fornecedor)
    _confirmar()
    return fornecedor


def editar(fornecedor_id, nome, documento=None, telefone=None, contato=None):
    fornecedor = buscar(fornecedor_id)
    nome, documento, telefone, contato = _dados_validados(nome, documento, telefone, contato)
    _checar_duplicidade(nome, documento, ignorar_id=fornecedor.id)
    fornecedor.nome = nome
    fornecedor.documento = documento
    fornecedor.telefone = telefone
    fornecedor.contato = contato
    _confirmar()
    return fornecedor


def alternar_ativo(fornecedor_id):
    """RN32: ativa/desativa. As compras antigas continuam ligadas a ele."""
    fornecedor = buscar(fornecedor_id)
    fornecedor.ativo = not fornecedor.ativo
    db.session.commit()
    return fornecedor
