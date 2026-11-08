"""Ponto de entrada: executa o servidor de desenvolvimento.

Uso:  python run.py   ->  http://127.0.0.1:5000
"""
import os

from app import create_app
from app.extensions import db

app = create_app()

# Cria as tabelas (ainda não há modelos; na próxima etapa elas passam a existir).
os.makedirs(app.instance_path, exist_ok=True)
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
