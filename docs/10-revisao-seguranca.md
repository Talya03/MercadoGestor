# Revisão final de segurança (Fase 9)

Revisão do sistema inteiro, feita sobre o código e verificada por testes automáticos (`tests/test_revisao_seguranca.py`,
`tests/test_recuperacao.py`) e por um teste no navegador com todas as telas. **Não substitui** uma auditoria profissional.

## Resultado em uma frase
Adequado para uso **local, em um computador, por um mercado pequeno**, com os cuidados da seção "O que você precisa fazer".
**Não** está pronto para ser colocado na internet nem para uso em rede com vários computadores.

## O que foi verificado
| Tema | Situação | Como é garantido |
|---|---|---|
| Acesso sem login | Protegido | Guarda global "negar por padrão"; teste varre **todas** as rotas como visitante |
| Permissões por perfil | Protegido | Matriz dono/gerente/caixa testada; módulo não listado é negado a todos |
| CSRF (ataque por outro site) | Protegido | Teste envia POST sem token em **toda** rota POST e exige recusa |
| Alterar dados por GET | Protegido | Teste confere que rotas que alteram dados só aceitam POST |
| Senhas | Protegido | Hash scrypt, mensagem única de login, bloqueio após 5 erros, troca de senha derruba as sessões |
| Sessão | Protegido | Cookie HttpOnly + SameSite, expira em 12 h, sessão nova no login (fixation) |
| Redirecionamento aberto | Protegido | `next` só aceita caminhos do próprio sistema |
| SQL injection | Protegido | Só consultas do SQLAlchemy com parâmetros; o único SQL escrito à mão (migração) usa nomes fixos do código |
| XSS (script injetado numa tela) | Protegido | Escape automático do Jinja (teste proíbe `\|safe`) + **CSP** (`script-src 'self'`): script injetado é bloqueado (comprovado no navegador) |
| Recursos de terceiros | Eliminado | Bootstrap agora é local (arquivos oficiais, hash conferido por teste); não há CDN, funciona sem internet |
| Clickjacking | Protegido | `X-Frame-Options: DENY` e `frame-ancestors 'none'` |
| Erros | Protegido | Páginas 400/403/404/500 amigáveis, sem traceback nem caminhos de arquivo |
| Depurador | **Corrigido** | `debug=True` permitia executar código por quem abrisse a página de erro; agora vem desligado |
| Segredos no Git | **Corrigido** | `.gitignore` só cobria `instance/*.db`; ficavam de fora `secret_key`, `backups/` e `*.antes-da-migracao-*` |
| Valores monetários | Protegido | `Decimal` ponta a ponta, limites e CHECK no banco |
| Duplo clique / reenvio | Protegido | Token de envio único em venda e compra |
| Perda de dados | Protegido | Backup consistente + restauração testada em 6 cenários (arquivo apagado, corrompido, dados apagados, backup antigo, arquivo ruim, pen drive) |
| Auditoria | Parcial | Registra quem vendeu, ajustou estoque, comprou e lançou; **não** registra quem alterou preços/cadastros/logins |

## Corrigido nesta revisão
1. `debug=True` no `run.py` -> desligado por padrão (`MERCADOGESTOR_DEBUG=1` para desenvolver).
2. `.gitignore` incompleto -> `instance/` inteiro fica fora do Git.
3. Telas de login e primeiro acesso ainda carregavam Bootstrap do CDN (achado pelo teste no navegador, ficariam sem estilo com a CSP) -> locais.
4. JavaScript dentro do HTML (botão Imprimir, formulário financeiro) -> movido para arquivos, para permitir a CSP.
5. Erro de token CSRF mostrava página técnica -> página amigável. Erro 500 e 404 também.

## O que você precisa fazer (ações suas)
1. **Verifique se `instance/` já foi para o Git:** `git ls-files instance`. Se listar algo, rode `git rm -r --cached instance`
   e faça commit. Se o repositório já foi publicado (GitHub público), **considere o banco e as senhas expostos**: apague
   `instance/secret_key` (uma nova é gerada) e troque as senhas de todos os usuários.
2. Faça **backup** com frequência e guarde **fora do computador** (pen drive). Teste uma restauração.
3. Se a pasta do projeto está no **OneDrive**, o `instance/` é sincronizado com a nuvem: proteja a conta com verificação em duas etapas.
4. Use senhas fortes e **uma conta por pessoa** (não compartilhe o login do dono com o caixa).
5. Deixe o Windows atualizado e com senha de login; o sistema é tão seguro quanto o computador onde roda.
6. Defina `SECRET_KEY` por variável de ambiente se quiser controlar a chave (opcional; há uma automática).

## Riscos que restam (aceitos, por serem fora do escopo)
- **Sem HTTPS.** O tráfego é local (127.0.0.1). Por isso o sistema **não deve** ser aberto para a rede/Wi-Fi do mercado.
- **Um computador, um servidor de desenvolvimento.** O servidor do Flask (`run.py`) não é um servidor de produção. Vários caixas ao mesmo tempo (SQLite + servidor de desenvolvimento) não são suportados.
- **Bloqueio de login por conta, não por IP.** Alguém com acesso físico ao teclado ainda pode tentar senhas (5 erros bloqueiam a conta por 5 min).
- **Backup sem criptografia** e contendo os hashes das senhas: trate o arquivo como o próprio banco.
- **Quem tem acesso ao Windows/arquivos do computador tem acesso a tudo** (banco e chave secreta ficam em `instance/` sem criptografia).
- **Sem registro de alterações de preço, cadastros e usuários** (só de operações financeiras e de estoque).
- **Dependências sem versão fixa** (`>=`). Para reproduzir exatamente seu ambiente: `pip freeze > requirements-lock.txt`.
- **Sem nota fiscal.** O comprovante diz "não é documento fiscal". Um mercado que precisa emitir NFC-e/SAT precisa de outro sistema.
- **Desconto não é rateado por produto** nos relatórios de lucro (limitação documentada).
- **O teste manual de segurança foi feito por mim em ambiente de teste.** Não houve teste de penetração por terceiros.

## Checklist antes de usar com dinheiro de verdade
- [ ] Rodou `pytest` e viu todos passando no seu computador.
- [ ] Fez e **restaurou** um backup de teste.
- [ ] Criou usuários separados para dono, gerente e caixa e testou o que cada um vê.
- [ ] Conferiu o `.gitignore` e o `git ls-files instance` (item 1 acima).
- [ ] Cadastrou os produtos reais e fez uma venda de teste conferindo estoque e financeiro.
- [ ] Definiu quem faz o backup e quando (ex.: todo dia ao fechar).
