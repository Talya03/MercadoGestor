"""Regras de negócio do Financeiro: lançamentos, contas a pagar e resumo mensal.

Numeração continua a de docs/03-compras.md (detalhes em docs/04-financeiro.md):
- RN40: lançamento tem tipo (despesa/receita), categoria, descrição, valor > 0 (2 casas)
        e data (vencimento). Receita avulsa nasce RECEBIDA; despesa nasce paga ou pendente.
- RN41: a categoria "Compra de mercadoria" só é criada por uma Compra (não se digita à mão),
        para a mesma compra não ser contada duas vezes.
- RN42: pagar = informar a data do pagamento (padrão hoje; nunca no futuro).
        Só despesas pendentes e não canceladas podem ser pagas.
- RN43: desfazer pagamento volta a despesa para pendente (erro de digitação). Receita não.
- RN44: cancelar vale só para despesa PENDENTE que não veio de compra. Nada é excluído.
- RN45: conta vencida = pendente com vencimento anterior a hoje (horário do mercado).
- RN46: resumo mensal (por mês do vencimento/data do lançamento e, nas vendas, do dia da venda):
        resultado = (vendas - custo das mercadorias vendidas) + outras receitas - despesas
        operacionais. Compras de mercadoria NÃO entram nas despesas (entram via custo vendido),
        para não contar o mesmo dinheiro duas vezes.

Exemplo de mercado: aluguel de R$ 1.800,00 vence dia 10 (pendente = conta a pagar); dia 9 você
paga e informa a data; no resumo de novembro ele aparece em "Despesas operacionais".
"""
import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select

from app.extensions import db
from app.models import CATEGORIA_MERCADORIA, CATEGORIAS, Compra, ItemVenda, Lancamento, Venda
from app.models.lancamento import CATEGORIAS_DESPESA, CATEGORIAS_RECEITA
from app.utils.datas import intervalo_utc
from app.utils.erros import ErroDeNegocio
from app.utils.hoje import hoje_local
from app.utils.numeros import validar_decimal

CENTAVO = Decimal("0.01")
VALOR_MAXIMO = Decimal("99999999.99")
TAMANHO_MAX_DESCRICAO = 120
LIMITE_LISTAGEM = 300
ANO_MIN, ANO_MAX = 2000, 2100
STATUS_VALIDOS = ("pendentes", "pagos", "todos")


# ---------------------------------------------------------------- validações
def _normalizar(texto):
    return " ".join((texto or "").split())


def converter_data(valor, rotulo="Data"):
    """Aceita date ou texto ISO (AAAA-MM-DD, como o <input type=date> envia)."""
    if isinstance(valor, date):
        dia = valor
    else:
        try:
            dia = date.fromisoformat(str(valor or "").strip())
        except ValueError:
            raise ErroDeNegocio(f"{rotulo}: informe uma data válida.")
    if not ANO_MIN <= dia.year <= ANO_MAX:
        raise ErroDeNegocio(f"{rotulo}: o ano deve estar entre {ANO_MIN} e {ANO_MAX}.")
    return dia


def validar_valor(valor):
    numero = validar_decimal(valor, "Valor", 2, VALOR_MAXIMO)
    if numero == 0:
        raise ErroDeNegocio("O valor deve ser maior que zero.")
    return numero


def _buscar(lancamento_id):
    lancamento = db.session.get(Lancamento, lancamento_id)
    if lancamento is None:
        raise ErroDeNegocio("Lançamento não encontrado.")
    return lancamento


