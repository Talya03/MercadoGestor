def test_pagina_inicial_responde(client):
    resposta = client.get("/")
    assert resposta.status_code == 200
    assert "MercadoGestor" in resposta.get_data(as_text=True)


def test_app_usa_banco_em_memoria_nos_testes(app):
    assert app.config["TESTING"] is True
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite:///:memory:"


def test_rota_inexistente_retorna_404(client):
    assert client.get("/nao-existe").status_code == 404
