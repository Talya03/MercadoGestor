"""Modelo Fornecedor (quem vende mercadoria ao mercado: distribuidora, padaria, hortifrúti...)."""
from app.extensions import db


class Fornecedor(db.Model):
    __tablename__ = "fornecedor"

    id = db.Column(db.Integer, primary_key=True)
    # RN31: o nome é único (sem diferenciar maiúsculas/minúsculas, checado no service).
    nome = db.Column(db.String(120), nullable=False, unique=True)
    # CPF (11 dígitos) ou CNPJ (14), só números. Opcional, mas único quando informado
    # (o SQLite aceita vários NULL em colunas UNIQUE).
    documento = db.Column(db.String(14), unique=True)
    telefone = db.Column(db.String(20))
    contato = db.Column(db.String(80))  # nome do vendedor/representante
    # RN32: desativamos em vez de excluir (as compras antigas continuam apontando para ele).
    ativo = db.Column(db.Boolean, nullable=False, default=True)

    compras = db.relationship("Compra", back_populates="fornecedor")

    def __repr__(self):
        return f"<Fornecedor {self.id} {self.nome!r}>"
