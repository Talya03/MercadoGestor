"""Testes de segurança de acesso: login, sessão, guarda global e permissões por perfil."""
import os
import re
import stat

import pytest
from flask import Blueprint

from app import create_app
from app.extensions import db
from app.models import Categoria, Lancamento, Produto, Usuario
from app.permissoes import (
    ENDPOINTS_PUBLICOS, ENDPOINTS_SO_LOGADO, PERMISSAO_DO_MODULO, PERMISSOES,
)
from app.seguranca import destino_interno
from app.services import usuario_service as svc
from config import CHAVE_DEV, Config, TestConfig
from tests.conftest import SENHA_TESTE, criar_usuario, entrar


def html(r):
    return r.get_data(as_text=True)


def logar(client, login, senha=SENHA_TESTE, **extras):
    return client.post("/login", data={"login": login, "senha": senha, **extras})


# =============================================================== guarda global
def rotas_do_app(app):
    for regra in app.url_map.iter_rules():
        if regra.endpoint == "static":
            continue
        yield regra


def url_de(regra):
    """Preenche os parâmetros da regra: <int:id> vira 1 e <any(a,b):x> vira o primeiro valor."""
    caminho = re.sub(r"<any\(([^,)]+)[^>]*>", r"\1", regra.rule)
    return re.sub(r"<[^>]+>", "1", caminho)


def test_todo_endpoint_esta_classificado(app):
    """Se alguém criar um módulo novo e esquecer de classificá-lo, este teste avisa."""
    for regra in rotas_do_app(app):
        ep = regra.endpoint
        modulo = ep.split(".")[0]
        assert ep in ENDPOINTS_PUBLICOS or ep in ENDPOINTS_SO_LOGADO or modulo in PERMISSAO_DO_MODULO, (
            f"Endpoint {ep} não está classificado em app/permissoes.py"
        )
    assert set(PERMISSAO_DO_MODULO.values()) <= set(PERMISSOES)


def test_anonimo_e_barrado_em_toda_rota_do_sistema(app):
    """Inventário: TODA rota (GET ou POST) manda quem não entrou para o login."""
    criar_usuario("DONO")  # com usuários existindo, o destino é /login
    anonimo = app.test_client()
    verificadas = 0
    for regra in rotas_do_app(app):
        if regra.endpoint in ENDPOINTS_PUBLICOS:
            continue
        for metodo in sorted(regra.methods - {"HEAD", "OPTIONS"}):
            r = anonimo.open(url_de(regra), method=metodo)
            assert r.status_code == 302 and "/login" in r.headers["Location"], (
                f"{metodo} {regra.rule} ficou aberta: {r.status_code}"
            )
            verificadas += 1
    esperado = sum(len(r.methods - {"HEAD", "OPTIONS"}) for r in rotas_do_app(app) if r.endpoint not in ENDPOINTS_PUBLICOS)
    assert verificadas == esperado and verificadas > 50  # o inventário percorreu TUDO, sem pular nada


def test_anonimo_nao_ve_nada_de_dados_mesmo_com_get_direto(app):
    criar_usuario("DONO")
    categoria = Categoria(nome="Secreta")
    db.session.add(categoria)
    db.session.commit()
    anonimo = app.test_client()
    for url in ("/categorias/", "/produtos/", "/financeiro/", "/relatorios/dias", "/usuarios/", "/"):
        r = anonimo.get(url, follow_redirects=True)
        assert "Secreta" not in html(r) and "Entrar" in html(r)


def test_modulo_nao_classificado_e_negado_ate_para_o_dono(app):
    """Falha fechada: um blueprint novo, sem entrada em PERMISSAO_DO_MODULO, nunca fica aberto."""
    novo = Blueprint("modulo_novo", __name__, url_prefix="/novo")
    novo.add_url_rule("/", "pagina", lambda: "segredo")
    app.register_blueprint(novo)
    cliente = app.test_client()
    entrar(cliente, "DONO")
    r = cliente.get("/novo/")
    assert r.status_code == 403 and "segredo" not in html(r)


def test_url_inexistente_continua_404(client, client_anonimo):
    assert client.get("/nao-existe").status_code == 404
    criar_usuario("CAIXA", login="cx")
    assert client_anonimo.get("/nao-existe").status_code == 404


