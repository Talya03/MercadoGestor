"""Precificação: quanto cobrar para ganhar a margem que você quer.

Conceitos (exemplo de mercado de bairro):
- MARGEM = a parte do preço de venda que sobra como lucro. Vendeu a R$ 10,00 e o produto custou R$ 7,00:
  sobraram R$ 3,00, margem de 30% (3 / 10).
- MARKUP = quanto se soma em cima do custo (3 / 7 = 42,86%). Parece parecido, mas NÃO é a mesma coisa:
  "colocar 30% em cima do custo" dá margem de só 23%. Este módulo trabalha com margem.
- DESPESAS SOBRE A VENDA = o que sai de cada venda antes do lucro, em % do preço (taxa da maquininha,
  imposto do Simples...). Entra na conta para o lucro desejado ser o que de fato sobra.

Regras:
- RN77 Preço sugerido = custo / (1 − (margem + despesas)/100), arredondado PARA CIMA ao centavo
       (nunca fica abaixo da margem pedida). Ex.: custo 7,00, margem 30%, despesas 0% -> 10,00.
- RN78 Margem desejada e despesas não podem ser negativas e a soma precisa ser MENOR que 100%
       (com 100% o preço seria infinito).
- RN79 Produto sem custo (zero) não tem sugestão: mostramos o aviso em vez de inventar um preço.
- RN80 "Aplicar" recalcula o preço NO SERVIDOR com a margem e as despesas informadas; o preço nunca vem
       pronto do navegador. Só produtos ativos.
- RN81 Margem atual (líquida) = (preço − custo − despesas) / preço. Produto está ABAIXO da meta quando o
       preço de venda é menor que o preço sugerido.
- Simular não grava nada. Só "Aplicar" altera o preço de venda do produto.
"""
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Produto
from app.services import produto_service
from app.utils.erros import ErroDeNegocio
from app.utils.numeros import validar_decimal

MARGEM_PADRAO = Decimal("30")
DESPESAS_PADRAO = Decimal("0")
LIMITE_PERCENTUAL = Decimal("99.99")
CENTAVO = Decimal("0.01")

SEM_CUSTO, SEM_PRECO, ABAIXO, OK = "SEM_CUSTO", "SEM_PRECO", "ABAIXO", "OK"


def validar_parametros(margem, despesas):
    """Converte o que foi digitado e confere RN78. Devolve (margem, despesas) como Decimal."""
    margem = validar_decimal(margem, "Margem desejada", 2, LIMITE_PERCENTUAL)
    despesas = validar_decimal(despesas, "Despesas sobre a venda", 2, LIMITE_PERCENTUAL)
    if margem + despesas >= 100:
        raise ErroDeNegocio("A margem e as despesas somadas precisam ser menores que 100%.")
    return margem, despesas


def preco_sugerido(custo, margem, despesas=Decimal("0")):
    """RN77/RN79. Devolve Decimal em centavos, ou None se o produto não tem custo."""
    custo = Decimal(custo)
    if custo <= 0:
        return None
    fator = 1 - (Decimal(margem) + Decimal(despesas)) / 100
    preco = (custo / fator).quantize(CENTAVO, rounding=ROUND_CEILING)
    if preco > produto_service.PRECO_MAXIMO:
        raise ErroDeNegocio("O preço sugerido é grande demais para ser cadastrado.")
    return preco


def margem_liquida(custo, preco, despesas=Decimal("0")):
    """RN81, em %, com 2 casas. None se o preço de venda é zero (não há o que medir)."""
    custo, preco = Decimal(custo), Decimal(preco)
    if preco <= 0:
        return None
    lucro = preco - custo - preco * Decimal(despesas) / 100
    return (lucro / preco * 100).quantize(CENTAVO)


def markup(custo, preco):
    """Quanto o preço está acima do custo, em %. None se não há custo."""
    custo, preco = Decimal(custo), Decimal(preco)
    if custo <= 0:
        return None
    return ((preco - custo) / custo * 100).quantize(CENTAVO)


def situacao(produto, sugerido):
    if produto.preco_custo <= 0:
        return SEM_CUSTO
    if produto.preco_venda <= 0:
        return SEM_PRECO
    return ABAIXO if produto.preco_venda < sugerido else OK


def linhas(margem, despesas, busca="", categoria_id=None, apenas_abaixo=False):
    """Uma linha por produto ativo, com a conta feita. `margem`/`despesas` já validadas (Decimal)."""
    resultado = []
    for p in produto_service.listar(busca=busca, categoria_id=categoria_id):
        sugerido = preco_sugerido(p.preco_custo, margem, despesas)
        estado = situacao(p, sugerido)
        if apenas_abaixo and estado not in (ABAIXO, SEM_PRECO):
            continue
        resultado.append({
            "produto": p,
            "sugerido": sugerido,
            "margem_atual": margem_liquida(p.preco_custo, p.preco_venda, despesas),
            "markup_atual": markup(p.preco_custo, p.preco_venda),
            "situacao": estado,
        })
    return resultado


def aplicar(produto_id, margem, despesas):
    """RN80: grava o preço sugerido como novo preço de venda. Devolve (produto, preco_antigo)."""
    margem, despesas = validar_parametros(margem, despesas)
    produto = produto_service.buscar(produto_id)
    if not produto.ativo:
        raise ErroDeNegocio("Produto inativo: reative-o antes de mudar o preço.")
    novo = preco_sugerido(produto.preco_custo, margem, despesas)
    if novo is None:
        raise ErroDeNegocio("Este produto está sem preço de custo; cadastre o custo antes de precificar.")
    antigo = produto.preco_venda
    produto.preco_venda = novo
    db.session.commit()
    return produto, antigo
