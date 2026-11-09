"""Formulário de movimentação de estoque (usado por entrada, saída e ajuste)."""
from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange

from app.forms.campos import DecimalBRField, nao_negativo


class MovimentacaoForm(FlaskForm):
    produto_id = SelectField(
        "Produto",
        coerce=int,
        validate_choice=False,  # existência/atividade do produto é regra do service
        validators=[NumberRange(min=1, message="Selecione um produto.")],
    )
    quantidade = DecimalBRField(
        "Quantidade",  # o rótulo muda conforme a operação (definido na rota)
        casas=3,
        aparar_zeros=True,
        validators=[InputRequired(message="Informe a quantidade."), nao_negativo],
        render_kw={"inputmode": "decimal", "placeholder": "0"},
    )
    motivo = StringField(
        "Motivo",
        validators=[
            DataRequired(message="Informe o motivo da movimentação."),
            Length(max=255, message="O motivo pode ter no máximo 255 caracteres."),
        ],
        render_kw={"list": "motivos-sugeridos", "autocomplete": "off", "maxlength": 255},
    )
    submit = SubmitField("Registrar")