# ======================================================== matriz de permissões
PAGINAS = {
    "pdv": ["/pdv/", "/pdv/vendas"],
    "catalogo": ["/produtos/", "/categorias/", "/estoque/"],
    "comprar": ["/fornecedores/", "/compras/", "/compras/nova"],
    "relatorios": ["/relatorios/", "/relatorios/produtos", "/relatorios/dias?formato=csv"],
    "financeiro": ["/financeiro/", "/financeiro/resumo", "/financeiro/novo"],
    "usuarios": ["/usuarios/", "/usuarios/novo"],
    "backup": ["/backup/"],
}
PERMISSAO_DA_PAGINA = {
    "pdv": "vender", "catalogo": "catalogo", "comprar": "comprar",
    "relatorios": "relatorios", "financeiro": "financeiro", "usuarios": "usuarios", "backup": "backup",
}


@pytest.mark.parametrize("perfil", ["DONO", "GERENTE", "CAIXA"])
@pytest.mark.parametrize("grupo", list(PAGINAS))
def test_matriz_de_permissoes(cliente_como, perfil, grupo):
    cliente = cliente_como(perfil)
    esperado_liberado = perfil in PERMISSOES[PERMISSAO_DA_PAGINA[grupo]]
    for url in PAGINAS[grupo]:
        r = cliente.get(url)
        assert r.status_code == (200 if esperado_liberado else 403), f"{perfil} em {url}: {r.status_code}"


@pytest.mark.parametrize("perfil", ["DONO", "GERENTE", "CAIXA"])
def test_inicio_e_troca_de_senha_abrem_para_todos(cliente_como, perfil):
    cliente = cliente_como(perfil)
    assert cliente.get("/").status_code == 200
    assert cliente.get("/conta/senha").status_code == 200


def test_perfis_do_projeto_batem_com_a_regra_de_negocio():
    assert PERMISSOES["vender"] == {"DONO", "GERENTE", "CAIXA"}
    assert PERMISSOES["financeiro"] == {"DONO"} and PERMISSOES["usuarios"] == {"DONO"}
    assert PERMISSOES["backup"] == {"DONO"}  # o backup contém todos os dados e os hashes das senhas
    assert "CAIXA" not in PERMISSOES["catalogo"] | PERMISSOES["comprar"] | PERMISSOES["relatorios"]
    assert "GERENTE" in PERMISSOES["catalogo"] and "GERENTE" not in PERMISSOES["financeiro"]


def test_acao_negada_nao_executa(cliente_como):
    """403 não pode ter efeito colateral: a rota nem chega a ser executada."""
    caixa = cliente_como("CAIXA")
    r = caixa.post("/financeiro/novo", data={"tipo": "DESPESA", "categoria": "ALUGUEL", "descricao": "x",
                                             "valor": "10", "data": "2026-11-10"})
    assert r.status_code == 403 and db.session.query(Lancamento).count() == 0
    r = caixa.post("/produtos/novo", data={"nome": "Leite"})
    assert r.status_code == 403 and db.session.query(Produto).count() == 0


def test_caixa_nao_consegue_se_promover_nem_criar_usuarios(cliente_como):
    """Escalada de privilégio: o ataque mais importante a bloquear."""
    caixa = cliente_como("CAIXA")
    eu = db.session.query(Usuario).filter_by(login="caixa-teste").one()
    antes = db.session.query(Usuario).count()
    for url, dados in (
        ("/usuarios/novo", {"nome": "Eu", "login": "novo-dono", "perfil": "DONO", "senha": "senha-forte-12"}),
        (f"/usuarios/{eu.id}/editar", {"nome": eu.nome, "perfil": "DONO"}),
        (f"/usuarios/{eu.id}/redefinir-senha", {}),
        (f"/usuarios/{eu.id}/alternar", {}),
    ):
        assert caixa.post(url, data=dados).status_code == 403
    db.session.expire_all()
    assert db.session.query(Usuario).count() == antes and eu.perfil == "CAIXA"


def test_gerente_nao_acessa_financeiro_nem_usuarios_mas_acessa_relatorios(cliente_como):
    g = cliente_como("GERENTE")
    assert g.get("/financeiro/").status_code == 403 and g.get("/usuarios/").status_code == 403
    assert g.get("/relatorios/dias").status_code == 200


def test_pagina_403_e_amigavel_e_nao_vaza_dados(cliente_como):
    r = cliente_como("CAIXA").get("/financeiro/")
    assert r.status_code == 403 and "Acesso negado" in html(r) and "Caixa" in html(r)


