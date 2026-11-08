"""Modelo Categoria (ex.: Laticínios, Bebidas, Hortifrúti)."""
from app.extensions import db


class Categoria(db.Model):
    __tablename__ = "categoria"

    id = db.Column(db.Integer, primary_key=True)
    # RN01: o nome da categoria é único.
    nome = db.Column(db.String(80), nullable=False, unique=True)
    descricao = db.Column(db.String(255))
    # RN08: desativamos em vez de excluir.
    ativo = db.Column(db.Boolean, nullable=False, default=True)

    # Lado "1" do relacionamento 1—N: uma categoria tem vários produtos.
    produtos = db.relationship("Produto", back_populates="categoria")

    def __repr__(self):
        return f"<Categoria {self.id} {self.nome!r}>"
