"""Importar os modelos aqui garante que o SQLAlchemy os conheça
antes de db.create_all() criar as tabelas."""
from app.models.categoria import Categoria
from app.models.compra import Compra, ItemCompra
from app.models.fornecedor import Fornecedor
from app.models.lancamento import CATEGORIAS, CATEGORIA_MERCADORIA, Lancamento, TIPOS_LANCAMENTO
from app.models.movimentacao_estoque import MovimentacaoEstoque, TIPOS_MOVIMENTACAO
from app.models.produto import Produto
from app.models.usuario import PERFIS, Usuario
from app.models.venda import FORMAS_PAGAMENTO, ItemVenda, Pagamento, Venda

__all__ = [
    "Categoria",
    "Produto",
    "MovimentacaoEstoque",
    "TIPOS_MOVIMENTACAO",
    "Venda",
    "ItemVenda",
    "Pagamento",
    "Fornecedor",
    "Usuario",
    "PERFIS",
    "Lancamento",
    "TIPOS_LANCAMENTO",
    "CATEGORIAS",
    "CATEGORIA_MERCADORIA",
    "Compra",
    "ItemCompra",
    "FORMAS_PAGAMENTO",
]
