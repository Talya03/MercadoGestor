"""Restaura o banco a partir de um backup.   Uso:  python restaurar.py instance/backups/ARQUIVO.db

IMPORTANTE: feche o sistema (Ctrl+C no terminal do run.py) antes de restaurar.
O banco atual NÃO é apagado: vira instance/mercadogestor.db.antes-da-restauracao-DATA-HORA.
"""
import sys

from app import create_app
from app.services import backup_service
from app.utils.erros import ErroDeNegocio


def main(argumentos):
    if len(argumentos) != 1:
        print(__doc__)
        return 2
    app = create_app()
    caminho_banco = app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "", 1)
    try:
        seguranca = backup_service.restaurar(argumentos[0], caminho_banco)
    except ErroDeNegocio as erro:
        print(f"Não foi possível restaurar: {erro}")
        return 1
    if seguranca:
        print(f"Banco anterior guardado em: {seguranca}")
    print("Backup restaurado. Inicie o sistema novamente com: python run.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
