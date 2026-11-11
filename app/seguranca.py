"""Guarda global de acesso: login obrigatório, troca de senha pendente e permissões por perfil.

Funciona como um porteiro que olha TODA requisição antes da rota (before_request). Como a regra
é "negar por padrão", uma rota nova já nasce protegida sem ninguém precisar lembrar de proteger.
"""
from urllib.parse import urlsplit

from flask import abort, g, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFError

from app.permissoes import (
    ENDPOINTS_PUBLICOS, ENDPOINTS_SO_LOGADO, PERMISSAO_DO_MODULO, perfil_pode,
)
from app.extensions import db
from app.services import usuario_service


def destino_interno(alvo):
    """Aceita só caminhos DO PRÓPRIO sistema (evita 'open redirect': /login?next=https://golpe.com)."""
    if not alvo or not alvo.startswith("/") or alvo.startswith("//") or "\\" in alvo:
        return None
    partes = urlsplit(alvo)
    if partes.scheme or partes.netloc:
        return None
    return alvo


def iniciar_sessao(usuario):
    """Nova sessão limpa (evita 'fixação de sessão') com a versão atual do usuário."""
    session.clear()
    session["usuario_id"] = usuario.id
    session["sv"] = usuario.sessao_versao
    session.permanent = True


def _usuario_da_sessao():
    """O usuário logado, ou None. Sessão velha (senha trocada, usuário desativado) é descartada."""
    if "usuario_id" not in session:
        return None  # visitante: não mexe na sessão (ela pode guardar um aviso a exibir)
    usuario = usuario_service.obter(session.get("usuario_id"))
    if usuario is None or not usuario.ativo or session.get("sv") != usuario.sessao_versao:
        session.clear()  # sessão que valia e deixou de valer
        return None
    return usuario


def _ir_para_login():
    proximo = request.full_path.rstrip("?") if request.method == "GET" else None
    return redirect(url_for("auth.login", next=proximo) if proximo else url_for("auth.login"))


def guarda():
    endpoint = request.endpoint
    if endpoint is None:  # URL inexistente: deixa o Flask responder 404
        return None

    g.usuario = None
    if endpoint == "static":
        return None

    g.usuario = _usuario_da_sessao()
    if g.usuario is None:
        if endpoint in ENDPOINTS_PUBLICOS:
            # Sistema recém-instalado (sem nenhum usuário): leva ao cadastro do dono.
            if endpoint == "auth.login" and usuario_service.contar() == 0:
                return redirect(url_for("auth.primeiro_acesso"))
            return None
        if usuario_service.contar() == 0:
            return redirect(url_for("auth.primeiro_acesso"))
        return _ir_para_login()

    if g.usuario.trocar_senha and endpoint not in {"auth.trocar_senha", "auth.logout"}:
        return redirect(url_for("auth.trocar_senha"))  # RN63

    if endpoint in ENDPOINTS_SO_LOGADO or endpoint in ENDPOINTS_PUBLICOS:
        return None

    permissao = PERMISSAO_DO_MODULO.get(request.blueprint)
    if permissao is None or not perfil_pode(g.usuario.perfil, permissao):
        abort(403)  # módulo desconhecido também é negado
    return None


CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "font-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


def cabecalhos_de_seguranca(resposta):
    """Páginas do sistema não ficam em cache (o botão "voltar" não reabre tela após o logout)."""
    if request.endpoint != "static":
        resposta.headers["Cache-Control"] = "no-store"
        resposta.headers["Pragma"] = "no-cache"
    resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
    resposta.headers.setdefault("X-Frame-Options", "DENY")  # ninguém coloca o sistema dentro de um iframe
    resposta.headers.setdefault("Referrer-Policy", "same-origin")
    # CSP: o navegador só executa JavaScript e carrega recursos do próprio sistema. Se alguém conseguir
    # injetar um <script> numa tela (XSS), ele é bloqueado. 'unsafe-inline' só em estilos (style="...").
    resposta.headers.setdefault("Content-Security-Policy", CSP)
    return resposta


def contexto_dos_templates():
    usuario = getattr(g, "usuario", None)
    return {
        "usuario_atual": usuario,
        "pode": lambda permissao: bool(usuario and perfil_pode(usuario.perfil, permissao)),
    }


def pagina_403(_erro):
    return render_template("erros/403.html"), 403


def _pagina_de_erro(status, titulo, mensagem):
    return render_template("erros/erro.html", status=status, titulo=titulo, mensagem=mensagem), status


def pagina_400_csrf(_erro):
    """Token de segurança do formulário ausente/vencido (ex.: a tela ficou aberta além do tempo da sessão)."""
    return _pagina_de_erro(400, "A página expirou",
                           "Por segurança, o formulário só vale por um tempo. Volte, recarregue a página e tente de novo.")


def pagina_404(_erro):
    return _pagina_de_erro(404, "Página não encontrada", "O endereço não existe ou foi digitado errado.")


def pagina_500(_erro):
    db.session.rollback()  # não deixa uma transação quebrada pendurada
    return _pagina_de_erro(500, "Algo deu errado",
                           "O sistema encontrou um problema inesperado. Nada foi perdido do que já estava salvo. "
                           "Tente de novo; se persistir, avise quem cuida do sistema.")


def registrar(app):
    app.before_request(guarda)
    app.after_request(cabecalhos_de_seguranca)
    app.context_processor(contexto_dos_templates)
    app.register_error_handler(403, pagina_403)
    app.register_error_handler(CSRFError, pagina_400_csrf)
    app.register_error_handler(404, pagina_404)
    app.register_error_handler(500, pagina_500)
