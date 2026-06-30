# Runbook — Coleta PA5 (Polymarket Up/Down × Binance) 48h em AWS

**Objetivo:** rodar o coletor `pa5_collector.py` por **48h** numa VM EC2 (read-only, **PAPER**,
sem capital), varrendo as janelas BTC `up/down` de 5/15min e gravando, por janela, os
paper-trades aligned/anti + o resultado. **Roda mesmo com o seu PC desligado.** Ao fim das
48h: envia **email** (SNS) com o sumário e a instância **se auto-para** (para a cobrança).

> **Sem segredos na VM** para os dados (APIs públicas Gamma + Binance). A VM só usa uma
> **IAM role** mínima (`sns:Publish`) para mandar o email final. Resolver real = **Chainlink**;
> Binance é o sinal proxy → a divergência Binance×Chainlink é risco (registrada nos dados).

> **Custo:** t3.micro ~US$0.01/h → 48h ≈ **US$0.50** + EBS (centavos). Após o auto-stop, só
> EBS até você rodar o teardown.

---

## Pré-requisitos
- `aws configure` já feito (perfil com permissão p/ EC2 + SNS + IAM).
- AWS CLI e `ssh`/`scp` no PATH (Windows 10+ já tem OpenSSH).

## Fluxo (com o PC ligado; depois pode desligar)
A partir de `C:\Users\Usuario\Documents\deriv_trade-polymarket\trading-engine`.

### 1. Provisionar (valida a conta + cria tudo)
```powershell
.\deploy\provision_pa5_aws.ps1 -Email voce@exemplo.com
# opcional: -Region ap-northeast-1 -InstanceType t3.micro
```
- Imprime a **conta AWS no topo — CONFIRME que é a sua** antes de prosseguir.
- Cria key pair, security group (SSH só do seu IP), **SNS topic + assinatura do seu email**,
  IAM role/instance-profile (`sns:Publish`) e a instância. Estado em `~/.aws/pa5-collector.state.json`.
- **AÇÃO MANUAL:** abra o email e clique em **"Confirm subscription"** (senão o email final não chega).

### 2. Subir o coletor (transfere + setup + lança 48h desacoplado)
```powershell
.\deploy\deploy_pa5_aws.ps1                 # default 48h, horizontes 5,15, min_move 8
# ou: .\deploy\deploy_pa5_aws.ps1 48 "5,15" 8
```
O setup roda os selftests + checagem de rede na VM. No fim mostra o PID e as 1ªs linhas do log.

### 3. Confirmar e DESLIGAR o PC
```powershell
$st = Get-Content $env:USERPROFILE\.aws\pa5-collector.state.json | ConvertFrom-Json
ssh -i $st.keyPath ubuntu@$($st.ip) "tail -n 12 ~/te/logs/pa5_collector.out; echo ---; cat ~/te/data/pa5/summary.json"
```
Viu janelas sendo coletadas (`coletando btc-updown-5m-... -> ... trades aligned/anti`)?
**Pode desligar o computador.** A coleta segue na AWS por 48h.

---

## No fim (~48h depois)
- Você recebe um **email** (assunto `PA5 coleta finalizada (rc=0)`) com o sumário consolidado:
  n aligned/anti, win-rate, P&L médio, `aligned-anti`, IC95% e veredito.
- A instância **se auto-parou**. Para baixar os dados crus e destruir tudo:
```powershell
.\deploy\teardown_pa5_aws.ps1
```
Liga a instância (se parada), baixa `~/te/data/pa5/*` para `trading-engine\data\pa5_aws\`, e
**destrói** instância + SG + key pair + SNS topic + IAM role/profile.

---

## Formato dos dados (`data/pa5/windows.jsonl`, 1 linha por janela)
```
slug, question, horizon_min, end, begin_ref, close_px, outcome (Up/Down),
trades[ {tag: aligned|anti, side: Up|Down, ask, binance, move, won, pnl} ],
summary{ aligned{n,wr,wr_ci,pnl_mean,pnl_total}, anti{...}, aligned_minus_anti, diff_ci95, verdict }
```
`summary.json` = consolidado de TODAS as janelas (atualizado a cada janela; resiliente a quedas).

## Como ler o resultado (veredito da tese PA5)
- **`verdict: edge_comprovado`** + `aligned.pnl_mean > 0` → edge PAPER positivo e significativo
  (IC95% de `aligned-anti` acima de zero). **Próximo passo:** medir a divergência Binance×Chainlink
  (basis); só então pensar em executor EIP-712 (fora deste escopo).
- **`cruza_zero`** / `aligned.pnl_mean <= 0` → **sem edge líquido** = mesmo padrão H1/H3
  (sinal real, sub-custo). Tese refutada como estratégia de varejo.

## Notas
- O coletor sobrevive a falhas de janela (try/except por janela) e grava 1 linha por janela.
- Para mudar custo/sensibilidade sem re-subir: edite os args no passo 2 (`--taker-rate`, `--min-move`).
- **Não opera**: nenhuma ordem é assinada (Polymarket exige EIP-712, fora de escopo por decisão de projeto).
- Se a IAM role demorar a propagar, o `run-instances` pode falhar — basta rodar o provision de novo.
- Sanidade local antes de subir: `python pa5_collector.py --selftest` e `python polymarket_lag_probe.py --selftest`.
