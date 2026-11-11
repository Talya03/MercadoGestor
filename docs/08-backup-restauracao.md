# v0.13 — Backup e restauração

## Por que
Todo o mercado está num único arquivo (`instance/mercadogestor.db`). Se o computador quebrar, for roubado ou o arquivo
corromper, **tudo se perde**. Backup é a única proteção real, e só vale se for guardado **fora** do computador.

## Como fazer backup (somente DONO)
Menu **Backup → Fazer backup agora**. O arquivo vai para `instance/backups/mercadogestor-AAAAMMDD-HHMMSS.db`.
Use **Baixar** e guarde numa pen drive ou disco externo. Sugestão: ao fechar o mercado, todo dia.

## Regras
- **RN72** Usa a API de backup do SQLite: cópia consistente mesmo com o sistema em uso.
- **RN73** O backup é verificado (integridade + tabelas esperadas); se falhar, é descartado e o erro é mostrado.
- **RN74** Ficam os 14 mais recentes (`BACKUP_MANTER`); arquivos que não são backups nunca são apagados.
- **RN75** O arquivo a baixar é validado por um padrão fixo de nome; caminhos como `../` são recusados.
- **RN76** Restaurar sempre guarda antes uma cópia do banco atual.
- Só o DONO vê e baixa backups: eles contêm todos os dados e os hashes das senhas.

## Como restaurar
1. **Feche o sistema** (Ctrl+C no terminal onde roda `python run.py`).
2. No terminal da pasta do projeto: `python restaurar.py instance/backups/mercadogestor-AAAAMMDD-HHMMSS.db`
3. O banco anterior fica em `instance/mercadogestor.db.antes-da-restauracao-DATA-HORA` (nada é apagado).
4. Inicie de novo: `python run.py`.

Para restaurar a partir de uma pen drive, passe o caminho do arquivo dela no passo 2.

## Teste seu backup
Um backup que nunca foi restaurado é só uma esperança. Pelo menos uma vez, restaure um backup numa cópia da pasta do
projeto e confira se os dados aparecem.

## Limitações
- Não há backup agendado automático (plano gratuito, sem serviços externos): é um clique manual.
- Restaurar exige o sistema fechado e o terminal.
- O backup não é criptografado.
