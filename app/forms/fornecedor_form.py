"""Formulário de Fornecedor (validações de formato ficam no service)."""
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length, Optional


class FornecedorForm(FlaskForm):
    nome = StringField(
        "Nome",
        validators=[
            DataRequired(message="Informe o nome do fornecedor."),
            Length(max=120, message="O nome pode ter no máximo 120 caracteres."),
        ],
    )
    documento = StringField(
        "CPF/CNPJ (opcional)",
        validators=[Optional(), Length(max=30, message="CPF/CNPJ longo demais.")],
        render_kw={"inputmode": "numeric", "autocomplete": "off"},
    )
    telefone = StringField(
        "Telefone (opcional)",
        validators=[Optional(), Length(max=30, message="Telefone longo demais.")],
        render_kw={"inputmode": "tel"},
    )
    contato = StringField(
        "Contato / vendedor (opcional)",
        validators=[Optional(), Length(max=80, message="O contato pode ter no máximo 80 caracteres.")],
    )
    submit = SubmitField("Salvar")
