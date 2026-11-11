"""Regras de negócio do Controle de Estoque.

Regras (numeração continua a de docs/01-modelagem.md):
- RN04: o saldo nunca fica negativo.
- RN05: toda alteração de saldo gera uma movimentação, com motivo.
- RN06: saída maior que o saldo disponível é bloqueada.
- RN14: unidades contáveis (UN, CX, PCT) só aceitam quantidades inteiras;
        KG, G, L e ML aceitam até 3 casas decimais.
- RN15: produto inativo não pode ser movimentado.
- RN16: quantidade da entrada/saída deve ser maior que zero; no ajuste, o
        saldo contado deve ser diferente do atual.
- RN17: a movimentação e o novo saldo são gravados JUNTOS, em uma transação,
        com controle de concorrência (veja _registrar).

Exemplo de mercado: chegam 24 caixas de leite -> entrada de 24 UN, motivo
"Compra de fornecedor". Uma caixa estragou -> saída de 1 UN, "Produto vencido".
Na contagem das prateleiras só há 22 -> ajuste para 22, "Contagem de inventário".
"""
from decimal import Decimal

from sqlalchemy import desc, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import MovimentacaoEstoque, Produto, TIPOS_MOVIMENTACAO
from app.utils.datas import intervalo_utc
from app.utils.erros import ErroDeNegocio
from app.utils.formatacao import quantidade as formatar_quantidade
from app.utils.numeros import validar_decimal

CASAS_QUANTIDADE = 3
QUANTIDADE_MAXIMA = Decimal("9999999.999")
UNIDADES_FRACIONAVEIS = ("KG", "G", "L", "ML")
TAMANHO_MAX_MOTIVO = 255
LIMITE_HISTORICO = 200


# ---------------------------------------------------------------- validações
def _carregar_produto(produto_id):
    # populate_existing: garante dados frescos do banco (não uma cópia antiga em memória).
    produto = db.session.get(Produto, produto_id, populate_existing=True)
    if produto is None:
        raise ErroDeNegocio("Produto não encontrado.")
    if not produto.ativo:  # RN15
        raise ErroDeNegocio(
            f'O produto "{produto.nome}" está inativo. Reative-o para movimentar o estoque.'
        )
    return produto


def _validar_motivo(motivo):
    motivo = " ".join((motivo or "").split())
    if not motivo:
        raise ErroDeNegocio("Informe o motivo da movimentação.")
    if len(motivo) > TAMANHO_MAX_MOTIVO:
        raise ErroDeNegocio(f"O motivo pode ter no máximo {TAMANHO_MAX_MOTIVO} caracteres.")
    return motivo


def _validar_quantidade(valor, produto, rotulo, permitir_zero=False):
    numero = validar_decimal(valor, rotulo, CASAS_QUANTIDADE, QUANTIDADE_MAXIMA)
    if numero == 0 and not permitir_zero:  # RN16
        raise ErroDeNegocio(f"{rotulo} deve ser maior que zero.")
    if produto.unidade_medida not in UNIDADES_FRACIONAVEIS and numero != numero.to_integral_value():
        raise ErroDeNegocio(  # RN14
            f"Produtos em {produto.unidade_medida} só aceitam quantidades inteiras "
            "(não existe meia unidade)."
        )
    return numero


# ------------------------------------------------------------------ gravação
def _registrar(produto, tipo, quantidade, novo_saldo, motivo, confirmar=True, usuario_id=None):
    """Grava movimentação + novo saldo de forma atômica e consistente (RN05, RN17).

    confirmar=False é usado pela VENDA: a baixa de estoque entra na transação
    maior da venda (venda + itens + pagamento + baixas). Nesse caso não há
    commit aqui; quem chamou confirma tudo junto ou desfaz tudo junto.

    Dois conceitos importantes:

    1) TRANSAÇÃO: o UPDATE do saldo e o INSERT da movimentação só valem juntos
       (commit). Se algo falhar, rollback desfaz tudo: nunca fica saldo mudado
       sem histórico, nem histórico sem saldo mudado.

    2) CONCORRÊNCIA OTIMISTA: dois caixas poderiam sair do mesmo produto ao
       mesmo tempo. Ambos leriam saldo 10 e cada um gravaria "10 - 8 = 2",
       vendendo 16 de um estoque de 10 (o "lost update"). Para evitar, o
       UPDATE só vale se o saldo no banco ainda for o que lemos
       (WHERE quantidade_estoque = saldo_lido). Se outra operação mudou o saldo
       no meio do caminho, nenhuma linha é atualizada, e recusamos esta operação.
    """
    saldo_lido = produto.quantidade_estoque
    resultado = db.session.execute(
        update(Produto)
        .where(Produto.id == produto.id, Produto.quantidade_estoque == saldo_lido)
        .values(quantidade_estoque=novo_saldo),
        execution_options={"synchronize_session": False},
    )
    if resultado.rowcount != 1:
        if confirmar:
            db.session.rollback()
        raise ErroDeNegocio(
            "O estoque deste produto foi alterado por outra operação. "
            "Confira o saldo atual e tente novamente."
        )

    movimentacao = MovimentacaoEstoque(
        produto_id=produto.id,
        tipo=tipo,
        quantidade=quantidade,
        saldo_anterior=saldo_lido,
        saldo_posterior=novo_saldo,
        motivo=motivo,
        usuario_id=usuario_id,  # RN67: quem fez a movimentação
    )
    db.session.add(movimentacao)
    try:
        if confirmar:
            db.session.commit()
        else:
            db.session.flush()  # envia ao banco (e checa as restrições) sem confirmar
    except IntegrityError:
        # Rede de segurança: as restrições CHECK do banco barraram algo
        # que as validações acima deixaram passar (não deveria acontecer).
        db.session.rollback()
        raise ErroDeNegocio("Não foi possível registrar a movimentação. Nada foi alterado.")
    return movimentacao


