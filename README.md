# Agente de concursos da Bahia no Telegram

Monitora concursos e processos seletivos da Bahia, priorizando PMBA, PCBA,
guardas municipais, áreas administrativas e tecnologia da informação.

## O que ele envia

- alerta imediato para edital, banca, inscrições, retificação, prova, resultado,
  convocação e nomeação;
- resumo diário às 19h, inclusive avisando quando não houve novidade;
- fonte e link em todas as mensagens;
- nenhuma repetição: as publicações vistas ficam registradas em `state.json`.

Na primeira execução, o programa apenas cadastra as notícias existentes. Isso evita
uma enxurrada de alertas antigos. Elas aparecerão no primeiro resumo; alertas
imediatos começam nas execuções seguintes.

## Instalação gratuita

1. No Telegram, abra `@BotFather`, envie `/newbot` e siga as instruções.
2. Copie o token fornecido. Não publique nem envie esse token em conversas.
3. Abra uma conversa com o novo bot e envie `/start`.
4. No navegador, acesse `https://api.telegram.org/botSEU_TOKEN/getUpdates`.
5. Localize `chat` e copie o número de `id`.
6. Crie um repositório no GitHub e envie todos os arquivos desta pasta.
7. No repositório, abra **Settings > Secrets and variables > Actions**.
8. Crie os segredos `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`.
9. Abra **Actions > Monitor de concursos da Bahia > Run workflow**.

O processo roda a cada duas horas, das 8h às 23h no horário de São Paulo. Para
alterar temas, fontes ou horário, edite `config.json`.

## Segurança e confiabilidade

O token fica nos Secrets do GitHub e nunca deve ser gravado em arquivo. O agente
aceita apenas domínios incluídos em `trusted_domains`. Uma descoberta ainda pode
apontar para conteúdo incorreto ou desatualizado; por isso, confirme prazos e
requisitos no edital ou Diário Oficial antes de inscrição ou pagamento.

## Teste no computador (opcional)

No PowerShell:

```powershell
$env:TELEGRAM_BOT_TOKEN = "token-do-bot"
$env:TELEGRAM_CHAT_ID = "numero-do-chat"
python agent.py
```

Python 3.9 ou superior é suficiente e não há bibliotecas adicionais para instalar.
