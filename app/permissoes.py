"""Quem pode o quê: a ÚNICA fonte da verdade das permissões.

Cada módulo (blueprint) exige uma permissão; cada permissão pertence a alguns perfis.
Um blueprint que não esteja listado aqui é NEGADO a todos (falha fechada): esquecer de
registrar um módulo novo nunca o deixa aberto por engano.
"""

PERMISSOES = {
    "vender": {"DONO", "GERENTE", "CAIXA"},      # PDV, vendas e comprovantes
    "catalogo": {"DONO", "GERENTE"},             # produtos, categorias e estoque
    "comprar": {"DONO", "GERENTE"},              # fornecedores e compras
    "relatorios": {"DONO", "GERENTE"},           # relatórios (mostram custo e lucro)
    "financeiro": {"DONO"},                      # contas, receitas, resumo mensal
    "usuarios": {"DONO"},                        # gerir usuários
    "backup": {"DONO"},                          # fazer/baixar backup (contém TODOS os dados)
}

# Módulo (blueprint) -> permissão exigida.
PERMISSAO_DO_MODULO = {
    "pdv": "vender",
    "produtos": "catalogo",
    "categorias": "catalogo",
    "estoque": "catalogo",
    "precificacao": "catalogo",
    "fornecedores": "comprar",
    "compras": "comprar",
    "relatorios": "relatorios",
    "financeiro": "financeiro",
    "usuarios": "usuarios",
    "backup": "backup",
}

# Páginas públicas (sem login).
ENDPOINTS_PUBLICOS = {"static", "auth.login", "auth.primeiro_acesso"}
# Páginas que exigem só estar logado (qualquer perfil).
ENDPOINTS_SO_LOGADO = {"main.index", "auth.logout", "auth.trocar_senha"}


def perfil_pode(perfil, permissao):
    return perfil in PERMISSOES.get(permissao, set())
