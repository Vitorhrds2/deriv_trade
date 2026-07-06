# Agentic Conversation — Integração Devin ↔ Telegram

Ponte entre o Telegram e agentes Devin (Cloud e Local/Macbook), com foco em **input e output**:
ver em tempo real o que cada agente está fazendo, enviar mensagens em fila, falar
simultaneamente com múltiplos agentes, criar/gerenciar sessões, tudo pelo chat do Telegram.

```
Telegram  ⇄  Bot (este projeto)  ⇄  Devin Cloud API (api.devin.ai)
                                  ⇄  Devin Local (Macbook) via relay HTTP
```

## Componentes

| Arquivo | Função |
| --- | --- |
| `run.py` | Entry point do bot (long polling do Telegram) |
| `devin_telegram/config.py` | Configuração via variáveis de ambiente |
| `devin_telegram/telegram_api.py` | Cliente mínimo da Bot API do Telegram |
| `devin_telegram/devin_api.py` | Cliente da API Devin Cloud (sessões, mensagens, status) |
| `devin_telegram/local_agent.py` | Adapter para o Devin Local (Macbook) via relay HTTP |
| `devin_telegram/registry.py` | Registro persistente de agentes/sessões (JSON em disco) |
| `devin_telegram/queue_manager.py` | Filas de mensagens por agente (enfileirar, listar, despachar) |
| `devin_telegram/watcher.py` | Watcher de output: faz polling das sessões e envia novidades ao chat |
| `devin_telegram/router.py` | Parser de comandos e roteamento das mensagens |
| `devin_telegram/bot.py` | Loop principal do bot |
| `local_relay.py` | Servidor relay para rodar **no Macbook** e expor o Devin Local |

## Variáveis de ambiente

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Sim | Token do bot (via @BotFather) |
| `TELEGRAM_CHAT_ID` | Sim | Chat autorizado (mensagens de outros chats são ignoradas) |
| `DEVIN_API_KEY` | Para Cloud | API key da Devin Cloud API (`https://app.devin.ai/settings/api-keys`) |
| `DEVIN_API_BASE` | Não | Default `https://api.devin.ai/v1` |
| `LOCAL_DEVIN_URL` | Para Local | URL do relay no Macbook (ex.: via Tailscale `http://macbook:8787`) |
| `STATE_DIR` | Não | Diretório de estado (default `./state`) |
| `POLL_INTERVAL` | Não | Intervalo (s) do watcher de output (default `15`) |

## Instalação e execução

```bash
cd agentic-conversation
pip install -r requirements.txt
cp .env.example .env   # preencha os valores
set -a && source .env && set +a
python run.py
```

No **Macbook** (para o Devin Local):

```bash
python local_relay.py --port 8787
# exponha via Tailscale/ngrok e configure LOCAL_DEVIN_URL no bot
```

## Comandos do bot

### Gerenciamento de agentes/sessões
- `/new <prompt>` — cria uma nova sessão Devin Cloud e registra como agente
- `/attach <session_id> [alias]` — registra uma sessão Cloud existente
- `/local [alias]` — registra o Devin Local (via relay) como agente
- `/agents` — lista agentes registrados (alias, tipo, status, watch on/off)
- `/use <alias>` — define o agente ativo (mensagens sem prefixo vão para ele)
- `/detach <alias>` — remove o agente do registro
- `/sessions` — lista sessões recentes na Devin Cloud

### Conversa (input)
- Mensagem simples — vai para o agente ativo
- `@alias mensagem` — envia para um agente específico (multiplexação)
- `/all <mensagem>` — broadcast para **todos** os agentes simultaneamente

### Fila de mensagens
- `/queue <alias> <mensagem>` — enfileira mensagem para o agente
- `/queues` — mostra todas as filas e seus tamanhos
- `/flush <alias>` — despacha a fila do agente em ordem
- `/clearqueue <alias>` — descarta a fila

### Output / observabilidade
- `/status [alias]` — status da sessão + últimas mensagens
- `/watch <alias> on|off` — liga/desliga streaming de output para o chat
  (o watcher faz polling e envia toda mensagem nova do Devin, prefixada com `[alias]`)
- `/help` — ajuda

## Fluxo típico

```
/new Investigar hipótese X no dydx          → cria devin-1
/attach devin-abc123 pesquisador            → anexa sessão existente
/local mac                                  → registra o Macbook
/watch devin-1 on                           → output do devin-1 chega no chat
@pesquisador qual o status do backtest?     → fala com o pesquisador
/all pausar tudo e reportar estado          → fala com todos ao mesmo tempo
/queue mac rodar suite de testes            → enfileira p/ quando o mac estiver livre
/flush mac                                  → despacha a fila
```

## Notas de design

- **Sem dependências pesadas**: apenas `requests`; long polling em vez de webhooks
  (funciona atrás de NAT, sem precisar de domínio/HTTPS).
- **Estado persistente** em `state/registry.json` e `state/queues.json` — o bot pode
  ser reiniciado sem perder agentes/filas/cursores de watch.
- **Segurança**: o bot só aceita mensagens do `TELEGRAM_CHAT_ID` configurado; o relay
  local aceita um token compartilhado opcional (`RELAY_TOKEN`).
- **Devin Local**: o relay é um adapter genérico — ele grava inputs em uma inbox
  (`~/.devin-local-relay/inbox.jsonl`) e serve outputs de uma outbox
  (`~/.devin-local-relay/outbox.jsonl`), permitindo acoplar qualquer processo local
  (Devin CLI, scripts, outro agente) lendo/escrevendo nesses arquivos.
