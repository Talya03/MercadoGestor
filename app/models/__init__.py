"""Importar os modelos aqui garante que o SQLAlchemy os conheça
antes de db.create_all() criar as tabelas."""
from app.models.categoria import Categoria
from app.models.movimentacao_estoque import MovimentacaoEstoque, TIPOS_MOVIMENTACAO
from app.models.produto import Produto

__all__ = ["Categoria", "Produto", "MovimentacaoEstoque", "TIPOS_MOVIMENTACAO"]
