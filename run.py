"""Ponto de entrada: executa o servidor de desenvolvimento.

Uso:  python run.py   ->  http://127.0.0.1:5000
"""
import os

from app import create_app, migracoes
from app.extensions import db

app = create_app()

# Cria as tabelas que faltam e atualiza as existentes (com cópia de segurança do banco).
os.makedirs(app.instance_path, exist_ok=True)
with app.app_context():
    db.create_all()
    migracoes.aplicar()

if __name__ == "__main__":
    # debug=True liga o depurador interativo do Werkzeug, que PERMITE EXECUTAR CÓDIGO no computador
    # a quem abrir a página de erro. Por isso vem DESLIGADO. Para desenvolver (recarga automática ao salvar):
    #   Windows (Git Bash):  MERCADOGESTOR_DEBUG=1 python run.py
    # O sistema escuta só em 127.0.0.1 (este computador); não o exponha à rede.
    app.run(host="127.0.0.1", port=5000, debug=os.environ.get("MERCADOGESTOR_DEBUG") == "1")
