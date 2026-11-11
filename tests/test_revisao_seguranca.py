"""Fase 9 — revisão final de segurança: verificações que valem para o sistema INTEIRO.

Em vez de testar uma tela por vez, estes testes varrem todas as rotas e todos os templates, para que
uma tela nova que esqueça uma proteção quebre o teste.
"""
import re
import subprocess
from pathlib import Path

import pytest

from app import create_app
from app.extensions import db
from app.permissoes import ENDPOINTS_PUBLICOS, ENDPOINTS_SO_LOGADO
from config import TestConfig
from tests.conftest import entrar

RAIZ = Path(__file__).resolve().parent.parent
TEMPLATES = sorted((RAIZ / "app" / "templates").rglob("*.html"))
STATIC_JS = sorted((RAIZ / "app" / "static" / "js").glob("*.js"))


class _ComCsrf(TestConfig):
    WTF_CSRF_ENABLED = True


@pytest.fixture
def app_csrf():
    app = create_app(_ComCsrf)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _rotas_post(app):
    return [r for r in app.url_map.iter_rules() if "POST" in r.methods and r.endpoint != "static"]


def _url(regra):
    url = re.sub(r"<any\(([^,)]+)[^)]*\):[^>]+>", r"\1", regra.rule)  # /estoque/<any(entrada,...):operacao>
    return re.sub(r"<(?:int:)?[^>]+>", "1", url)


# ------------------------------------------------------------------ CSRF
def test_toda_rota_post_rejeita_requisicao_sem_token_csrf(app_csrf):
    """Um site malicioso não consegue fazer o navegador do dono enviar um POST sem o token."""
    cliente = app_csrf.test_client()
    entrar(cliente, "DONO")
    rotas = _rotas_post(app_csrf)
    assert len(rotas) > 25  # a varredura enxerga as rotas de verdade
    for regra in rotas:
        r = cliente.post(_url(regra), data={})
        assert r.status_code == 400, f"{regra.rule} aceitou POST sem token CSRF ({r.status_code})"


def test_post_sem_csrf_mostra_pagina_amigavel_e_nao_vaza_detalhes(app_csrf):
    cliente = app_csrf.test_client()
    entrar(cliente, "DONO")
    r = cliente.post("/backup/criar", data={})
    corpo = r.get_data(as_text=True)
    assert r.status_code == 400 and "A página expirou" in corpo
    assert "Traceback" not in corpo and "CSRF" not in corpo


def test_nenhuma_rota_que_altera_dados_aceita_get():
    """Alterar dados por GET permitiria um <img src=...> alterar o sistema."""
    app = create_app(TestConfig)
    perigosas = ("criar", "aplicar", "pagar", "cancelar", "alternar", "desfazer", "finalizar", "adicionar",
                 "remover", "redefinir", "logout")
    for regra in app.url_map.iter_rules():
        ultimo = regra.endpoint.rsplit(".", 1)[-1]
        if any(ultimo.startswith(p) for p in perigosas):
            assert "GET" not in regra.methods, f"{regra.rule} altera dados e aceita GET"


# ------------------------------------------------------------ guarda global
def test_toda_rota_exige_login_exceto_as_publicas(app_csrf):
    anonimo = app_csrf.test_client()
    for regra in app_csrf.url_map.iter_rules():
        if regra.endpoint in ENDPOINTS_PUBLICOS:
            continue
        metodo = "GET" if "GET" in regra.methods else "POST"
        r = getattr(anonimo, metodo.lower())(_url(regra))
        assert r.status_code in (302, 400), f"{regra.rule} respondeu {r.status_code} a um visitante sem login"
        if r.status_code == 302:
            assert "/login" in r.headers["Location"] or "/primeiro-acesso" in r.headers["Location"]


# ------------------------------------------------------- cabeçalhos e CSP
def test_todas_as_paginas_mandam_cabecalhos_de_seguranca(client):
    for url in ("/", "/produtos/", "/pdv/", "/backup/", "/precificacao/", "/nao-existe"):
        h = client.get(url).headers
        assert "script-src 'self'" in h["Content-Security-Policy"] and "frame-ancestors 'none'" in h["Content-Security-Policy"]
        assert h["X-Frame-Options"] == "DENY" and h["X-Content-Type-Options"] == "nosniff"
        assert "no-store" in h["Cache-Control"]


def test_login_tambem_tem_csp(client_anonimo):
    assert "script-src 'self'" in client_anonimo.get("/login").headers["Content-Security-Policy"]


@pytest.mark.parametrize("arquivo", TEMPLATES, ids=lambda p: str(p.relative_to(RAIZ)))
def test_template_nao_tem_javascript_inline_nem_recurso_externo(arquivo):
    """A CSP bloqueia JS dentro do HTML e recursos de fora: um template assim ficaria quebrado."""
    texto = arquivo.read_text(encoding="utf-8")
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", texto), "script inline"
    assert not re.search(r"\son[a-z]+\s*=\s*[\"']", texto, re.I), "manipulador on...= inline"
    assert "javascript:" not in texto.lower()
    assert not re.search(r"""(?:src|href)\s*=\s*["']https?://""", texto), "recurso externo (CDN)"
    assert "|safe" not in texto and "Markup(" not in texto, "saída sem escape (risco de XSS)"


def test_bootstrap_local_existe_e_e_o_oficial():
    import hashlib, base64
    base = RAIZ / "app" / "static" / "vendor" / "bootstrap"
    oficiais = {
        "bootstrap.min.css": "QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH",
        "bootstrap.bundle.min.js": "YvpcrYf0tY3lHB60NNkmXc5s9fDVZLESaAA55NDzOxhy9GkcIdslK1eN7N6jIeHz",
    }
    for nome, esperado in oficiais.items():
        assert base.joinpath(nome).exists()
        assert base64.b64encode(hashlib.sha384(base.joinpath(nome).read_bytes()).digest()).decode() == esperado


# ----------------------------------------------------------------- erros
def test_erro_inesperado_mostra_pagina_generica_sem_detalhes_tecnicos():
    class _Producao(TestConfig):
        PROPAGATE_EXCEPTIONS = False
        TESTING = False
        SECRET_KEY = "k" * 40
    app = create_app(_Producao)

    @app.route("/boom")
    def boom():
        raise RuntimeError("SEGREDO-INTERNO caminho C:/Users/x")

    ENDPOINTS_SO_LOGADO.add("boom")  # a guarda nega por padrão; liberamos só esta rota de teste
    try:
        _verificar_500(app)
    finally:
        ENDPOINTS_SO_LOGADO.discard("boom")


def _verificar_500(app):
    with app.app_context():
        db.create_all()
        c = app.test_client()
        entrar(c, "DONO")
        r = c.get("/boom")
        corpo = r.get_data(as_text=True)
        assert r.status_code == 500 and "Algo deu errado" in corpo
        assert "SEGREDO-INTERNO" not in corpo and "Traceback" not in corpo and "RuntimeError" not in corpo
        db.session.remove()
        db.drop_all()


def test_run_py_nao_liga_o_depurador_por_padrao():
    texto = (RAIZ / "run.py").read_text(encoding="utf-8")
    assert not re.search(r"app\.run\([^)]*debug\s*=\s*True", texto)  # só liga se a variável pedir
    assert "MERCADOGESTOR_DEBUG" in texto


# ------------------------------------------------------------------ segredos
def test_gitignore_protege_banco_backups_e_chave():
    linhas = {l.strip() for l in (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()}
    assert "instance/" in linhas  # cobre banco, backups/, secret_key e .antes-da-migracao-*
    assert ".env" in linhas