# ------------------------------------------------------------------- escrita
def criar(tipo, categoria, descricao, valor, data, ja_pago=False, data_pagamento=None):
    """Cria uma despesa/receita avulsa (RN40, RN41).

    `data`: vencimento da despesa ou data da receita.
    Receita é sempre recebida na própria data. Despesa `ja_pago` usa `data_pagamento`
    (padrão: hoje).
    """
    if tipo not in ("DESPESA", "RECEITA"):
        raise ErroDeNegocio("Tipo inválido: escolha despesa ou receita.")
    permitidas = CATEGORIAS_DESPESA if tipo == "DESPESA" else CATEGORIAS_RECEITA
    if categoria == CATEGORIA_MERCADORIA:
        raise ErroDeNegocio(  # RN41
            "Compras de mercadoria são lançadas em Compras, que já geram a conta a pagar."
        )
    if categoria not in permitidas:
        raise ErroDeNegocio("Escolha uma categoria válida.")
    descricao = _normalizar(descricao)
    if not descricao:
        raise ErroDeNegocio("Informe a descrição.")
    if len(descricao) > TAMANHO_MAX_DESCRICAO:
        raise ErroDeNegocio(f"A descrição pode ter no máximo {TAMANHO_MAX_DESCRICAO} caracteres.")
    valor = validar_valor(valor)
    vencimento = converter_data(data, "Data" if tipo == "RECEITA" else "Vencimento")

    pago_em = None
    if tipo == "RECEITA":
        pago_em = vencimento
    elif ja_pago:
        pago_em = _data_pagamento(data_pagamento)

    lancamento = Lancamento(
        tipo=tipo, categoria=categoria, descricao=descricao, valor=valor,
        vencimento=vencimento, pago_em=pago_em,
    )
    db.session.add(lancamento)
    db.session.commit()
    return lancamento


def _data_pagamento(data):
    if data in (None, ""):
        return hoje_local()
    dia = converter_data(data, "Data do pagamento")
    if dia > hoje_local():
        raise ErroDeNegocio("A data do pagamento não pode ser futura.")  # RN42
    return dia


def pagar(lancamento_id, data_pagamento=None):
    lancamento = _buscar(lancamento_id)
    if lancamento.tipo != "DESPESA":
        raise ErroDeNegocio("Receitas já nascem recebidas.")
    if lancamento.cancelado:
        raise ErroDeNegocio("Este lançamento foi cancelado.")
    if lancamento.pago_em:
        raise ErroDeNegocio("Esta conta já está paga.")
    lancamento.pago_em = _data_pagamento(data_pagamento)
    db.session.commit()
    return lancamento


def desfazer_pagamento(lancamento_id):
    lancamento = _buscar(lancamento_id)
    if lancamento.tipo != "DESPESA":
        raise ErroDeNegocio("Receitas não podem voltar a pendentes.")  # RN43
    if not lancamento.pago_em:
        raise ErroDeNegocio("Esta conta não está paga.")
    lancamento.pago_em = None
    db.session.commit()
    return lancamento


def cancelar(lancamento_id):
    lancamento = _buscar(lancamento_id)
    if lancamento.cancelado:
        raise ErroDeNegocio("Este lançamento já foi cancelado.")
    if lancamento.compra_id:  # RN44
        raise ErroDeNegocio("A conta de uma compra não pode ser cancelada (a compra não é estornada).")
    if lancamento.tipo != "DESPESA" or lancamento.pago_em:
        raise ErroDeNegocio("Só é possível cancelar despesas pendentes. Se está paga, desfaça o pagamento antes.")
    lancamento.cancelado = True
    db.session.commit()
    return lancamento


# ------------------------------------------------------------------ consultas
def buscar(lancamento_id):
    return _buscar(lancamento_id)


def esta_vencida(lancamento, hoje=None):
    """RN45"""
    return (
        lancamento.tipo == "DESPESA"
        and not lancamento.cancelado
        and lancamento.pago_em is None
        and lancamento.vencimento < (hoje or hoje_local())
    )


def listar(status="pendentes", tipo=None, data_inicio=None, data_fim=None, limite=LIMITE_LISTAGEM):
    """Lançamentos por vencimento (os mais antigos primeiro). Cancelados nunca aparecem."""
    if status not in STATUS_VALIDOS:
        raise ErroDeNegocio("Situação inválida.")
    if tipo and tipo not in ("DESPESA", "RECEITA"):
        raise ErroDeNegocio("Tipo inválido.")
    if data_inicio and data_fim and data_inicio > data_fim:
        raise ErroDeNegocio("A data inicial não pode ser posterior à data final.")
    consulta = (
        select(Lancamento)
        .where(Lancamento.cancelado.is_(False))
        .order_by(Lancamento.vencimento, Lancamento.id)
        .limit(limite)
    )
    if status == "pendentes":
        consulta = consulta.where(Lancamento.pago_em.is_(None))
    elif status == "pagos":
        consulta = consulta.where(Lancamento.pago_em.is_not(None))
    if tipo:
        consulta = consulta.where(Lancamento.tipo == tipo)
    if data_inicio:
        consulta = consulta.where(Lancamento.vencimento >= data_inicio)
    if data_fim:
        consulta = consulta.where(Lancamento.vencimento <= data_fim)
    return db.session.execute(consulta).scalars().all()


