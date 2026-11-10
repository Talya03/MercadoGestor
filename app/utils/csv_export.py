"""Exportação CSV pensada para abrir direto no Excel/LibreOffice em português.

Decisões:
- separador ";" e números com vírgula decimal (padrão brasileiro);
- BOM UTF-8 no início, para o Excel acertar os acentos;
- PROTEÇÃO CONTRA "CSV INJECTION": um texto que começa com = + - @ (ou tab/enter) pode ser
  executado como FÓRMULA pelo Excel (ex.: um produto chamado "=HYPERLINK(...)"). Em colunas de
  texto, esses casos recebem um apóstrofo na frente. Colunas numéricas são formatadas por nós.
"""
import csv
import io
from datetime import date
from decimal import Decimal

from flask import Response

from app.utils.numeros import formatar_decimal_br

_PERIGOSOS = ("=", "+", "-", "@", "\t", "\r")


def _texto_seguro(valor):
    texto = "" if valor is None else str(valor)
    return "'" + texto if texto.startswith(_PERIGOSOS) else texto


def _formatar(valor, tipo):
    if tipo == "texto":
        return _texto_seguro(valor)
    if valor is None:
        return ""
    if tipo == "moeda":
        return formatar_decimal_br(Decimal(valor), 2)
    if tipo == "qtd":
        return formatar_decimal_br(Decimal(valor), 3, aparar_zeros=True)
    if tipo == "pct":
        return formatar_decimal_br(Decimal(valor), 1)
    if tipo == "inteiro":
        return str(int(valor))
    if tipo == "data":
        return valor.strftime("%d/%m/%Y") if isinstance(valor, date) else str(valor)
    raise ValueError(f"Tipo de coluna desconhecido: {tipo}")


def gerar_csv(colunas, linhas):
    """colunas: [(titulo, tipo)]; linhas: listas de valores BRUTOS (Decimal, date, str...)."""
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    escritor.writerow([_texto_seguro(titulo) for titulo, _ in colunas])
    for linha in linhas:
        escritor.writerow([_formatar(v, tipo) for v, (_, tipo) in zip(linha, colunas)])
    return "﻿" + saida.getvalue()


def resposta_csv(nome_arquivo, colunas, linhas):
    return Response(
        gerar_csv(colunas, linhas),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )
