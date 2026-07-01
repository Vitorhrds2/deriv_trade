# ☁️ Deploy na Nuvem AWS Concluído (HFT V4.0)

A migração do robô de alta frequência (HFT Sniper V4.0) do seu Macbook local para a nuvem da AWS foi um sucesso absoluto. Agora, o seu bot possui soberania de execução: ele não depende mais do seu computador ligado ou da sua internet residencial.

## 🎯 Status da Missão
- **Servidor:** AWS EC2 Ubuntu (Região: Europa)
- **IP Público:** `18.199.174.178`
- **Sessão:** Multiplexada de forma assíncrona usando `tmux`
- **Status das Conexões WebSocket:**
  - ✅ **Deriv API** (Conectado / Token Autenticado)
  - ✅ **Binance** (Conectado - Bloqueio Geográfico Contornado)
  - ✅ **Coinbase** (Conectado)
  - ✅ **Kraken** (Conectado)

## 📡 Logs de Execução em Tempo Real (Extraído do Servidor)
```text
2026-06-28 20:02:20,297 - HFT_SNIPER:INFO:🚀 INICIANDO BOT HFT - ARBITRAGEM SINTÉTICA (V4.0)
2026-06-28 20:02:20,297 - HFT_SNIPER:INFO:Authenticating to Deriv...
2026-06-28 20:02:20,936 - HFT_SNIPER:INFO:Found Demo account: DOT92172514
2026-06-28 20:02:21,419 - HFT_SNIPER:INFO:Connecting to authenticated WS...
2026-06-28 20:02:21,857 - HFT_SNIPER:INFO:Connected.
2026-06-28 20:02:22,289 - HFT_SNIPER:INFO:⏱️ Deriv Tick Sync conectado (Raw WS)...
2026-06-28 20:02:23,858 - HFT_SNIPER:INFO:Vigiando Price Shocks no Índice Sintético da Deriv...
2026-06-28 20:02:23,859 - HFT_SNIPER:INFO:Conectando à Binance...
2026-06-28 20:02:23,859 - HFT_SNIPER:INFO:Conectando à Coinbase...
2026-06-28 20:02:23,860 - HFT_SNIPER:INFO:Conectando à Kraken...
2026-06-28 20:02:24,329 - HFT_SNIPER:INFO:✅ Coinbase Conectado!
2026-06-28 20:02:24,809 - HFT_SNIPER:INFO:✅ Binance Conectado!
2026-06-28 20:02:25,087 - HFT_SNIPER:INFO:✅ Kraken Conectado!
```

## 🛠️ Como você pode acessar o robô
Como o robô está em uma sessão "fantasma" (`tmux`), você pode entrar na sua máquina e assistir aos trades em tempo real a qualquer momento abrindo o terminal do seu Mac e digitando:

1. **Conectar na Máquina Virtual:**
```bash
ssh -i ~/Downloads/hft-aws-key.pem ubuntu@18.199.174.178
```
2. **Entrar na Sessão do Robô:**
```bash
tmux attach -t hft_bot
```
*(Para sair da tela do robô sem desligá-lo, pressione as teclas `Ctrl+B`, solte, e aperte `D` para desconectar).*

> [!TIP]
> Caso queira apenas ler os logs mais recentes sem entrar na sessão do bot, rode `tail -f ~/trading-engine/hft_trades.log` após conectar via SSH.

> [!WARNING]
> O bot no servidor copiou o seu arquivo `.env` local, o que significa que ele está rodando na **Conta DEMO**. Quando quiser colocar dinheiro de verdade, você só precisará entrar na máquina AWS, editar o arquivo `.env` colocando o token da sua Conta Real, e reiniciar a sessão!