def total_a_pagar():
    """(total pendente, total vencido) das despesas não canceladas."""
    pendentes = db.session.execute(
        select(Lancamento).where(
            Lancamento.tipo == "DESPESA", Lancamento.cancelado.is_(False), Lancamento.pago_em.is_(None)
        )
    ).scalars().all()
    hoje = hoje_local()
    total = sum((l.valor for l in pendentes), Decimal("0"))
    vencido = sum((l.valor for l in pendentes if l.vencimento < hoje), Decimal("0"))
    return total, vencido


# --------------------------------------------------------------- resumo mensal
@dataclass
class ResumoMensal:
    ano: int
    mes: int
    vendas: Decimal = Decimal("0")
    qtd_vendas: int = 0
    custo_vendido: Decimal = Decimal("0")
    outras_receitas: Decimal = Decimal("0")
    despesas: Decimal = Decimal("0")
    despesas_pagas: Decimal = Decimal("0")
    despesas_pendentes: Decimal = Decimal("0")
    compras: Decimal = Decimal("0")  # informativo: não entra no resultado (RN46)
    despesas_por_categoria: list = field(default_factory=list)  # [(nome, valor)]

    @property
    def lucro_bruto(self):
        return self.vendas - self.custo_vendido

    @property
    def margem_bruta(self):
        """Lucro bruto / vendas, em %; None quando não há vendas."""
        if self.vendas == 0:
            return None
        return (self.lucro_bruto / self.vendas * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    @property
    def resultado(self):
        return self.lucro_bruto + self.outras_receitas - self.despesas


def limites_do_mes(ano, mes):
    if not (ANO_MIN <= ano <= ANO_MAX and 1 <= mes <= 12):
        raise ErroDeNegocio("Mês inválido.")
    return date(ano, mes, 1), date(ano, mes, calendar.monthrange(ano, mes)[1])


def resumo_mensal(ano, mes):
    primeiro, ultimo = limites_do_mes(ano, mes)
    resumo = ResumoMensal(ano, mes)
    inicio, fim = intervalo_utc(primeiro, ultimo)  # o mês é o do MERCADO, não o de UTC

    vendas = db.session.execute(
        select(func.count(Venda.id), func.coalesce(func.sum(Venda.total), 0))
        .where(Venda.data_hora >= inicio, Venda.data_hora < fim)
    ).one()
    resumo.qtd_vendas = vendas[0]
    resumo.vendas = Decimal(vendas[1]).quantize(CENTAVO)

    # Custo das mercadorias vendidas: custo COPIADO no item no dia da venda x quantidade,
    # arredondado ao centavo por item (meio para cima), igual ao subtotal.
    linhas = db.session.execute(
        select(ItemVenda.custo_unitario, ItemVenda.quantidade)
        .join(Venda, Venda.id == ItemVenda.venda_id)
        .where(Venda.data_hora >= inicio, Venda.data_hora < fim)
    ).all()
    resumo.custo_vendido = sum(
        ((Decimal(c) * Decimal(q)).quantize(CENTAVO, rounding=ROUND_HALF_UP) for c, q in linhas),
        Decimal("0"),
    )

    resumo.compras = Decimal(
        db.session.execute(
            select(func.coalesce(func.sum(Compra.total), 0)).where(
                Compra.data_hora >= inicio, Compra.data_hora < fim
            )
        ).scalar()
    ).quantize(CENTAVO)

    lancamentos = db.session.execute(
        select(Lancamento).where(
            Lancamento.cancelado.is_(False),
            Lancamento.vencimento >= primeiro,
            Lancamento.vencimento <= ultimo,
        )
    ).scalars().all()
    por_categoria = {}
    for l in lancamentos:
        if l.tipo == "RECEITA":
            resumo.outras_receitas += l.valor
        elif l.categoria != CATEGORIA_MERCADORIA:  # RN46
            resumo.despesas += l.valor
            if l.pago_em:
                resumo.despesas_pagas += l.valor
            else:
                resumo.despesas_pendentes += l.valor
            por_categoria[l.categoria] = por_categoria.get(l.categoria, Decimal("0")) + l.valor
    resumo.despesas_por_categoria = sorted(
        ((CATEGORIAS[c], v) for c, v in por_categoria.items()), key=lambda x: -x[1]
    )
    return resumo