def test_inicio_esconde_blocos_financeiros_de_quem_nao_pode(cliente_como):
    for perfil, ve in (("DONO", True), ("GERENTE", False), ("CAIXA", False)):
        corpo = html(cliente_como(perfil).get("/"))
        assert ("Contas vencidas" in corpo) is ve and ("Mês atual" in corpo) is ve


def test_menu_so_mostra_o_que_o_perfil_abre(cliente_como):
    esperado = {
        "CAIXA": {"PDV (caixa)", "Vendas"},
        "GERENTE": {"PDV (caixa)", "Vendas", "Categorias", "Produtos", "Estoque", "Fornecedores", "Compras", "Relatórios"},
    }
    todos = {"PDV (caixa)", "Vendas", "Categorias", "Produtos", "Estoque", "Fornecedores", "Compras",
             "Financeiro", "Resumo mensal", "Relatórios", "Usuários", "Backup"}
    for perfil, visivel in esperado.items():
        menu = re.findall(r'class="nav-link[^"]*"\s+href="[^"]+">([^<]+)</a>', html(cliente_como(perfil).get("/")))
        assert set(menu) - {"Início"} == visivel, perfil
    menu_dono = re.findall(r'class="nav-link[^"]*"\s+href="[^"]+">([^<]+)</a>', html(cliente_como("DONO").get("/")))
    assert set(menu_dono) - {"Início"} == todos


# ==================================================================== login
def test_pagina_de_login(client_anonimo, app):
    criar_usuario("DONO")
    r = client_anonimo.get("/login")
    assert r.status_code == 200 and "Entrar" in html(r) and 'type="password"' in html(r)


def test_login_correto_abre_sessao_minima(client_anonimo, app):
    u = criar_usuario("DONO", login="maria")
    r = logar(client_anonimo, "MARIA")
    assert r.status_code == 302 and r.headers["Location"].endswith("/")
    with client_anonimo.session_transaction() as s:
        assert set(s.keys()) == {"usuario_id", "sv", "_permanent"} and s["usuario_id"] == u.id  # sem senha/dados na sessão
    assert client_anonimo.get("/").status_code == 200


def test_login_errado_e_igual_para_login_inexistente_e_senha_errada(client_anonimo, app):
    criar_usuario("DONO", login="maria")
    a = logar(client_anonimo, "maria", "senha-errada-xx")
    b = logar(client_anonimo, "fantasma", "senha-errada-xx")
    c = logar(client_anonimo, "", "")
    assert a.status_code == b.status_code == c.status_code == 401
    sem_login = lambda t: re.sub(r'value="[^"]*"', 'value=""', t)  # a página devolve o login digitado
    assert sem_login(html(a)) == sem_login(html(b))  # nada revela se o login existe
    assert svc.MSG_LOGIN_FALHOU in html(a)
    assert client_anonimo.get("/").status_code == 302  # continua sem entrar


def test_login_nao_reexibe_a_senha_digitada(client_anonimo, app):
    criar_usuario("DONO", login="maria")
    corpo = html(logar(client_anonimo, "maria", "minha-senha-secreta-1"))
    assert "minha-senha-secreta-1" not in corpo and 'value="maria"' in corpo


def test_bloqueio_pela_tela(client_anonimo, app):
    criar_usuario("DONO", login="maria")
    for _ in range(5):
        logar(client_anonimo, "maria", "senha-errada-xx")
    r = logar(client_anonimo, "maria", SENHA_TESTE)  # certa, mas bloqueada
    assert r.status_code == 401 and client_anonimo.get("/").status_code == 302


def test_login_so_aceita_post_para_autenticar_e_logout_so_post(client_anonimo, client):
    assert client.get("/logout").status_code == 405
    assert client_anonimo.get("/login?login=x&senha=y").status_code in (200, 302)  # GET não autentica
    with client.session_transaction() as s:
        assert "usuario_id" in s


def test_redirecionamento_apos_login_vai_para_a_pagina_pedida(client_anonimo, app):
    criar_usuario("DONO", login="maria")
    r = client_anonimo.get("/produtos/?q=leite")
    assert r.status_code == 302 and r.headers["Location"].startswith("/login?next=")
    pagina = client_anonimo.get(r.headers["Location"])  # o destino volta intacto no formulário
    assert 'name="next" value="/produtos/?q=leite"' in html(pagina)
    r = logar(client_anonimo, "maria", next="/produtos/?q=leite")
    assert r.headers["Location"] == "/produtos/?q=leite"


