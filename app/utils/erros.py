"""Erros do sistema."""


class ErroDeNegocio(Exception):
    """Uma regra de negócio foi violada (ex.: nome de categoria repetido).

    A mensagem é escrita para o usuário final, então é seguro exibi-la na tela.
    Erros inesperados (bugs) NÃO usam esta classe.
    """
