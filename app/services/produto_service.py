"""Regras de negócio de Produto.

Regras desta etapa (além das de categoria):
- RN02: código único (sem diferenciar maiúsculas/minúsculas).
- RN03: preços e estoque mínimo não podem ser negativos.
- RN10: só se cadastra/move produto para categoria ativa; não se reativa
        produto cuja categoria está inativa.
- RN11: a unidade de medida não muda se o produto já tem estoque ou histórico.
- RN12: o saldo de estoque NÃO é editado aqui. Começa em 0 e só muda por
        movimentações (módulo de Estoque, Fase 4).
- RN13: preço de venda abaixo do custo (ou zero) é permitido, mas gera aviso.
"""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Categoria, Produto
from app.utils.erros import ErroDeNegocio
from app.utils.numeros import validar_decimal

UNIDADES = {
    "UN": "Unidade (UN)",
    "KG": "Quilo (KG)",
    "G": "Grama (G)",
    "L": "Litro (L)",
    "ML": "Mililitro (ML)",
    "CX": "Caixa (CX)",
    "PCT": "Pacote (PCT)",
}

TAMANHO_MAX_NOME = 120
TAMANHO_MAX_CODIGO = 50
# Limites que cabem nas colunas Numeric(10,2) e Numeric(10,3) do banco.
PRECO_MAXIMO = Decimal("99999999.99")
QUANTIDADE_MAXIMA = Decimal("9999999.999")


def _normalizar(texto):
    return " ".join((texto or "").split())


def _mensagem_codigo_duplicado(codigo):
    return f'Já existe um produto com o código "{codigo}".'


def _codigo_em_uso(codigo, ignorar_id=None):
    alvo = codigo.casefold()
    linhas = db.session.execute(select(Produto.id, Produto.codigo)).all()
    return any(i != ignorar_id and c.casefold() == alvo for i, c in linhas)


def _validar(dados, produto_atual=None):
    """Valida e limpa os dados vindos do formulário. Só lê as chaves conhecidas,
    então um campo extra (ex.: quantidade_estoque) é simplesmente ignorado (RN12)."""
    nome = _normalizar(dados.get("nome"))
    if not nome:
        raise ErroDeNegocio("Informe o nome do produto.")
    if len(nome) > TAMANHO_MAX_NOME:
        raise ErroDeNegocio(f"O nome pode ter no máximo {TAMANHO_MAX_NOME} caracteres.")

    codigo = _normalizar(dados.get("codigo"))
    if not codigo:
        raise ErroDeNegocio("Informe o código do produto.")
    if len(codigo) > TAMANHO_MAX_CODIGO:
        raise ErroDeNegocio(f"O código pode ter no máximo {TAMANHO_MAX_CODIGO} caracteres.")
    ignorar = produto_atual.id if produto_atual else None
    if _codigo_em_uso(codigo, ignorar_id=ignorar):
        raise ErroDeNegocio(_mensagem_codigo_duplicado(codigo))

    unidade = (dados.get("unidade_medida") or "").strip().upper()
    if unidade not in UNIDADES:
        raise ErroDeNegocio("Selecione uma unidade de medida válida.")

    try:
        categoria_id = int(dados.get("categoria_id"))
    except (TypeError, ValueError):
        raise ErroDeNegocio("Selecione uma categoria.")
    categoria = db.session.get(Categoria, categoria_id)
    if categoria is None:
        raise ErroDeNegocio("Categoria não encontrada.")
    mudou_de_categoria = produto_atual is None or produto_atual.categoria_id != categoria.id
    if not categoria.ativo and mudou_de_categoria:  # RN10
        raise ErroDeNegocio(f'A categoria "{categoria.nome}" está inativa.')

    return {
        "nome": nome,
        "codigo": codigo,
        "unidade_medida": unidade,
        "categoria_id": categoria.id,
        "preco_custo": validar_decimal(dados.get("preco_custo"), "Preço de custo", 2, PRECO_MAXIMO),
        "preco_venda": validar_decimal(dados.get("preco_venda"), "Preço de venda", 2, PRECO_MAXIMO),
        "estoque_minimo": validar_decimal(
            dados.get("estoque_minimo"), "Estoque mínimo", 3, QUANTIDADE_MAXIMA
        ),
    }


def buscar(produto_id):
    produto = db.session.get(Produto, produto_id)
    if produto is None:
        raise ErroDeNegocio("Produto não encontrado.")
    return produto


def listar(busca="", categoria_id=None, incluir_inativos=False, apenas_estoque_baixo=False):
    """Lista produtos por nome. A busca procura no nome OU no código.

    joinedload traz a categoria junto na mesma consulta, evitando o problema
    "N+1" (uma consulta extra por produto da lista).
    """
    consulta = select(Produto).options(joinedload(Produto.categoria)).order_by(Produto.nome)
    if not incluir_inativos:
        consulta = consulta.where(Produto.ativo.is_(True))
    if categoria_id:
        consulta = consulta.where(Produto.categoria_id == categoria_id)
    produtos = db.session.execute(consulta).scalars().all()

    termo = _normalizar(busca).casefold()
    if termo:
        produtos = [
            p for p in produtos if termo in p.nome.casefold() or termo in p.codigo.casefold()
        ]
    if apenas_estoque_baixo:
        produtos = [p for p in produtos if p.estoque_baixo]
    return produtos


def criar(dados):
    limpos = _validar(dados)
    # RN12: todo produto novo começa com saldo 0.
    produto = Produto(**limpos, quantidade_estoque=Decimal("0"))
    db.session.add(produto)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ErroDeNegocio(_mensagem_codigo_duplicado(limpos["codigo"]))
    return produto


def editar(produto_id, dados):
    produto = buscar(produto_id)
    limpos = _validar(dados, produto_atual=produto)

    if limpos["unidade_medida"] != produto.unidade_medida:  # RN11
        if produto.quantidade_estoque != 0 or produto.movimentacoes:
            raise ErroDeNegocio(
                "Não é possível mudar a unidade de medida: o produto já tem estoque "
                "ou histórico de movimentações."
            )

    for campo, valor in limpos.items():
        setattr(produto, campo, valor)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ErroDeNegocio(_mensagem_codigo_duplicado(limpos["codigo"]))
    return produto


def alternar_ativo(produto_id):
    produto = buscar(produto_id)
    if not produto.ativo and not produto.categoria.ativo:  # RN10
        raise ErroDeNegocio(
            f'Reative primeiro a categoria "{produto.categoria.nome}" '
            "para poder reativar este produto."
        )
    produto.ativo = not produto.ativo
    db.session.commit()
    return produto


def avisos(produto):
    """RN13: situações permitidas, mas que merecem atenção do dono."""
    if produto.preco_venda == 0:
        return "Atenção: o preço de venda está zerado."
    if produto.preco_venda < produto.preco_custo:
        return "Atenção: o preço de venda está abaixo do preço de custo (venda com prejuízo)."
    return None
