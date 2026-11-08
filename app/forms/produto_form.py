"""Formulário de Produto."""
from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField
from wtforms.fields import SelectChoice
from wtforms.validators import (
    DataRequired,
    InputRequired,
    Length,
    NumberRange,
    ValidationError,
)

from app.forms.campos import DecimalBRField
from app.services.produto_service import UNIDADES

CAMPOS = (
    "categoria_id",
    "nome",
    "codigo",
    "unidade_medida",
    "preco_custo",
    "preco_venda",
    "estoque_minimo",
)


def _nao_negativo(form, campo):
    if campo.data is not None and campo.data < 0:
        raise ValidationError("O valor não pode ser negativo.")


class ProdutoForm(FlaskForm):
    categoria_id = SelectField(
        "Categoria",
        coerce=int,
        validate_choice=False,  # a existência/atividade da categoria é regra do service
        validators=[NumberRange(min=1, message="Selecione uma categoria.")],
    )
    nome = StringField(
        "Nome",
        validators=[
            DataRequired(message="Informe o nome do produto."),
            Length(max=120, message="O nome pode ter no máximo 120 caracteres."),
        ],
    )
    codigo = StringField(
        "Código (interno ou de barras)",
        validators=[
            DataRequired(message="Informe o código do produto."),
            Length(max=50, message="O código pode ter no máximo 50 caracteres."),
        ],
    )
    unidade_medida = SelectField(
        "Unidade de medida",
        choices=[SelectChoice(sigla, rotulo) for sigla, rotulo in UNIDADES.items()],
        default="UN",
    )
    # Atenção: usamos InputRequired (e não DataRequired) nos números, porque
    # DataRequired trata o valor 0 como "vazio" e recusaria um preço de 0,00.
    preco_custo = DecimalBRField(
        "Preço de custo (R$)",
        casas=2,
        validators=[InputRequired(message="Informe o preço de custo."), _nao_negativo],
        render_kw={"inputmode": "decimal", "placeholder": "0,00"},
    )
    preco_venda = DecimalBRField(
        "Preço de venda (R$)",
        casas=2,
        validators=[InputRequired(message="Informe o preço de venda."), _nao_negativo],
        render_kw={"inputmode": "decimal", "placeholder": "0,00"},
    )
    estoque_minimo = DecimalBRField(
        "Estoque mínimo",
        casas=3,
        aparar_zeros=True,
        validators=[InputRequired(message="Informe o estoque mínimo."), _nao_negativo],
        render_kw={"inputmode": "decimal", "placeholder": "0"},
    )
    submit = SubmitField("Salvar")

    def dados(self):
        """Dicionário com os campos editáveis, pronto para o service."""
        return {campo: getattr(self, campo).data for campo in CAMPOS}
