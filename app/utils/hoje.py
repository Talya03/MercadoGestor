"""Data de hoje no horário do mercado (e não em UTC: às 22h em São Paulo já é "amanhã" em UTC)."""
from datetime import date, datetime, timezone

from app.utils.datas import para_local


def hoje_local() -> date:
    return para_local(datetime.now(timezone.utc)).date()
