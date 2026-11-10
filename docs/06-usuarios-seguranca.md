# Usuários, perfis e segurança de acesso (v0.11)

## Para que serve
Até a v0.10 qualquer pessoa que abrisse o endereço fazia tudo (inclusive ver custo e lucro). Agora **ninguém entra sem login**
e cada perfil só acessa o que precisa. Exemplo de mercado: a Ana (caixa) opera o PDV, mas não vê o aluguel nem o lucro do mês.

## Perfis e permissões
| Permissão | Telas | Dono | Gerente | Caixa |
|---|---|:-:|:-:|:-:|
| vender | PDV, vendas, comprovantes | ✔ | ✔ | ✔ |
| catálogo | produtos, categorias, estoque | ✔ | ✔ | |
| comprar | fornecedores, compras | ✔ | ✔ | |
| relatórios | relatórios (mostram custo e lucro) | ✔ | ✔ | |
| financeiro | contas, receitas, resumo mensal | ✔ | | |
| usuários | gerir usuários | ✔ | | |

Todos os perfis veem o Início (os blocos de contas e de resultado do mês só aparecem para quem tem a permissão "financeiro") e podem trocar a própria senha.
A matriz vive em um único arquivo: `app/permissoes.py`.

## Como a proteção funciona
Um "porteiro" (`app/seguranca.py`) olha **toda** requisição antes da rota:
1. Sem sessão válida → vai para o login (ou, em sistema sem usuários, para o primeiro acesso).
2. Senha temporária pendente → só a troca de senha e o logout são permitidos.
3. Módulo sem permissão para o perfil → **403** (a rota nem é executada, então não há efeito colateral).
4. Módulo **não classificado** em `permissoes.py` → 403 para todos (falha fechada: esquecer de classificar um módulo novo nunca o deixa aberto).

Um teste percorre **todas as rotas** do sistema como visitante e exige redirecionamento ao login; outro exige que todo endpoint esteja classificado.

## Regras de negócio
- **RN56** Login: 3 a 30 caracteres (minúsculas, números, ponto, hífen, sublinhado), único. Maiúsculas digitadas viram minúsculas.
- **RN57** Senha: 8 a 128 caracteres; não pode ser igual ao login, repetir um só caractere nem estar na lista de senhas óbvias. Só o **hash** é guardado (scrypt, ou PBKDF2 se o Python não tiver scrypt), com sal aleatório.
- **RN58** Perfis: dono, gerente, caixa.
- **RN59** A mensagem de falha no login é **sempre a mesma** (login inexistente, senha errada, conta bloqueada ou desativada) e o tempo gasto é parecido (login inexistente também calcula um hash).
- **RN60** 5 erros seguidos bloqueiam a conta por 5 minutos; durante o bloqueio nem a senha certa entra, e novas tentativas não prolongam o bloqueio.
- **RN61** Usuário desativado não entra e é desconectado na próxima requisição.
- **RN62** O sistema nunca fica sem dono ativo; ninguém desativa nem muda o perfil de si mesmo.
- **RN63** Senha temporária (conta nova ou redefinida) obriga a trocar antes de usar o sistema.
- **RN64** Trocar ou redefinir a senha, mudar o perfil ou desativar derruba as outras sessões da pessoa (campo `sessao_versao`).
- **RN65** Sistema sem nenhum usuário → tela de **primeiro acesso** cria o dono. Depois do primeiro usuário, a tela deixa de existir (um POST direto também é recusado).
- **RN66** Trocar a própria senha exige a senha atual (erros contam para o bloqueio); a nova deve ser diferente da atual.

## Outras proteções
- Sessão em cookie assinado, `HttpOnly`, `SameSite=Lax`, validade de 12 h (`SESSAO_HORAS`); a sessão guarda só o id do usuário e a versão, nunca senha.
- Login limpa a sessão anterior (contra *session fixation*); `next` do login só aceita caminhos internos (contra *open redirect*).
- Login, logout e todas as ações são **POST com token CSRF**; o CSRF é conferido **antes** do porteiro.
- Páginas com `Cache-Control: no-store` (o botão "voltar" não reabre tela após sair), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`.
- `AUTOINCREMENT` na tabela de usuários: um id nunca é reaproveitado, então uma sessão antiga jamais passa a valer para outra pessoa criada depois.
- **Chave secreta**: se `SECRET_KEY` não for definida, o sistema gera uma aleatória e a guarda em `instance/secret_key` (permissão 0600 em Linux/macOS).
- Senha temporária é mostrada **uma única vez**, na própria resposta (não passa pela sessão nem por redirecionamento).

## Como usar
1. Rode `python run.py` e abra o endereço: no primeiro acesso, crie o dono.
2. Em **Usuários**, crie o gerente e os caixas (deixe a senha em branco para o sistema gerar uma). Passe o login e a senha temporária à pessoa.
3. Esqueceu a senha? O dono usa **Redefinir senha**. Se o **único dono** esquecer a dele, veja "Limitações".

## Limitações conhecidas (leia antes de usar de verdade)
- **Recuperar o dono único:** não existe "esqueci a senha" por e-mail (o sistema é local e sem serviços externos). Se o único dono perder a senha, é preciso apagar a linha dele do banco com uma ferramenta de SQLite e refazer o primeiro acesso. Por isso, tenha sempre **dois donos**.
- O bloqueio é por conta, não por endereço de origem: alguém pode bloquear a conta de outra pessoa por 5 minutos errando a senha de propósito.
- O sistema roda em `http://127.0.0.1` (só o próprio computador). Se for expor na rede, use HTTPS e defina `SESSION_COOKIE_SECURE = True`; sem isso, a senha trafega em texto puro.
- Não há registro do **quem fez o quê** (vendas, ajustes, compras): isso é a próxima etapa (v0.12).
- O limite de desconto é o mesmo para todos os perfis (`DESCONTO_MAXIMO_PERCENTUAL`).
- Não há autenticação em dois fatores nem política de expiração de senha.
- Há um limite de 128 caracteres por senha (para impedir que uma senha gigante sobrecarregue o servidor).
- Esta fase **não** torna o sistema pronto para a internet: faltam, no mínimo, HTTPS, backup e recuperação testados e uma revisão de segurança independente.
