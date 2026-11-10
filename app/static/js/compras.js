// Tela "Nova compra": adiciona/remove linhas, mostra uma PRÉVIA do total e
// impede o clique duplo. A conta oficial é sempre feita no servidor.
(function () {
  const form = document.getElementById("form-compra");
  if (!form) return;
  const corpo = document.getElementById("linhas");
  const modelo = document.getElementById("modelo-linha");
  const total = document.getElementById("total-previa");

  function numero(texto) {
    // "1.234,56" -> 1234.56 ; texto inválido -> NaN
    const limpo = String(texto).trim().replace(/\s/g, "");
    if (!limpo) return NaN;
    const normal = limpo.includes(",") ? limpo.replace(/\./g, "").replace(",", ".") : limpo;
    return /^\d+(\.\d+)?$/.test(normal) ? Number(normal) : NaN;
  }

  function atualizarTotal() {
    let soma = 0;
    let algum = false;
    corpo.querySelectorAll(".linha-item").forEach(function (linha) {
      const qtd = numero(linha.querySelector('[name="quantidade"]').value);
      const custo = numero(linha.querySelector('[name="custo_unitario"]').value);
      if (!isNaN(qtd) && !isNaN(custo)) {
        soma += Math.round(qtd * custo * 100) / 100;
        algum = true;
      }
    });
    total.textContent = algum
      ? soma.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })
      : "—";
  }

  document.getElementById("adicionar-linha").addEventListener("click", function () {
    corpo.appendChild(modelo.content.cloneNode(true));
    corpo.lastElementChild.querySelector("select").focus();
  });

  corpo.addEventListener("click", function (evento) {
    if (!evento.target.closest(".js-remover-linha")) return;
    const linhas = corpo.querySelectorAll(".linha-item");
    const linha = evento.target.closest(".linha-item");
    if (linhas.length > 1) {
      linha.remove();
    } else {
      linha.querySelectorAll("input").forEach(function (i) { i.value = ""; });
      linha.querySelector("select").value = "";
    }
    atualizarTotal();
  });

  corpo.addEventListener("input", atualizarTotal);

  form.addEventListener("submit", function () {
    document.getElementById("registrar").disabled = true;
  });

  // O vencimento só faz sentido para compra a prazo.
  const condicao = document.getElementById("condicao");
  const grupoVenc = document.getElementById("grupo-vencimento");
  function atualizarVencimento() {
    grupoVenc.style.display = condicao.value === "A_PRAZO" ? "" : "none";
  }
  condicao.addEventListener("change", atualizarVencimento);
  atualizarVencimento();

  atualizarTotal();
})();
