"""Modelo MovimentacaoEstoque: histórico de tudo que altera o saldo."""
from datetime import datetime, timezone

from app.extensions import db

TIPOS_MOVIMENTACAO = ("ENTRADA", "SAIDA", "AJUSTE")


def _agora():
    return datetime.now(timezone.utc)


class MovimentacaoEstoque(db.Model):
    __tablename__ = "movimentacao_estoque"

    __table_args__ = (
        db.CheckConstraint(
            "tipo IN ('ENTRADA', 'SAIDA', 'AJUSTE')", name="ck_movimentacao_tipo"
        ),
        # A quantidade movimentada é sempre positiva; o tipo define o sentido.
        db.CheckConstraint("quantidade > 0", name="ck_movimentacao_quantidade"),
        db.CheckConstraint("saldo_anterior >= 0", name="ck_movimentacao_saldo_anterior"),
        # RN04: o saldo depois da movimentação nunca pode ser negativo.
        db.CheckConstraint("saldo_posterior >= 0", name="ck_movimentacao_saldo_posterior"),
    )

    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.Integer, db.ForeignKey("produto.id"), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)
    quantidade = db.Column(db.Numeric(10, 3), nullable=False)
    saldo_anterior = db.Column(db.Numeric(10, 3), nullable=False)
    saldo_posterior = db.Column(db.Numeric(10, 3), nullable=False)
    # RN05: toda movimentação tem um motivo (ex.: "Compra", "Produto vencido").
    motivo = db.Column(db.String(255), nullable=False)
    data_hora = db.Column(db.DateTime, nullable=False, default=_agora)

    produto = db.relationship("Produto", back_populates="movimentacoes")

    def __repr__(self):
        return f"<Movimentacao {self.id} {self.tipo} {self.quantidade}>"
