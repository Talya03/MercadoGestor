"""Modelo Lancamento: uma receita ou despesa do mercado (conta a pagar quando pendente).

Datas financeiras são DATAS do dia no horário do mercado (Date), não instantes em UTC:
"vence dia 10" é um dia do calendário local.
"""
from datetime import datetime, timezone

from app.extensions import db

TIPOS_LANCAMENTO = {"DESPESA": "Despesa", "RECEITA": "Receita"}

# Categoria "MERCADORIA" só nasce de uma Compra (RN41); as demais são digitadas.
CATEGORIA_MERCADORIA = "MERCADORIA"
CATEGORIAS = {
    "MERCADORIA": "Compra de mercadoria",
    "ALUGUEL": "Aluguel",
    "ENERGIA": "Energia elétrica",
    "AGUA": "Água",
    "SALARIOS": "Salários e encargos",
    "IMPOSTOS": "Impostos e taxas",
    "MANUTENCAO": "Manutenção e reparos",
    "OUTRAS_DESPESAS": "Outras despesas",
    "OUTRAS_RECEITAS": "Outras receitas",
}
CATEGORIAS_DESPESA = [c for c in CATEGORIAS if c != "OUTRAS_RECEITAS"]
CATEGORIAS_RECEITA = ["OUTRAS_RECEITAS"]


def _agora():
    return datetime.now(timezone.utc)


def _lista_sql(chaves):
    return ", ".join(f"'{c}'" for c in chaves)


class Lancamento(db.Model):
    __tablename__ = "lancamento"

    __table_args__ = (
        db.CheckConstraint("tipo IN ('DESPESA', 'RECEITA')", name="ck_lancamento_tipo"),
        db.CheckConstraint(f"categoria IN ({_lista_sql(CATEGORIAS)})", name="ck_lancamento_categoria"),
        db.CheckConstraint("valor > 0", name="ck_lancamento_valor"),
        # Receita sempre nasce recebida; cancelado nunca está pago.
        db.CheckConstraint("tipo = 'DESPESA' OR pago_em IS NOT NULL", name="ck_lancamento_receita_recebida"),
        db.CheckConstraint("NOT cancelado OR pago_em IS NULL", name="ck_lancamento_cancelado_sem_pagamento"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(10), nullable=False)
    categoria = db.Column(db.String(20), nullable=False)
    descricao = db.Column(db.String(120), nullable=False)
    valor = db.Column(db.Numeric(10, 2), nullable=False)
    vencimento = db.Column(db.Date, nullable=False)  # data da receita, ou vencimento da conta
    pago_em = db.Column(db.Date)  # None = pendente (conta a pagar)
    cancelado = db.Column(db.Boolean, nullable=False, default=False)
    # Conta a pagar gerada por uma compra (no máximo uma por compra).
    compra_id = db.Column(db.Integer, db.ForeignKey("compra.id"), unique=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=_agora)
    # Quem registrou (auditoria, RN67). Vazio nos registros anteriores à v0.12.
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"))
    usuario = db.relationship("Usuario")

    compra = db.relationship("Compra", back_populates="lancamento")

    @property
    def categoria_nome(self):
        return CATEGORIAS.get(self.categoria, self.categoria)

    @property
    def situacao(self):
        if self.cancelado:
            return "CANCELADO"
        return "PAGO" if self.pago_em else "PENDENTE"

    def __repr__(self):
        return f"<Lancamento {self.id} {self.tipo} {self.valor} {self.situacao}>"