def _checar_limite(novo_saldo):
    if novo_saldo > QUANTIDADE_MAXIMA:
        raise ErroDeNegocio("O saldo resultante passaria do limite que o sistema comporta.")


def entrada(produto_id, quantidade, motivo, confirmar=True, usuario_id=None):
    """Chegada de mercadoria: aumenta o saldo.

    confirmar=False: não faz commit (veja _registrar); usado no registro da COMPRA.
    """
    produto = _carregar_produto(produto_id)
    quantidade = _validar_quantidade(quantidade, produto, "Quantidade")
    motivo = _validar_motivo(motivo)
    novo_saldo = produto.quantidade_estoque + quantidade
    _checar_limite(novo_saldo)
    return _registrar(produto, "ENTRADA", quantidade, novo_saldo, motivo, confirmar, usuario_id)


def validar_quantidade(valor, produto, rotulo="Quantidade", permitir_zero=False):
    """Versão pública da validação de quantidade (RN14, RN16), usada também pelo PDV."""
    return _validar_quantidade(valor, produto, rotulo, permitir_zero)


def saida(produto_id, quantidade, motivo, confirmar=True, usuario_id=None):
    """Saída por perda, vencimento, consumo, venda etc.: diminui o saldo (RN04, RN06).

    confirmar=False: não faz commit (veja _registrar); usado na finalização da venda.
    """
    produto = _carregar_produto(produto_id)
    quantidade = _validar_quantidade(quantidade, produto, "Quantidade")
    motivo = _validar_motivo(motivo)
    saldo = produto.quantidade_estoque
    if quantidade > saldo:  # RN06
        raise ErroDeNegocio(
            f"Saldo insuficiente: há {formatar_quantidade(saldo)} {produto.unidade_medida} "
            f"em estoque e a saída pedida é de {formatar_quantidade(quantidade)}."
        )
    return _registrar(produto, "SAIDA", quantidade, saldo - quantidade, motivo, confirmar, usuario_id)


def ajuste(produto_id, saldo_contado, motivo, usuario_id=None):
    """Corrige o saldo para o valor realmente contado nas prateleiras.

    A pessoa informa QUANTO EXISTE (saldo contado), e o sistema calcula a
    diferença. A movimentação guarda a diferença (sempre positiva) e os saldos
    antes/depois mostram o sentido.
    """
    produto = _carregar_produto(produto_id)
    novo_saldo = _validar_quantidade(saldo_contado, produto, "Saldo contado", permitir_zero=True)
    motivo = _validar_motivo(motivo)
    diferenca = novo_saldo - produto.quantidade_estoque
    if diferenca == 0:  # RN16
        raise ErroDeNegocio("O saldo informado é igual ao saldo atual. Não há o que ajustar.")
    return _registrar(produto, "AJUSTE", abs(diferenca), novo_saldo, motivo, usuario_id=usuario_id)


# ----------------------------------------------------------------- consultas
def historico(produto_id=None, tipo=None, data_inicio=None, data_fim=None, limite=LIMITE_HISTORICO):
    """Movimentações, da mais recente para a mais antiga.

    data_inicio/data_fim são datas no horário local do mercado (inclusivas).
    """
    if tipo and tipo not in TIPOS_MOVIMENTACAO:
        raise ErroDeNegocio("Tipo de movimentação inválido.")
    if data_inicio and data_fim and data_inicio > data_fim:
        raise ErroDeNegocio("A data inicial não pode ser posterior à data final.")

    consulta = (
        select(MovimentacaoEstoque)
        .options(joinedload(MovimentacaoEstoque.produto), joinedload(MovimentacaoEstoque.usuario))
        .order_by(desc(MovimentacaoEstoque.data_hora), desc(MovimentacaoEstoque.id))
        .limit(limite)
    )
    if produto_id:
        consulta = consulta.where(MovimentacaoEstoque.produto_id == produto_id)
    if tipo:
        consulta = consulta.where(MovimentacaoEstoque.tipo == tipo)
    inicio, fim_exclusivo = intervalo_utc(data_inicio, data_fim)
    if inicio:
        consulta = consulta.where(MovimentacaoEstoque.data_hora >= inicio)
    if fim_exclusivo:
        consulta = consulta.where(MovimentacaoEstoque.data_hora < fim_exclusivo)
    return db.session.execute(consulta).scalars().all()


def conferir_saldos():
    """Auditoria: o saldo de cada produto bate com a cadeia de movimentações?

    Para cada produto, percorre o histórico em ordem: o "saldo anterior" de
    cada movimentação deve ser o "saldo posterior" da anterior (começando em 0),
    e o último saldo deve ser igual ao saldo atual do produto.
    Devolve uma lista de (produto, saldo_esperado) dos que NÃO batem.
    """
    divergentes = []
    produtos = db.session.execute(select(Produto).order_by(Produto.id)).scalars().all()
    for produto in produtos:
        movimentacoes = db.session.execute(
            select(MovimentacaoEstoque)
            .where(MovimentacaoEstoque.produto_id == produto.id)
            .order_by(MovimentacaoEstoque.id)
        ).scalars().all()
        esperado = Decimal("0")
        cadeia_ok = True
        for mov in movimentacoes:
            if mov.saldo_anterior != esperado:
                cadeia_ok = False
            esperado = mov.saldo_posterior
        if not cadeia_ok or esperado != produto.quantidade_estoque:
            divergentes.append((produto, esperado))
    return divergentes