@pytest.mark.parametrize("alvo", [
    "https://evil.com", "//evil.com", "/\\evil.com", "http:evil.com", "javascript:alert(1)",
    "evil.com", "", "///evil.com", "\\\\evil.com",
])
def test_next_externo_e_ignorado(client_anonimo, app, alvo):
    criar_usuario("DONO", login="maria")
    r = logar(client_anonimo, "maria", next=alvo)
    assert r.status_code == 302 and r.headers["Location"] == "/"
    assert destino_interno(alvo) is None


def test_logado_que_abre_login_vai_para_o_inicio(client):
    r = client.get("/login")
    assert r.status_code == 302 and r.headers["Location"].endswith("/")


def test_logout_encerra_a_sessao(client):
    assert client.get("/").status_code == 200
    r = client.post("/logout")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert client.get("/").status_code == 302
    assert client.get("/produtos/").status_code == 302


def test_aviso_de_logout_aparece_na_tela_de_login(client):
    """Regressão: a guarda apagava a sessão de visitantes e o aviso nunca chegava."""
    assert "Você saiu do sistema" in html(client.post("/logout", follow_redirects=True))


def test_sessao_de_usuario_inativo_cai_mesmo_sem_mudar_a_versao(app):
    """Defesa em camadas: desativar direto no banco (sem passar pelo service) também derruba."""
    u = criar_usuario("CAIXA", login="cx")
    cx = app.test_client()
    entrar_sessao(cx, u)
    assert cx.get("/pdv/").status_code == 200
    u.ativo = False
    db.session.commit()  # a versão da sessão NÃO mudou
    assert cx.get("/pdv/").status_code == 302


def entrar_sessao(cliente, usuario):
    with cliente.session_transaction() as s:
        s["usuario_id"], s["sv"] = usuario.id, usuario.sessao_versao


def test_iniciar_sessao_descarta_o_que_ja_havia_na_sessao(app):
    """O 'clear' do login, testado sozinho (a guarda não o disfarça)."""
    from flask import session
    from app.seguranca import iniciar_sessao

    u = criar_usuario("DONO", login="maria")
    with app.test_request_context("/"):
        session["lixo_do_atacante"] = "x"
        iniciar_sessao(u)
        assert "lixo_do_atacante" not in session
        assert session["usuario_id"] == u.id and session["sv"] == u.sessao_versao and session.permanent


def test_fixacao_de_sessao_login_descarta_a_sessao_anterior(client_anonimo, app):
    criar_usuario("DONO", login="maria")
    with client_anonimo.session_transaction() as s:
        s["lixo_do_atacante"] = "x"
    logar(client_anonimo, "maria")
    with client_anonimo.session_transaction() as s:
        assert "lixo_do_atacante" not in s


def test_cookie_de_sessao_e_httponly_samesite_e_expira(client_anonimo, app):
    criar_usuario("DONO", login="maria")
    cookie = logar(client_anonimo, "maria").headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie and "Expires=" in cookie
    assert app.config["PERMANENT_SESSION_LIFETIME"].total_seconds() == 12 * 3600


