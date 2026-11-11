"""Backup e restauração do banco SQLite.

Regras:
- RN72 Backup usa a API de backup do SQLite: gera uma cópia CONSISTENTE mesmo com o sistema em uso
  (copiar o arquivo "na mão" durante uma gravação pode produzir uma cópia corrompida).
- RN73 O backup só vale se passar na verificação de integridade; senão é descartado e o erro é mostrado.
- RN74 Só ficam os N backups mais recentes (BACKUP_MANTER); os mais antigos são apagados.
- RN75 O nome do arquivo para baixar é validado contra um padrão fixo (nunca um caminho enviado pelo usuário).
- RN76 Restaurar SEMPRE guarda antes uma cópia do banco atual (restaurar.py).
O backup contém TUDO, inclusive os hashes das senhas: guarde-o como guarda o próprio banco.
"""
import os
import re
import shutil
import sqlite3
from datetime import datetime

from flask import current_app

from app.extensions import db
from app.utils.erros import ErroDeNegocio

PADRAO_NOME = re.compile(r"^mercadogestor-(\d{8})-(\d{6})(?:-(\d+))?\.db$")
TABELAS_ESPERADAS = {"usuario", "produto", "venda", "compra", "lancamento", "movimentacao_estoque"}


def _caminho_do_banco():
    url = db.engine.url
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise ErroDeNegocio("O backup automático só funciona com o banco SQLite em arquivo.")
    return url.database


def pasta_de_backups():
    pasta = current_app.config.get("BACKUP_DIR") or os.path.join(current_app.instance_path, "backups")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def verificar(caminho):
    """Abre o arquivo SOMENTE para leitura e confere integridade e se parece um banco do MercadoGestor."""
    try:
        con = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
    except sqlite3.Error as erro:
        raise ErroDeNegocio("Não foi possível abrir o arquivo de backup.") from erro
    try:
        try:
            resultado = con.execute("PRAGMA integrity_check").fetchall()
            tabelas = {linha[0] for linha in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        except sqlite3.DatabaseError as erro:
            raise ErroDeNegocio("O arquivo não é um banco válido ou está corrompido.") from erro
        if resultado != [("ok",)]:
            raise ErroDeNegocio("O banco falhou na verificação de integridade.")
        if not TABELAS_ESPERADAS <= tabelas:
            raise ErroDeNegocio("O arquivo não parece ser um banco do MercadoGestor.")
    finally:
        con.close()


def _nome_novo(pasta):
    base = f"mercadogestor-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    nome, i = f"{base}.db", 1
    while os.path.exists(os.path.join(pasta, nome)):  # dois backups no mesmo segundo
        i += 1
        nome = f"{base}-{i}.db"
    return nome


def criar_backup():
    """Gera um backup consistente e verificado. Devolve o nome do arquivo."""
    origem_caminho = _caminho_do_banco()
    db.session.commit()  # não deixa transação aberta nossa segurando o banco
    pasta = pasta_de_backups()
    nome = _nome_novo(pasta)
    final = os.path.join(pasta, nome)
    temporario = final + ".tmp"
    origem = sqlite3.connect(origem_caminho)
    destino = sqlite3.connect(temporario)
    try:
        origem.backup(destino)
    finally:
        destino.close()
        origem.close()
    try:
        verificar(temporario)
    except ErroDeNegocio:
        os.remove(temporario)
        raise ErroDeNegocio("O backup foi descartado porque não passou na verificação. Tente de novo.")
    os.chmod(temporario, 0o600)
    os.replace(temporario, final)
    _aplicar_retencao(pasta)
    return nome


def _aplicar_retencao(pasta):
    manter = int(current_app.config.get("BACKUP_MANTER", 14))
    nomes = sorted(_nomes_validos(pasta), reverse=True)  # nome tem data: mais novo primeiro
    for antigo in nomes[manter:]:
        os.remove(os.path.join(pasta, antigo))


def _chave(nome):
    m = PADRAO_NOME.match(nome)
    return (m.group(1), m.group(2), int(m.group(3) or 1))


def _nomes_validos(pasta):
    return sorted((n for n in os.listdir(pasta) if PADRAO_NOME.match(n)), key=_chave)


def listar():
    """Backups existentes, do mais novo para o mais antigo."""
    pasta = pasta_de_backups()
    itens = []
    for nome in sorted(_nomes_validos(pasta), key=_chave, reverse=True):
        m = PADRAO_NOME.match(nome)
        quando = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        itens.append({"nome": nome, "quando": quando, "tamanho": os.path.getsize(os.path.join(pasta, nome))})
    return itens


def caminho_do_backup(nome):
    """Valida o nome (RN75) e devolve o caminho. Qualquer coisa fora do padrão é recusada."""
    if not isinstance(nome, str) or not PADRAO_NOME.match(nome):
        raise ErroDeNegocio("Backup não encontrado.")
    caminho = os.path.join(pasta_de_backups(), nome)
    if not os.path.isfile(caminho):
        raise ErroDeNegocio("Backup não encontrado.")
    return caminho


def restaurar(arquivo_backup, arquivo_banco):
    """Substitui o banco por um backup (use com o sistema FECHADO). Devolve o caminho da cópia de segurança
    do banco que estava em uso (ou None se ele ainda não existia). Ver restaurar.py."""
    if not os.path.isfile(arquivo_backup):
        raise ErroDeNegocio("Arquivo de backup não encontrado.")
    verificar(arquivo_backup)
    seguranca = None
    if os.path.exists(arquivo_banco):
        seguranca = f"{arquivo_banco}.antes-da-restauracao-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(arquivo_banco, seguranca)
    temporario = arquivo_banco + ".restaurando"
    origem = sqlite3.connect(f"file:{arquivo_backup}?mode=ro", uri=True)
    destino = sqlite3.connect(temporario)
    try:
        origem.backup(destino)
    finally:
        destino.close()
        origem.close()
    verificar(temporario)
    os.replace(temporario, arquivo_banco)
    return seguranca
