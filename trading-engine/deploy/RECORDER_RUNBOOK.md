# Runbook — Gravador de ticks reais (Binance) 24h em AWS Tóquio

**Objetivo:** coletar 24h de ticks reais da Binance (`@aggTrade`) numa VM em
`ap-northeast-1` (co-locada com a Binance → latência ~ms), **rodando mesmo com o seu
PC desligado**. Stream público → **sem token/segredo** na VM.

> **Por que funciona com o PC off:** o gravador sobe com `nohup` **na instância EC2**.
> Seu PC só precisa estar ligado para *provisionar* e *subir*. Depois disso pode desligar:
> o processo continua na nuvem. Ao fim das 24h o gravador encerra e a VM **se auto-para**
> (stop), parando a cobrança de compute e preservando os dados no disco (EBS).

> **Custo:** t3.micro Tóquio ~US$0.017/h → 24h ≈ **US$0.41**. Após o auto-stop, só EBS
> (centavos/mês) até você rodar o teardown.

---

## Fluxo (3 passos com o PC ligado; depois pode desligar)

Tudo a partir de `C:\Users\Usuario\Documents\deriv_trade-h1\trading-engine`.

### 1. Provisionar a VM
```powershell
.\deploy\provision_recorder_tokyo.ps1
```
Cria key pair + security group (SSH só do seu IP) + instância. Salva o estado em
`~/.aws/tokyo-recorder.state.json`. Imprime a conta AWS no topo — **confira que é a sua**.

### 2. Subir o gravador (transfere + instala + lança desacoplado)
```powershell
.\deploy\deploy_recorder_tokyo.ps1                  # default BTCUSDT,ETHUSDT por 24h
# ou customizado:
.\deploy\deploy_recorder_tokyo.ps1 "BTCUSDT,ETHUSDT,SOLUSDT" 86400
```
No fim mostra o PID e as primeiras linhas do log (`[ws] conectado`, `[stats] ...`).

### 3. Confirmar que está gravando (opcional) e DESLIGAR o PC
```powershell
$st = Get-Content $env:USERPROFILE\.aws\tokyo-recorder.state.json | ConvertFrom-Json
ssh -i $st.keyPath ubuntu@$($st.ip) "tail -n 5 ~/te/logs/recorder.out; ls -la ~/te/data/binance_ticks/"
```
Viu `[stats] ... ticks=...` subindo? **Pode desligar o computador.** A coleta segue na AWS.

---

## Depois (24h depois, com o PC ligado de novo): baixar dados + destruir
```powershell
.\deploy\teardown_recorder_tokyo.ps1
```
Liga a instância se estiver parada, baixa `~/te/data/binance_ticks/*` para
`trading-engine\data\binance_ticks_tokyo\`, e **destrói** instância + SG + key pair.

---

## Formato dos dados
1 CSV por símbolo, **rotação horária**: `btcusdt-aggtrade-YYYYMMDD-HH.csv`.
Colunas:
```
recv_ns,event_ms,trade_ms,agg_id,price,qty,first_id,last_id,is_buyer_maker
```
`recv_ns` = timestamp local (ns) na recepção — **não existe** nos dumps históricos da
Binance; co-locado em Tóquio fica ~1-3ms do `event_ms`, habilitando estudo de latência.

## Notas
- O gravador tem **auto-reconnect com backoff** + ping de cliente → sobrevive a quedas
  de WS ao longo de 24h.
- Para mudar símbolos/duração sem re-subir: edite os args no passo 2.
- Se quiser que NÃO se auto-pare (manter coletando indefinidamente), passe runtime `0`:
  `.\deploy\deploy_recorder_tokyo.ps1 "BTCUSDT,ETHUSDT" 0` (aí o teardown é manual).
