"""Modelos de Compra e Item de Compra (mercadoria comprada de fornecedor).

Relacionamentos:  Fornecedor 1—N Compra,  Compra 1—N ItemCompra,  Produto 1—N ItemCompra.

Como na venda, o item guarda o custo PAGO naquela compra (custo_unitario):
o histórico não muda quando o custo do produto for atualizado numa compra futura.
"""
from datetime import datetime, timezone

from app.extensions import db


def _agora():
    return datetime.now(timezone.utc)


class Compra(db.Model):
    __tablename__ = "compra"

    __table_args__ = (db.CheckConstraint("total > 0", name="ck_compra_total"),)

    id = db.Column(db.Integer, primary_key=True)
    fornecedor_id = db.Column(db.Integer, db.ForeignKey("fornecedor.id"), nullable=False)
    data_hora = db.Column(db.DateTime, nullable=False, default=_agora)
    numero_documento = db.Column(db.String(30))  # nº da nota/pedido do fornecedor (opcional)
    observacao = db.Column(db.String(255))
    total = db.Column(db.Numeric(10, 2), nullable=False)
    # Token de envio (idempotência), igual ao da venda: o mesmo formulário
    # enviado duas vezes não registra a compra (nem dá entrada no estoque) duas vezes.
    token_envio = db.Column(db.String(36), unique=True)

    fornecedor = db.relationship("Fornecedor", back_populates="compras")
    itens = db.relationship("ItemCompra", back_populates="compra", order_by="ItemCompra.id")
    # Conta a pagar gerada por esta compra (à vista = já paga; a prazo = pendente).
    lancamento = db.relationship("Lancamento", back_populates="compra", uselist=False)

    def __repr__(self):
        return f"<Compra {self.id} total={self.total}>"


class ItemCompra(db.Model):
    __tablename__ = "item_compra"

    __table_args__ = (
        db.UniqueConstraint("compra_id", "produto_id", name="uq_item_compra_produto"),
        db.CheckConstraint("quantidade > 0", name="ck_item_compra_quantidade"),
        db.CheckConstraint("custo_unitario > 0", name="ck_item_compra_custo"),
        db.CheckConstraint("subtotal > 0", name="ck_item_compra_subtotal"),
    )

    id = db.Column(db.Integer, primary_key=True)
    compra_id = db.Column(db.Integer, db.ForeignKey("compra.id"), nullable=False)
    produto_id = db.Column(db.Integer, db.ForeignKey("produto.id"), nullable=False)
    quantidade = db.Column(db.Numeric(10, 3), nullable=False)
    custo_unitario = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)

    compra = db.relationship("Compra", back_populates="itens")
    produto = db.relationship("Produto")

    def __repr__(self):
        return f"<ItemCompra compra={self.compra_id} produto={self.produto_id} qtd={self.quantidade}>"
