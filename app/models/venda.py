"""Modelos de Venda, Item de Venda e Pagamento (PDV).

Relacionamentos:  Venda 1—N ItemVenda,  Venda 1—N Pagamento,  Produto 1—N ItemVenda.

Decisão de modelagem importante: o item da venda COPIA o preço de venda e o
custo do produto no momento da venda (preco_unitario, custo_unitario).
Se o preço do leite subir amanhã, o comprovante de hoje continua mostrando o
valor que foi realmente cobrado. O custo copiado também permite calcular,
mais tarde, o lucro bruto de cada venda (Fase 6/7).
"""
from datetime import datetime, timezone

from app.extensions import db

# Chave guardada no banco -> nome mostrado na tela.
FORMAS_PAGAMENTO = {
    "DINHEIRO": "Dinheiro",
    "PIX": "Pix",
    "DEBITO": "Cartão de débito",
    "CREDITO": "Cartão de crédito",
}


def _agora():
    return datetime.now(timezone.utc)


class Venda(db.Model):
    __tablename__ = "venda"

    __table_args__ = (
        db.CheckConstraint("subtotal >= 0", name="ck_venda_subtotal"),
        db.CheckConstraint("desconto >= 0", name="ck_venda_desconto"),
        db.CheckConstraint("desconto <= subtotal", name="ck_venda_desconto_max"),
        db.CheckConstraint("total >= 0", name="ck_venda_total"),
        db.CheckConstraint("total <= subtotal", name="ck_venda_total_max"),
    )

    id = db.Column(db.Integer, primary_key=True)
    data_hora = db.Column(db.DateTime, nullable=False, default=_agora)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)
    desconto = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(10, 2), nullable=False)
    # Token de envio (idempotência): a tela gera um valor único por venda.
    # Se o mesmo formulário for enviado duas vezes (clique duplo, internet
    # lenta), a segunda tentativa bate na restrição UNIQUE e é recusada,
    # em vez de vender e baixar o estoque duas vezes.
    token_envio = db.Column(db.String(36), unique=True)

    itens = db.relationship("ItemVenda", back_populates="venda", order_by="ItemVenda.id")
    pagamentos = db.relationship("Pagamento", back_populates="venda", order_by="Pagamento.id")

    def __repr__(self):
        return f"<Venda {self.id} total={self.total}>"


class ItemVenda(db.Model):
    __tablename__ = "item_venda"

    __table_args__ = (
        db.UniqueConstraint("venda_id", "produto_id", name="uq_item_venda_produto"),
        db.CheckConstraint("quantidade > 0", name="ck_item_venda_quantidade"),
        db.CheckConstraint("preco_unitario >= 0", name="ck_item_venda_preco"),
        db.CheckConstraint("custo_unitario >= 0", name="ck_item_venda_custo"),
        db.CheckConstraint("subtotal >= 0", name="ck_item_venda_subtotal"),
    )

    id = db.Column(db.Integer, primary_key=True)
    venda_id = db.Column(db.Integer, db.ForeignKey("venda.id"), nullable=False)
    produto_id = db.Column(db.Integer, db.ForeignKey("produto.id"), nullable=False)
    quantidade = db.Column(db.Numeric(10, 3), nullable=False)
    preco_unitario = db.Column(db.Numeric(10, 2), nullable=False)
    custo_unitario = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)

    venda = db.relationship("Venda", back_populates="itens")
    produto = db.relationship("Produto")

    def __repr__(self):
        return f"<ItemVenda venda={self.venda_id} produto={self.produto_id} qtd={self.quantidade}>"


class Pagamento(db.Model):
    __tablename__ = "pagamento"

    __table_args__ = (
        db.CheckConstraint(
            "forma IN ('DINHEIRO', 'PIX', 'DEBITO', 'CREDITO')", name="ck_pagamento_forma"
        ),
        db.CheckConstraint("valor > 0", name="ck_pagamento_valor"),
        db.CheckConstraint("troco >= 0", name="ck_pagamento_troco"),
    )

    id = db.Column(db.Integer, primary_key=True)
    venda_id = db.Column(db.Integer, db.ForeignKey("venda.id"), nullable=False)
    forma = db.Column(db.String(10), nullable=False)
    # Quanto este pagamento abate da venda.
    valor = db.Column(db.Numeric(10, 2), nullable=False)
    # Só para dinheiro: quanto o cliente entregou e quanto voltou de troco.
    valor_recebido = db.Column(db.Numeric(10, 2))
    troco = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    venda = db.relationship("Venda", back_populates="pagamentos")

    @property
    def forma_nome(self):
        return FORMAS_PAGAMENTO.get(self.forma, self.forma)

    def __repr__(self):
        return f"<Pagamento venda={self.venda_id} {self.forma} {self.valor}>"
