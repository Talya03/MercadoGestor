"""Regras de negócio da Compra de mercadoria.

Numeração continua a de docs/02-vendas-pdv.md (detalhes em docs/03-compras.md):
- RN33: a compra precisa de um fornecedor ATIVO e de ao menos um item; cada produto
        aparece uma só vez e precisa estar ativo.
- RN34: quantidade > 0 (inteira para UN/CX/PCT, até 3 casas para KG/G/L/ML: RN14) e
        custo unitário > 0 (até 2 casas decimais).
- RN35: subtotal do item = custo x quantidade, arredondado ao centavo (meio para cima);
        total da compra = soma dos subtotais.
- RN36: registrar é ATÔMICO: compra + itens + entradas de estoque (motivo "Compra #N")
        + atualização do custo do produto valem juntos ou não valem nada.
- RN37: o custo do produto passa a ser o custo da ÚLTIMA compra (o preço de venda
        NÃO muda sozinho; a tela avisa quando ele fica abaixo do custo).
- RN38: o mesmo envio de formulário não gera duas compras (token de envio único).
- RN39: compra concluída não é editada nem excluída (se errou, corrija com ajuste de
        estoque; estorno de compra: fase futura).
- RN47: toda compra gera uma conta a pagar (despesa "Compra de mercadoria") NA MESMA
        transação: à vista = já paga hoje; a prazo = pendente, com vencimento hoje ou depois.

Exemplo de mercado: chegam 24 UN de leite a R$ 4,80 e 10 kg de tomate a R$ 6,20 da
"Distribuidora Bom Preço": total R$ 177,20, estoque sobe e o custo dos produtos é atualizado.
"""
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import CATEGORIA_MERCADORIA, Compra, Fornecedor, ItemCompra, Lancamento, Produto
from app.services import estoque_service
from app.utils.datas import intervalo_utc
from app.utils.erros import ErroDeNegocio
from app.utils.hoje import hoje_local
from app.utils.numeros import validar_decimal

CENTAVO = Decimal("0.01")
VALOR_MAXIMO = Decimal("99999999.99")
MAX_ITENS = 200
TAMANHO_MAX_DOCUMENTO = 30
TAMANHO_MAX_OBSERVACAO = 255
LIMITE_LISTAGEM = 200


def _converter_data(valor, rotulo):
    # Import tardio: financeiro_service importa Compra; aqui só precisamos do conversor.
    from app.services.financeiro_service import converter_data

    return converter_data(valor, rotulo)


def _normalizar(texto):
    return " ".join((texto or "").split())


def _texto_opcional(texto, limite, rotulo):
    texto = _normalizar(texto)
    if len(texto) > limite:
        raise ErroDeNegocio(f"{rotulo} pode ter no máximo {limite} caracteres.")
    return texto or None


def _validar_item(bruto, numero):
    """Converte/valida uma linha digitada. Devolve (produto, quantidade, custo, subtotal)."""
    onde = f"Item {numero}"
    try:
        produto_id = int(bruto.get("produto_id"))
    except (TypeError, ValueError):
        raise ErroDeNegocio(f"{onde}: selecione o produto.")

    produto = db.session.get(Produto, produto_id, populate_existing=True)
    if produto is None:
        raise ErroDeNegocio(f"{onde}: produto não encontrado.")
    if not produto.ativo:
        raise ErroDeNegocio(f'{onde}: o produto "{produto.nome}" está inativo.')

    rotulo = f'{onde} ("{produto.nome}")'
    quantidade = estoque_service.validar_quantidade(
        bruto.get("quantidade"), produto, f"{rotulo}: quantidade"
    )
    custo = validar_decimal(bruto.get("custo_unitario"), f"{rotulo}: custo unitário", 2, VALOR_MAXIMO)
    if custo == 0:
        raise ErroDeNegocio(f"{rotulo}: o custo unitário deve ser maior que zero.")  # RN34

    subtotal = (custo * quantidade).quantize(CENTAVO, rounding=ROUND_HALF_UP)  # RN35
    if subtotal == 0:
        raise ErroDeNegocio(f"{rotulo}: o subtotal ficou zerado; confira quantidade e custo.")
    if subtotal > VALOR_MAXIMO:
        raise ErroDeNegocio(f"{rotulo}: o subtotal é grande demais.")
    return produto, quantidade, custo, subtotal