# ===================================================== sessões que perdem a validade
def test_usuario_desativado_e_derrubado_na_hora(app):
    dono = criar_usuario("DONO", login="chefe")
    cx = app.test_client()
    entrar(cx, "CAIXA", login="cx")
    assert cx.get("/pdv/").status_code == 200
    svc.alternar_ativo(db.session.query(Usuario).filter_by(login="cx").one().id, dono.id)
    r = cx.get("/pdv/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_trocar_senha_em_outro_lugar_derruba_esta_sessao(app):
    criar_usuario("DONO", login="maria")
    a, b = app.test_client(), app.test_client()
    logar(a, "maria"); logar(b, "maria")
    assert a.get("/").status_code == 200 and b.get("/").status_code == 200
    r = a.post("/conta/senha", data={"atual": SENHA_TESTE, "nova": "outra-senha-forte-9", "nova2": "outra-senha-forte-9"})
    assert r.status_code == 302
    assert a.get("/").status_code == 200  # quem trocou continua logado
    assert b.get("/").status_code == 302  # a outra sessão caiu


def test_mudar_perfil_derruba_a_sessao_do_usuario(app):
    dono = criar_usuario("DONO", login="chefe")
    g = app.test_client()
    entrar(g, "GERENTE", login="ger")
    ger = db.session.query(Usuario).filter_by(login="ger").one()
    svc.editar(ger.id, ger.nome, "CAIXA", dono.id)
    assert g.get("/produtos/").status_code == 302  # precisa entrar de novo, já com o perfil novo


def test_usuario_removido_do_banco_nao_mantem_sessao(app):
    cx = app.test_client()
    u = entrar(cx, "CAIXA", login="cx")
    db.session.delete(u)
    db.session.commit()
    criar_usuario("DONO", login="chefe")
    assert cx.get("/pdv/").status_code == 302


def test_sessao_forjada_com_versao_errada_e_recusada(app):
    u = criar_usuario("DONO", login="maria")
    cliente = app.test_client()
    with cliente.session_transaction() as s:
        s["usuario_id"], s["sv"] = u.id, 999
    assert cliente.get("/").status_code == 302
    with cliente.session_transaction() as s:
        assert "usuario_id" not in s  # sessão inválida é limpa


# ======================================================== senha temporária obrigatória
def test_senha_temporaria_obriga_a_trocar_antes_de_qualquer_coisa(app):
    criar_usuario("CAIXA", login="cx", trocar_senha=True)
    cx = app.test_client()
    logar(cx, "cx")
    for url in ("/", "/pdv/", "/produtos/", "/pdv/vendas"):
        r = cx.get(url)
        assert r.status_code == 302 and r.headers["Location"].endswith("/conta/senha"), url
    assert cx.get("/conta/senha").status_code == 200
    assert cx.post("/pdv/cancelar").status_code == 302  # nem ação de POST passa
    assert cx.post("/logout").status_code == 302  # sair é sempre possível


def test_depois_da_troca_o_acesso_e_liberado(app):
    criar_usuario("CAIXA", login="cx", trocar_senha=True)
    cx = app.test_client()
    logar(cx, "cx")
    r = cx.post("/conta/senha", data={"atual": SENHA_TESTE, "nova": "senha-so-minha-55", "nova2": "senha-so-minha-55"})
    assert r.status_code == 302
    assert cx.get("/pdv/").status_code == 200


def test_trocar_senha_erros_pela_tela(client):
    r = client.post("/conta/senha", data={"atual": SENHA_TESTE, "nova": "senha-so-minha-55", "nova2": "diferente"})
    assert "não são iguais" in html(r)
    r = client.post("/conta/senha", data={"atual": "errada-errada", "nova": "senha-so-minha-55", "nova2": "senha-so-minha-55"})
    assert "atual está incorreta" in html(r)
    r = client.post("/conta/senha", data={"atual": SENHA_TESTE, "nova": "123", "nova2": "123"})
    assert "pelo menos 8" in html(r)


# ====================================================================== primeiro acesso
def test_sistema_novo_leva_ao_primeiro_acesso(client_anonimo, app):
    for url in ("/", "/pdv/", "/login", "/produtos/"):
        r = client_anonimo.get(url)
        assert r.status_code == 302 and r.headers["Location"].endswith("/primeiro-acesso"), url
    assert "Bem-vindo" in html(client_anonimo.get("/primeiro-acesso"))


def test_primeiro_acesso_cria_dono_e_ja_entra(client_anonimo, app):
    r = client_anonimo.post("/primeiro-acesso", data={"nome": "Maria", "login": "Maria", "senha": SENHA_TESTE, "senha2": SENHA_TESTE})
    assert r.status_code == 302
    dono = db.session.query(Usuario).one()
    assert (dono.perfil, dono.login, dono.trocar_senha) == ("DONO", "maria", False)
    assert client_anonimo.get("/usuarios/").status_code == 200


def test_primeiro_acesso_erros(client_anonimo, app):
    base = {"nome": "Maria", "login": "maria", "senha": SENHA_TESTE, "senha2": SENHA_TESTE}
    assert "não são iguais" in html(client_anonimo.post("/primeiro-acesso", data={**base, "senha2": "x"}))
    assert "pelo menos 8" in html(client_anonimo.post("/primeiro-acesso", data={**base, "senha": "123", "senha2": "123"}))
    assert "login" in html(client_anonimo.post("/primeiro-acesso", data={**base, "login": "a"}))
    assert db.session.query(Usuario).count() == 0


def test_primeiro_acesso_nao_serve_para_invadir_depois(client_anonimo, app):
    """Com o sistema já em uso, a tela some e um POST direto NÃO cria dono."""
    criar_usuario("DONO", login="maria")
    for metodo in ("get", "post"):
        r = getattr(client_anonimo, metodo)("/primeiro-acesso", data={"nome": "Invasor", "login": "invasor",
                                                                      "senha": SENHA_TESTE, "senha2": SENHA_TESTE})
        assert r.status_code == 302 and r.headers["Location"].endswith("/login")
    assert db.session.query(Usuario).count() == 1


# ====================================================================== cabeçalhos
def test_paginas_nao_ficam_em_cache_e_tem_cabecalhos_de_seguranca(client):
    r = client.get("/")
    assert r.headers["Cache-Control"] == "no-store"
    assert r.headers["X-Frame-Options"] == "DENY" and r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Referrer-Policy"] == "same-origin"


def test_erro_403_e_login_tambem_levam_os_cabecalhos(cliente_como, client_anonimo, app):
    assert cliente_como("CAIXA").get("/financeiro/").headers["X-Frame-Options"] == "DENY"
    criar_usuario("DONO", login="maria")
    assert client_anonimo.get("/login").headers["Cache-Control"] == "no-store"


def test_arquivos_estaticos_podem_ser_baixados_sem_login_e_com_cache(client_anonimo, app):
    criar_usuario("DONO")
    r = client_anonimo.get("/static/css/style.css")
    assert r.status_code == 200 and r.headers.get("Cache-Control") != "no-store"


# ============================================================================ CSRF
@pytest.fixture
def app_csrf():
    class Cfg(TestConfig):
        WTF_CSRF_ENABLED = True

    aplicacao = create_app(Cfg)
    with aplicacao.app_context():
        db.create_all()
        yield aplicacao
        db.session.remove()
        db.drop_all()


def test_login_e_logout_exigem_token_csrf(app_csrf):
    criar_usuario("DONO", login="maria")
    c = app_csrf.test_client()
    assert c.post("/login", data={"login": "maria", "senha": SENHA_TESTE}).status_code == 400
    token = re.search(r'name="csrf_token" value="([^"]+)"', html(c.get("/login"))).group(1)
    assert c.post("/login", data={"login": "maria", "senha": SENHA_TESTE, "csrf_token": token}).status_code == 302
    assert c.post("/logout").status_code == 400  # sem token, ninguém desloga o usuário "de fora"
    assert c.get("/").status_code == 200


def test_primeiro_acesso_exige_csrf(app_csrf):
    c = app_csrf.test_client()
    r = c.post("/primeiro-acesso", data={"nome": "M", "login": "maria", "senha": SENHA_TESTE, "senha2": SENHA_TESTE})
    assert r.status_code == 400 and db.session.query(Usuario).count() == 0


# ============================================================== chave secreta da sessão
class _ConfigReal(Config):
    """Como em uso real (não é teste): SECRET_KEY de desenvolvimento, banco em memória."""
    SECRET_KEY = CHAVE_DEV
    TESTING = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    PASSWORD_HASH_METHOD = "pbkdf2:sha256:1000"


def test_gera_chave_aleatoria_persistente_quando_usa_a_de_desenvolvimento(tmp_path):
    a = create_app(_ConfigReal, instance_path=str(tmp_path))
    chave = a.config["SECRET_KEY"]
    assert chave != CHAVE_DEV and re.fullmatch(r"[0-9a-f]{64}", chave)
    arquivo = tmp_path / "secret_key"
    assert arquivo.read_text() == chave
    if os.name == "posix":
        assert stat.S_IMODE(arquivo.stat().st_mode) == 0o600  # só o dono do arquivo lê
    assert create_app(_ConfigReal, instance_path=str(tmp_path)).config["SECRET_KEY"] == chave  # reinício mantém


def test_chave_curta_ou_vazia_no_arquivo_e_regenerada(tmp_path):
    (tmp_path / "secret_key").write_text("curta")
    assert len(create_app(_ConfigReal, instance_path=str(tmp_path)).config["SECRET_KEY"]) == 64


def test_chave_definida_pelo_ambiente_e_respeitada_e_testes_nao_criam_arquivo(tmp_path):
    class Propria(_ConfigReal):
        SECRET_KEY = "x" * 40

    assert create_app(Propria, instance_path=str(tmp_path)).config["SECRET_KEY"] == "x" * 40
    assert not (tmp_path / "secret_key").exists()
    create_app(TestConfig, instance_path=str(tmp_path))
    assert not (tmp_path / "secret_key").exists()
