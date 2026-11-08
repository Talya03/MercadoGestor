"""Modelo Produto."""
from datetime import datetime, timezone
from decimal import Decimal

from app.extensions import db


def _agora():
    return datetime.now(timezone.utc)


class Produto(db.Model):
    __tablename__ = "produto"

    # CheckConstraint = regra que o próprio banco garante (última barreira
    # de defesa, mesmo que algum código esqueça de validar).
    __table_args__ = (
        db.CheckConstraint("preco_custo >= 0", name="ck_produto_preco_custo"),
        db.CheckConstraint("preco_venda >= 0", name="ck_produto_preco_venda"),
        db.CheckConstraint("quantidade_estoque >= 0", name="ck_produto_estoque"),
        db.CheckConstraint("estoque_minimo >= 0", name="ck_produto_estoque_minimo"),
    )

    id = db.Column(db.Integer, primary_key=True)
    categoria_id = db.Column(db.Integer, db.ForeignKey("categoria.id"), nullable=False)
    nome = db.Column(db.String(120), nullable=False)
    # RN02: código (interno ou de barras) é único.
    codigo = db.Column(db.String(50), nullable=False, unique=True)
    unidade_medida = db.Column(db.String(10), nullable=False, default="UN")
    preco_custo = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0"))
    preco_venda = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0"))
    # Saldo atual. RN04: nunca negativo. Só o service de estoque deve alterá-lo.
    quantidade_estoque = db.Column(db.Numeric(10, 3), nullable=False, default=Decimal("0"))
    estoque_minimo = db.Column(db.Numeric(10, 3), nullable=False, default=Decimal("0"))
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=_agora)
    atualizado_em = db.Column(db.DateTime, nullable=False, default=_agora, onupdate=_agora)

    categoria = db.relationship("Categoria", back_populates="produtos")
    movimentacoes = db.relationship("MovimentacaoEstoque", back_populates="produto")

    @property
    def estoque_baixo(self):
        """RN07: True quando o saldo está igual ou abaixo do mínimo."""
        return self.quantidade_estoque <= self.estoque_minimo

    def __repr__(self):
        return f"<Produto {self.id} {self.codigo} {self.nome!r}>"
