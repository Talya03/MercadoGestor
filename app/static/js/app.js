// Confirmação antes de operações importantes.
// Uso no HTML: <form data-confirmar="Deseja mesmo desativar?"> ... </form>
// O texto fica em um atributo (e não dentro do JavaScript do HTML) para que
// nomes com aspas ou apóstrofos não quebrem a página.
document.addEventListener("submit", function (evento) {
  const mensagem = evento.target.getAttribute("data-confirmar");
  if (mensagem && !window.confirm(mensagem)) {
    evento.preventDefault();
  }
});

// Botão "Imprimir": <button data-imprimir>. Fica aqui (e não em onclick="...") porque a política de
// segurança do sistema (CSP) não permite JavaScript escrito dentro do HTML.
document.addEventListener("click", function (evento) {
  if (evento.target.closest("[data-imprimir]")) {
    window.print();
  }
});
