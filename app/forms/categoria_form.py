"""Formulário de Categoria.

Conceito: o FlaskForm faz a validação básica no servidor (campo vazio,
tamanho) e já inclui o token CSRF. As regras de negócio (nome duplicado)
continuam no service.
"""
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length, Optional


class CategoriaForm(FlaskForm):
    nome = StringField(
        "Nome",
        validators=[
            DataRequired(message="Informe o nome da categoria."),
            Length(max=80, message="O nome pode ter no máximo 80 caracteres."),
        ],
    )
    descricao = StringField(
        "Descrição (opcional)",
        validators=[
            Optional(),
            Length(max=255, message="A descrição pode ter no máximo 255 caracteres."),
        ],
    )
    submit = SubmitField("Salvar")
