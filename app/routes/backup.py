"""Backup do banco (somente DONO; a guarda global já garante isso)."""
from flask import Blueprint, flash, redirect, render_template, send_file, url_for

from app.services import backup_service
from app.utils.erros import ErroDeNegocio

backup_bp = Blueprint("backup", __name__, url_prefix="/backup")


@backup_bp.route("/")
def lista():
    return render_template("backup/lista.html", backups=backup_service.listar())


@backup_bp.route("/criar", methods=["POST"])
def criar():
    try:
        nome = backup_service.criar_backup()
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
    else:
        flash(f"Backup criado: {nome}", "success")
    return redirect(url_for("backup.lista"))


@backup_bp.route("/baixar/<nome>")
def baixar(nome):
    try:
        caminho = backup_service.caminho_do_backup(nome)  # RN75: nome validado
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
        return redirect(url_for("backup.lista"))
    return send_file(caminho, as_attachment=True, download_name=nome, mimetype="application/octet-stream")
