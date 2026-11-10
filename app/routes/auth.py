"""Rotas de acesso: login, logout, primeiro acesso e troca da própria senha."""
from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from app.seguranca import destino_interno, iniciar_sessao
from app.services import usuario_service
from app.utils.erros import ErroDeNegocio

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    proximo = destino_interno(request.values.get("next"))
    if g.usuario is not None:
        return redirect(proximo or url_for("main.index"))
    if request.method == "POST":
        try:
            usuario = usuario_service.autenticar(request.form.get("login"), request.form.get("senha"))
        except ErroDeNegocio as erro:
            flash(str(erro), "danger")
            return render_template("auth/login.html", login=request.form.get("login", ""), proximo=proximo), 401
        iniciar_sessao(usuario)
        return redirect(proximo or url_for("main.index"))
    return render_template("auth/login.html", login="", proximo=proximo)


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Você saiu do sistema.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/primeiro-acesso", methods=["GET", "POST"])
def primeiro_acesso():
    if usuario_service.contar() > 0:  # RN65: depois do primeiro usuário, a tela deixa de existir
        return redirect(url_for("auth.login"))
    valores = request.form if request.method == "POST" else {}
    if request.method == "POST":
        try:
            if request.form.get("senha") != request.form.get("senha2"):
                raise ErroDeNegocio("As duas senhas digitadas não são iguais.")
            usuario = usuario_service.criar_primeiro_dono(
                request.form.get("nome"), request.form.get("login"), request.form.get("senha")
            )
        except ErroDeNegocio as erro:
            flash(str(erro), "danger")
        else:
            iniciar_sessao(usuario)
            flash("Tudo pronto! Você é o dono do sistema.", "success")
            return redirect(url_for("main.index"))
    return render_template("auth/primeiro_acesso.html", valores=valores)


@auth_bp.route("/conta/senha", methods=["GET", "POST"])
def trocar_senha():
    obrigatoria = g.usuario.trocar_senha
    if request.method == "POST":
        try:
            if request.form.get("nova") != request.form.get("nova2"):
                raise ErroDeNegocio("As duas senhas novas não são iguais.")
            usuario = usuario_service.trocar_senha(
                g.usuario.id, request.form.get("atual"), request.form.get("nova")
            )
        except ErroDeNegocio as erro:
            flash(str(erro), "danger")
        else:
            iniciar_sessao(usuario)  # as outras sessões deixam de valer; esta continua
            flash("Senha alterada com sucesso.", "success")
            return redirect(url_for("main.index"))
    return render_template("auth/trocar_senha.html", obrigatoria=obrigatoria)
