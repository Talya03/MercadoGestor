"""Conversão e formatação de números no padrão brasileiro.

Conceito: o usuário digita "4,50" (vírgula), mas o Python/Decimal só entende
"4.50" (ponto). Convertemos na entrada e formatamos de volta na saída.
Dinheiro e quantidades usam Decimal (nunca float) para não gerar centavos errados.
"""
import re
from decimal import Decimal

_PADRAO_NUMERO = re.compile(r"-?(\d+\.?\d*|\.\d+)")
_MSG_INVALIDO = "Valor inválido. Use apenas números, por exemplo 4,50."


def parse_decimal_br(texto):
    """Converte texto digitado em Decimal.

    Aceita: "4,50"  "4.50"  "1.234,56"  " 7 "  "-3" (o sinal é tratado depois).
    Recusa: vazio, letras, "NaN", "Infinity", notação científica ("1e5").
    Levanta ValueError com mensagem pronta para o usuário.
    """
    if isinstance(texto, Decimal):
        valor = texto
    elif isinstance(texto, int) and not isinstance(texto, bool):
        valor = Decimal(texto)
    else:
        limpo = str(texto if texto is not None else "").strip().replace(" ", "")
        if not limpo:
            raise ValueError("Informe um valor.")
        if "," in limpo:
            # Com vírgula, os pontos são separadores de milhar: 1.234,56
            limpo = limpo.replace(".", "").replace(",", ".")
        if not _PADRAO_NUMERO.fullmatch(limpo):
            raise ValueError(_MSG_INVALIDO)
        valor = Decimal(limpo)

    # Decimal("NaN") e Decimal("Infinity") são "válidos" para o Python,
    # mas não fazem sentido como preço ou quantidade.
    if not valor.is_finite():
        raise ValueError(_MSG_INVALIDO)
    return valor


def formatar_decimal_br(valor, casas=2, aparar_zeros=False):
    """Decimal -> texto com vírgula, para preencher campos de formulário."""
    valor = Decimal(valor)
    if aparar_zeros:
        texto = format(valor.normalize(), "f")  # 5.000 -> "5", 12.350 -> "12.35"
    else:
        texto = format(valor.quantize(Decimal(1).scaleb(-casas)), "f")
    return texto.replace(".", ",")
