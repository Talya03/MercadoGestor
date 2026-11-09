"""Campos de formulário personalizados."""
from wtforms import DecimalField
from wtforms.validators import ValidationError
from wtforms.widgets import TextInput

from app.utils.numeros import formatar_decimal_br, parse_decimal_br


def nao_negativo(form, campo):
    """Validador: recusa números negativos (se o valor nem foi lido, não opina)."""
    if campo.data is not None and campo.data < 0:
        raise ValidationError("O valor não pode ser negativo.")


class DecimalBRField(DecimalField):
    """Campo decimal que entende vírgula ("4,50") e mostra valores com vírgula.

    Usa <input type="text"> (e não type="number") porque o navegador
    nem sempre aceita vírgula em campos numéricos.
    """

    widget = TextInput()

    def __init__(self, label=None, validators=None, casas=2, aparar_zeros=False, **kwargs):
        super().__init__(label, validators, places=None, **kwargs)
        self.casas = casas
        self.aparar_zeros = aparar_zeros

    def process_formdata(self, valuelist):
        if not valuelist:
            return
        if not str(valuelist[0]).strip():
            # Campo vazio: deixa o validador InputRequired dar a mensagem.
            self.data = None
            return
        try:
            self.data = parse_decimal_br(valuelist[0])
        except ValueError as erro:
            self.data = None
            raise ValueError(str(erro))

    def _value(self):
        if self.raw_data:  # reexibe exatamente o que a pessoa digitou (ao errar)
            return self.raw_data[0]
        if self.data is None:
            return ""
        return formatar_decimal_br(self.data, self.casas, self.aparar_zeros)
