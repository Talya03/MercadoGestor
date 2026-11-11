// Formulário de lançamento: mostra os campos de pagamento só quando "já pago" está marcado.
(function () {
  const marca = document.getElementById("ja_pago");
  const grupo = document.getElementById("grupo-pagamento");
  if (!marca || !grupo) return;
  function atualizar() { grupo.style.display = marca.checked ? "" : "none"; }
  marca.addEventListener("change", atualizar);
  atualizar();
})();
