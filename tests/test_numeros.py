"""Testes de conversão e formatação de números (padrão brasileiro)."""
from decimal import Decimal

import pytest

from app.utils.formatacao import moeda, quantidade
from app.utils.numeros import formatar_decimal_br, parse_decimal_br


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("4,50", Decimal("4.50")),
        ("4.50", Decimal("4.50")),
        ("1.234,56", Decimal("1234.56")),
        ("  7  ", Decimal("7")),
        ("0", Decimal("0")),
        (",5", Decimal("0.5")),
        ("-3", Decimal("-3")),  # o sinal é recusado depois, pelas regras de negócio
        (Decimal("2.5"), Decimal("2.5")),
        (3, Decimal("3")),
    ],
)
def test_converte_texto_em_decimal(texto, esperado):
    assert parse_decimal_br(texto) == esperado


@pytest.mark.parametrize(
    "texto", ["", "   ", None, "abc", "R$ 4,50", "1,2,3", "NaN", "Infinity", "-Infinity", "1e5", "4,5,"]
)
def test_recusa_valores_invalidos(texto):
    with pytest.raises(ValueError):
        parse_decimal_br(texto)


def test_nao_usa_float_e_nao_gera_erro_de_centavos():
    # Em float, 0.1 + 0.2 = 0.30000000000000004. Em Decimal, é exato.
    assert parse_decimal_br("0,1") + parse_decimal_br("0,2") == Decimal("0.3")


def test_formata_decimal_com_virgula():
    assert formatar_decimal_br(Decimal("6.9"), casas=2) == "6,90"
    assert formatar_decimal_br(Decimal("5.000"), casas=3, aparar_zeros=True) == "5"
    assert formatar_decimal_br(Decimal("100.000"), casas=3, aparar_zeros=True) == "100"
    assert formatar_decimal_br(Decimal("12.350"), casas=3, aparar_zeros=True) == "12,35"


def test_filtro_moeda():
    assert moeda(Decimal("6.9")) == "R$ 6,90"
    assert moeda(Decimal("1234.5")) == "R$ 1.234,50"
    assert moeda(Decimal("0")) == "R$ 0,00"
    assert moeda(None) == "—"


def test_filtro_quantidade():
    assert quantidade(Decimal("12.350")) == "12,35"
    assert quantidade(Decimal("5.000")) == "5"
    assert quantidade(Decimal("0.000")) == "0"
    assert quantidade(Decimal("100.000")) == "100"
