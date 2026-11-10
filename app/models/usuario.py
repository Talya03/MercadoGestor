"""Modelo Usuario: quem usa o sistema (dono, gerente ou caixa).

Segurança: a senha NUNCA é guardada, só o hash (resultado de uma conta de mão única, lenta de
propósito). Quem vê o banco não descobre a senha; o sistema só sabe conferir se a digitada
gera o mesmo hash.
"""
from datetime import datetime, timezone

from app.extensions import db

PERFIS = {"DONO": "Dono", "GERENTE": "Gerente", "CAIXA": "Caixa"}


def _agora():
    return datetime.now(timezone.utc)


class Usuario(db.Model):
    __tablename__ = "usuario"

    __table_args__ = (
        db.CheckConstraint("perfil IN ('DONO', 'GERENTE', 'CAIXA')", name="ck_usuario_perfil"),
        db.CheckConstraint("tentativas_falhas >= 0", name="ck_usuario_tentativas"),
        # AUTOINCREMENT: um id já usado nunca é reaproveitado. Sem isso, uma sessão antiga poderia
        # passar a valer para OUTRA pessoa criada depois com o mesmo número.
        {"sqlite_autoincrement": True},
    )

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False)
    # Sempre minúsculo (a validação garante): o UNIQUE vale sem diferenciar maiúsculas.
    login = db.Column(db.String(30), nullable=False, unique=True)
    senha_hash = db.Column(db.String(255), nullable=False)
    perfil = db.Column(db.String(10), nullable=False)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    # True = a pessoa precisa trocar a senha (temporária) antes de usar o sistema.
    trocar_senha = db.Column(db.Boolean, nullable=False, default=False)
    # Proteção contra adivinhação de senha: após N erros seguidos, bloqueia por alguns minutos.
    tentativas_falhas = db.Column(db.Integer, nullable=False, default=0)
    bloqueado_ate = db.Column(db.DateTime)  # UTC; None = sem bloqueio
    # Sobe quando a senha muda, o usuário é desativado ou é redefinido: derruba sessões antigas.
    sessao_versao = db.Column(db.Integer, nullable=False, default=1)
    ultimo_acesso = db.Column(db.DateTime)
    criado_em = db.Column(db.DateTime, nullable=False, default=_agora)

    @property
    def perfil_nome(self):
        return PERFIS.get(self.perfil, self.perfil)

    def __repr__(self):
        return f"<Usuario {self.id} {self.login!r} {self.perfil}>"
