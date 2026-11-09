// PDV: mostra o campo "valor recebido" só para dinheiro e calcula o troco na tela.
// IMPORTANTE: isto é só uma prévia para o caixa. O valor oficial do troco é
// sempre calculado e conferido pelo servidor ao finalizar a venda.
document.addEventListener("DOMContentLoaded", function () {
  const formulario = document.getElementById("form-finalizar");
  if (!formulario) return;

  const total = Number(formulario.dataset.total);
  const campoRecebido = document.getElementById("campo-recebido");
  const entradaRecebido = document.getElementById("valor_recebido");
  const textoTroco = document.getElementById("troco");
  const botao = document.getElementById("botao-finalizar");
  const dinheiro = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

  function lerNumero(texto) {
    texto = (texto || "").trim().replace(/\s/g, "");
    if (!texto) return null;
    if (texto.includes(",")) texto = texto.replace(/\./g, "").replace(",", ".");
    const numero = Number(texto);
    return Number.isFinite(numero) ? numero : null;
  }

  function formaEscolhida() {
    const marcada = formulario.querySelector('input[name="forma"]:checked');
    return marcada ? marcada.value : "";
  }

  function atualizar() {
    const ehDinheiro = formaEscolhida() === "DINHEIRO";
    campoRecebido.classList.toggle("d-none", !ehDinheiro);
    if (!ehDinheiro) return;

    const recebido = lerNumero(entradaRecebido.value);
    if (recebido === null) {
      textoTroco.textContent = "valor exato";
    } else if (recebido < total) {
      textoTroco.textContent = "faltam " + dinheiro.format(total - recebido);
    } else {
      textoTroco.textContent = dinheiro.format(recebido - total);
    }
  }

  formulario.addEventListener("change", atualizar);
  entradaRecebido.addEventListener("input", atualizar);
  // Evita o clique duplo em "Finalizar" (o servidor também se protege com um token).
  formulario.addEventListener("submit", function () {
    window.setTimeout(function () {
      botao.disabled = true;
    }, 0);
  });
  atualizar();

  const busca = document.getElementById("busca-pdv");
  if (busca) busca.focus();
});
