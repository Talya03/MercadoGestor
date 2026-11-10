"""Gestão de usuários (somente DONO; a guarda global já garante isso)."""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from app.models import PERFIS
from app.services import usuario_service
from app.utils.erros import ErroDeNegocio

usuarios_bp = Blueprint("usuarios", __name__, url_prefix="/usuarios")


@usuarios_bp.route("/")
def lista():
    return render_template("usuarios/lista.html", usuarios=usuario_service.listar())


@usuarios_bp.route("/novo", methods=["GET", "POST"])
def novo():
    valores = request.form if request.method == "POST" else {}
    if request.method == "POST":
        # Senha em branco = o sistema gera uma temporária (mais segura que a que um humano inventa).
        senha = request.form.get("senha") or usuario_service.gerar_senha_temporaria()
        try:
            usuario = usuario_service.criar(
                request.form.get("nome"), request.form.get("login"), senha, request.form.get("perfil")
            )
        except ErroDeNegocio as erro:
            flash(str(erro), "danger")
        else:
            # Mostrada direto na resposta (sem redirecionar), para a senha não ir parar na sessão.
            return render_template("usuarios/senha_temporaria.html", usuario=usuario, senha=senha, novo=True)
    return render_template("usuarios/form.html", valores=valores, perfis=PERFIS, editando=None)


@usuarios_bp.route("/<int:usuario_id>/editar", methods=["GET", "POST"])
def editar(usuario_id):
    try:
        usuario = usuario_service.buscar(usuario_id)
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
        return redirect(url_for("usuarios.lista"))
    valores = request.form if request.method == "POST" else {"nome": usuario.nome, "perfil": usuario.perfil}
    if request.method == "POST":
        try:
            usuario_service.editar(usuario_id, request.form.get("nome"), request.form.get("perfil"), g.usuario.id)
        except ErroDeNegocio as erro:
            flash(str(erro), "danger")
        else:
            flash("Usuário atualizado.", "success")
            return redirect(url_for("usuarios.lista"))
    return render_template("usuarios/form.html", valores=valores, perfis=PERFIS, editando=usuario)


@usuarios_bp.route("/<int:usuario_id>/alternar", methods=["POST"])
def alternar(usuario_id):
    try:
        usuario = usuario_service.alternar_ativo(usuario_id, g.usuario.id)
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
    else:
        flash("Usuário ativado." if usuario.ativo else "Usuário desativado.", "success")
    return redirect(url_for("usuarios.lista"))


@usuarios_bp.route("/<int:usuario_id>/redefinir-senha", methods=["POST"])
def redefinir_senha(usuario_id):
    try:
        usuario, senha = usuario_service.redefinir_senha(usuario_id)
    except ErroDeNegocio as erro:
        flash(str(erro), "danger")
        return redirect(url_for("usuarios.lista"))
    return render_template("usuarios/senha_temporaria.html", usuario=usuario, senha=senha, novo=False)
