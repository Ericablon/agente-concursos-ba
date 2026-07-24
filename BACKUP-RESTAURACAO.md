# Backup e restauração do JARVIS

Este repositório guarda somente código e documentação. Nenhum valor de token,
senha ou chave secreta deve ser enviado ao GitHub.

## Componentes

- `agent.py` e `config.json`: monitor e relatórios executados pelo GitHub Actions.
- `cloudflare/worker.js`: assistente, Telegram, voz, memória, tarefas e painel.
- `google-apps-script/bridge.gs`: ponte de leitura da agenda e da planilha.
- `state.json`: controle de notícias, relatórios e fichas dos concursos.

## Segredos que permanecem fora do GitHub

No Cloudflare Worker:

- `TELEGRAM_BOT_TOKEN`
- `OWNER_CHAT_ID`
- `WEBHOOK_SECRET`
- `CF_API_TOKEN`
- `CF_ACCOUNT_ID`
- `ELEVENLABS_API_KEY`
- `ELEVENLABS_VOICE_ID`
- `MOBILE_SECRET`
- `GOOGLE_BRIDGE_URL`
- `GOOGLE_BRIDGE_SECRET`
- `DASHBOARD_SECRET`

No Google Apps Script:

- `BRIDGE_SECRET`
- `SHEET_ID`
- `SHEET_TAB`

## Restauração resumida

1. Crie ou abra um Cloudflare Worker.
2. Cole `cloudflare/worker.js` no arquivo `worker.js`.
3. Vincule um banco D1 com o nome de variável `DB`.
4. Cadastre novamente os segredos listados acima.
5. Configure um gatilho cron, recomendado a cada cinco minutos.
6. Implante o Worker.
7. No Google Apps Script, cole `google-apps-script/bridge.gs`, configure as
   propriedades e atualize a implantação do aplicativo da Web.
8. Registre novamente o webhook do Telegram, se necessário.

O painel ficará disponível em:

`https://SEU-WORKER.workers.dev/painel`