def registrar(fornecedor_id, itens, numero_documento=None, observacao=None, token_envio=None,
              condicao="A_VISTA", vencimento=None, usuario_id=None):
    """Registra a compra inteira de forma atômica (RN33 a RN38). Devolve a Compra.

    `itens`: lista de dicts com 'produto_id', 'quantidade' e 'custo_unitario'
    (texto digitado ou Decimal).
    `condicao`: "A_VISTA" (paga hoje) ou "A_PRAZO" (pendente, exige `vencimento`; RN47).
    """
    fornecedor = db.session.get(Fornecedor, fornecedor_id) if fornecedor_id else None
    if fornecedor is None:
        raise ErroDeNegocio("Selecione o fornecedor.")
    if not fornecedor.ativo:
        raise ErroDeNegocio(f'O fornecedor "{fornecedor.nome}" está inativo.')  # RN33
    if not itens:
        raise ErroDeNegocio("Inclua ao menos um item na compra.")  # RN33
    if len(itens) > MAX_ITENS:
        raise ErroDeNegocio(f"A compra pode ter no máximo {MAX_ITENS} itens.")
    numero_documento = _texto_opcional(numero_documento, TAMANHO_MAX_DOCUMENTO, "O número do documento")
    observacao = _texto_opcional(observacao, TAMANHO_MAX_OBSERVACAO, "A observação")
    if token_envio and compra_por_token(token_envio):
        raise ErroDeNegocio("Esta compra já foi registrada.")  # RN38
    hoje = hoje_local()
    if condicao == "A_PRAZO":
        if vencimento in (None, ""):
            raise ErroDeNegocio("Informe o vencimento da compra a prazo.")
        vencimento = _converter_data(vencimento, "Vencimento")
        if vencimento < hoje:
            raise ErroDeNegocio("O vencimento não pode ser anterior a hoje.")
    elif condicao == "A_VISTA":
        vencimento = hoje
    else:
        raise ErroDeNegocio("Escolha se a compra foi à vista ou a prazo.")

    try:
        validados = []
        vistos = set()
        for numero, bruto in enumerate(itens, start=1):
            produto, quantidade, custo, subtotal = _validar_item(bruto, numero)
            if produto.id in vistos:  # RN33
                raise ErroDeNegocio(
                    f'Item {numero}: o produto "{produto.nome}" já está na compra. '
                    "Some as quantidades em uma só linha."
                )
            vistos.add(produto.id)
            validados.append((produto, quantidade, custo, subtotal))

        total = sum((v[3] for v in validados), Decimal("0"))
        if total > VALOR_MAXIMO:
            raise ErroDeNegocio("O total da compra é grande demais.")

        compra = Compra(
            fornecedor_id=fornecedor.id,
            numero_documento=numero_documento,
            observacao=observacao,
            total=total,
            token_envio=token_envio or None,
            usuario_id=usuario_id,  # RN67
        )
        db.session.add(compra)
        db.session.flush()  # gera o número da compra para usar no motivo da entrada

        for produto, quantidade, custo, subtotal in validados:
            db.session.add(
                ItemCompra(
                    compra_id=compra.id,
                    produto_id=produto.id,
                    quantidade=quantidade,
                    custo_unitario=custo,
                    subtotal=subtotal,
                )
            )
            try:
                estoque_service.entrada(
                    produto.id, quantidade, f"Compra #{compra.id}", confirmar=False,
                    usuario_id=usuario_id,
                )
            except ErroDeNegocio as erro:
                raise ErroDeNegocio(f"{produto.nome}: {erro}")
            produto.preco_custo = custo  # RN37

        db.session.add(  # RN47: a conta a pagar nasce junto com a compra
            Lancamento(
                tipo="DESPESA",
                categoria=CATEGORIA_MERCADORIA,
                descricao=f"Compra #{compra.id} - {fornecedor.nome}"[:120],
                valor=total,
                vencimento=vencimento,
                pago_em=hoje if condicao == "A_VISTA" else None,
                compra_id=compra.id,
                usuario_id=usuario_id,
            )
        )
        db.session.commit()  # único commit: tudo vale junto (RN36)
    except ErroDeNegocio:
        db.session.rollback()
        raise
    except IntegrityError:
        db.session.rollback()
        if token_envio and compra_por_token(token_envio):
            raise ErroDeNegocio("Esta compra já foi registrada.")
        raise ErroDeNegocio("Não foi possível registrar a compra. Nada foi alterado.")
    except Exception:
        db.session.rollback()
        raise
    return compra


# ---------------------------------------------------------------- consultas
def compra_por_token(token):
    """A compra já registrada com este token de envio, ou None (RN38)."""
    if not token:
        return None
    return db.session.execute(select(Compra).where(Compra.token_envio == token)).scalar_one_or_none()


def buscar(compra_id):
    consulta = (
        select(Compra)
        .options(
            joinedload(Compra.fornecedor), joinedload(Compra.usuario),
            joinedload(Compra.itens).joinedload(ItemCompra.produto),
            joinedload(Compra.lancamento),
        )
        .where(Compra.id == compra_id)
    )
    compra = db.session.execute(consulta).unique().scalar_one_or_none()
    if compra is None:
        raise ErroDeNegocio("Compra não encontrada.")
    return compra


def listar(data_inicio=None, data_fim=None, fornecedor_id=None, limite=LIMITE_LISTAGEM):
    """Compras da mais recente para a mais antiga. Datas no horário local (inclusivas)."""
    if data_inicio and data_fim and data_inicio > data_fim:
        raise ErroDeNegocio("A data inicial não pode ser posterior à data final.")
    consulta = (
        select(Compra)
        .options(joinedload(Compra.fornecedor), joinedload(Compra.usuario))
        .order_by(Compra.data_hora.desc(), Compra.id.desc())
        .limit(limite)
    )
    if fornecedor_id:
        consulta = consulta.where(Compra.fornecedor_id == fornecedor_id)
    inicio, fim_exclusivo = intervalo_utc(data_inicio, data_fim)
    if inicio:
        consulta = consulta.where(Compra.data_hora >= inicio)
    if fim_exclusivo:
        consulta = consulta.where(Compra.data_hora < fim_exclusivo)
    return db.session.execute(consulta).scalars().all()
