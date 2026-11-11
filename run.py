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
    app.run(host="127.0.0.1", port=5000, debug=True)
