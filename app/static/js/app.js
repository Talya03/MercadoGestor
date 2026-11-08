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
