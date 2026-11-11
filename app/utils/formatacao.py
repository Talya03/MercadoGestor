"""Filtros de exibição para os templates (Jinja): {{ valor|moeda }}."""
from decimal import Decimal

from app.utils.datas import para_local


def moeda(valor):
    """6.9 -> 'R$ 6,90'    1234.5 -> 'R$ 1.234,50'"""
    if valor is None:
        return "—"
    texto = f"{Decimal(valor).quantize(Decimal('0.01')):,.2f}"
    # Formato en-US "1,234.50" -> pt-BR "1.234,50" (troca em 3 passos para não colidir).
    texto = texto.replace(",", "#").replace(".", ",").replace("#", ".")
    return f"R$ {texto}"


def percentual(valor):
    """30 -> '30,00%'    None -> '—'"""
    if valor is None:
        return "—"
    return f"{Decimal(valor).quantize(Decimal('0.01')):.2f}".replace(".", ",") + "%"


def quantidade(valor):
    """12.350 -> '12,35'    5.000 -> '5'    0 -> '0'"""
    if valor is None:
        return "—"
    return format(Decimal(valor).normalize(), "f").replace(".", ",")


def quantidade_com_sinal(valor):
    """+10 para aumentos, -3 para reduções (usado no histórico)."""
    texto = quantidade(valor)
    return f"+{texto}" if Decimal(valor) > 0 else texto


def data_hora(valor):
    """datetime em UTC -> '08/11/2026 17:30' no horário local."""
    if valor is None:
        return "—"
    return para_local(valor).strftime("%d/%m/%Y %H:%M")
