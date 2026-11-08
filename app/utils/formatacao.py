"""Filtros de exibição para os templates (Jinja): {{ valor|moeda }}."""
from decimal import Decimal


def moeda(valor):
    """6.9 -> 'R$ 6,90'    1234.5 -> 'R$ 1.234,50'"""
    if valor is None:
        return "—"
    texto = f"{Decimal(valor).quantize(Decimal('0.01')):,.2f}"
    # Formato en-US "1,234.50" -> pt-BR "1.234,50" (troca em 3 passos para não colidir).
    texto = texto.replace(",", "#").replace(".", ",").replace("#", ".")
    return f"R$ {texto}"


def quantidade(valor):
    """12.350 -> '12,35'    5.000 -> '5'    0 -> '0'"""
    if valor is None:
        return "—"
    return format(Decimal(valor).normalize(), "f").replace(".", ",")
