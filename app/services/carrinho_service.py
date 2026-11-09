"""Carrinho do PDV, guardado na SESSÃO do Flask (um cookie assinado).

Conceitos:
- O carrinho guarda só {id do produto: quantidade}. NUNCA guarda preço: os
  preços são lidos do banco a cada tela e na finalização. Assim ninguém consegue
  "baixar o preço" mexendo no navegador.
- As funções recebem a `sessao` (um dicionário), então podem ser testadas sem
  abrir navegador.
- Validações de unidade (RN14) e de saldo valem já ao adicionar; na finalização
  tudo é conferido de novo, porque o saldo pode mudar enquanto o cliente passa as compras.
"""
from decimal import Decimal, InvalidOperation

from app.services import estoque_service, produto_service
from app.utils.erros import ErroDeNegocio
from app.utils.formatacao import quantidade as formatar_quantidade

CHAVE_CARRINHO = "pdv_carrinho"
CHAVE_DESCONTO = "pdv_desconto"
CHAVE_TOKEN = "pdv_token"


def ler(sessao):
    """Devolve {produto_id (int): quantidade (Decimal)}. Dado corrompido é ignorado."""
    bruto = sessao.get(CHAVE_CARRINHO) or {}
    itens = {}
    for chave, valor in bruto.items():
        try:
            quantidade = Decimal(str(valor))
            if chave and int(chave) > 0 and quantidade.is_finite() and quantidade > 0:
                itens[int(chave)] = quantidade
        except (ValueError, InvalidOperation):
            continue
    return itens


def _salvar(sessao, itens):
    # Reatribuir a chave inteira avisa o Flask que a sessão mudou.
    sessao[CHAVE_CARRINHO] = {str(i): format(q, "f") for i, q in itens.items()}


def _produto_ativo(produto_id):
    produto = produto_service.buscar(produto_id)
    if not produto.ativo:
        raise ErroDeNegocio(f'O produto "{produto.nome}" está inativo.')
    return produto


def _conferir_saldo(produto, quantidade):
    if quantidade > produto.quantidade_estoque:
        raise ErroDeNegocio(
            f'Saldo insuficiente de "{produto.nome}": há '
            f"{formatar_quantidade(produto.quantidade_estoque)} {produto.unidade_medida}."
        )


def adicionar(sessao, produto_id, quantidade="1"):
    """Soma a quantidade ao item (ou cria o item)."""
    produto = _produto_ativo(produto_id)
    quantidade = estoque_service.validar_quantidade(quantidade, produto)
    itens = ler(sessao)
    nova = itens.get(produto.id, Decimal("0")) + quantidade
    _conferir_saldo(produto, nova)
    itens[produto.id] = nova
    _salvar(sessao, itens)
    return produto


def definir_quantidade(sessao, produto_id, quantidade):
    """Troca a quantidade de um item que já está no carrinho. Zero remove o item."""
    itens = ler(sessao)
    if produto_id not in itens:
        raise ErroDeNegocio("Este item não está no carrinho.")
    produto = _produto_ativo(produto_id)
    nova = estoque_service.validar_quantidade(quantidade, produto, permitir_zero=True)
    if nova == 0:
        del itens[produto_id]
    else:
        _conferir_saldo(produto, nova)
        itens[produto_id] = nova
    _salvar(sessao, itens)


def remover(sessao, produto_id):
    itens = ler(sessao)
    itens.pop(produto_id, None)
    _salvar(sessao, itens)


def ler_desconto(sessao):
    """Devolve (tipo, valor) ou None."""
    bruto = sessao.get(CHAVE_DESCONTO)
    if isinstance(bruto, (list, tuple)) and len(bruto) == 2:
        return bruto[0], bruto[1]
    return None


def definir_desconto(sessao, tipo, valor):
    sessao[CHAVE_DESCONTO] = [tipo, valor]


def limpar_desconto(sessao):
    sessao.pop(CHAVE_DESCONTO, None)


def limpar(sessao):
    """Esvazia o carrinho e o desconto (venda concluída ou cancelada)."""
    sessao.pop(CHAVE_CARRINHO, None)
    sessao.pop(CHAVE_DESCONTO, None)
