"""Datas e fuso horário.

Conceito: o banco guarda todos os horários em UTC (padrão universal, sem
confusão de fuso/horário de verão). Na tela, convertemos para o horário do
mercado. Ao filtrar por dia, "1º de novembro" significa 1º de novembro NO
HORÁRIO DO MERCADO, então convertemos o intervalo para UTC antes de consultar.

Observação: no Windows o Python precisa do pacote `tzdata` (está no requirements.txt).
"""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

FUSO_LOCAL = ZoneInfo("America/Sao_Paulo")


def para_local(momento):
    """Converte um datetime (UTC; naive é tratado como UTC) para o horário local."""
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(FUSO_LOCAL)


def _meia_noite_local_em_utc(dia):
    local = datetime.combine(dia, time.min, tzinfo=FUSO_LOCAL)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def intervalo_utc(data_inicio=None, data_fim=None):
    """Datas locais (inclusivas) -> (inicio, fim_exclusivo) em UTC naive.

    Uso: data_hora >= inicio  E  data_hora < fim_exclusivo.
    Qualquer ponta pode ser None (sem limite naquele lado).
    """
    inicio = _meia_noite_local_em_utc(data_inicio) if data_inicio else None
    fim = _meia_noite_local_em_utc(data_fim + timedelta(days=1)) if data_fim else None
    return inicio, fim
