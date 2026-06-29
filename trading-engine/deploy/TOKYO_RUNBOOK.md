# Runbook — Teste de arbitragem de latência CO-LOCADO (AWS Tóquio)

**Objetivo:** rodar `arb_order_test.py --live` de uma VM em **AWS `ap-northeast-1`**
(co-locada com a Binance) para ver se reagir ~270ms mais rápido (sinal ~1ms em vez de
~275ms de casa) captura uma janela "stale" da Deriv que o teste de casa (~450ms) não viu.

**Veredito que buscamos:** `aligned` (P&L médio) **> 0**, OU o IC95% de `aligned-anti`
claramente **acima** do de casa (`+0.0041`). Senão → H3 morto mesmo co-locado.

> Custo: t3.micro on-demand em Tóquio ~US$0.017/h → o teste inteiro custa **~2 centavos**.
> Tempo: ~15-20 min.

---

## 0. Pré-requisitos (no seu PC Windows)
- **AWS CLI** instalada e configurada (`aws configure`).
- **OpenSSH** (já vem no Windows 10/11: `ssh`, `scp`).
- Seu **`.env`** com `DERIV_APP_ID` e `DERIV_API_TOKEN` (em
  `C:\Users\Usuario\Documents\Deriv_trade\trading-engine\.env`).
- **SEGURANÇA:** esse token alcança a conta **REAL** também. Recomendo **gerar um token
  novo** em https://app.deriv.com/account/api-token só para este teste e **revogá-lo**
  ao terminar. O harness só toca a demo (trava por `account_type`), mas minimize exposição.

---

## 1. Provisionar a VM (PowerShell, no seu PC)

```powershell
$REGION = "ap-northeast-1"
# AMI Ubuntu 22.04 mais recente (via SSM)
$AMI = (aws ssm get-parameters --region $REGION --names /aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id --query "Parameters[0].Value" --output text)
# Par de chaves
aws ec2 create-key-pair --region $REGION --key-name tokyo-arb --query KeyMaterial --output text > tokyo-arb.pem
icacls tokyo-arb.pem /inheritance:r /grant:r "$($env:USERNAME):R"   # corrige permissao p/ o ssh aceitar
# Security group: SSH só do seu IP
$MYIP = (curl -s https://checkip.amazonaws.com).Trim()
$SG = (aws ec2 create-security-group --region $REGION --group-name tokyo-arb-sg --description "H3 arb test" --query GroupId --output text)
aws ec2 authorize-security-group-ingress --region $REGION --group-id $SG --protocol tcp --port 22 --cidr "$MYIP/32"
# Subir a instancia
$IID = (aws ec2 run-instances --region $REGION --image-id $AMI --instance-type t3.micro --key-name tokyo-arb --security-group-ids $SG --query "Instances[0].InstanceId" --output text)
aws ec2 wait instance-running --region $REGION --instance-ids $IID
$IP = (aws ec2 describe-instances --region $REGION --instance-ids $IID --query "Reservations[0].Instances[0].PublicIpAddress" --output text)
"Instancia $IID  |  IP $IP"
```

---

## 2. Enviar os arquivos + .env (PowerShell, no seu PC)

Rode a partir de `C:\Users\Usuario\Documents\deriv_trade-h1\trading-engine`:

```powershell
ssh -i tokyo-arb.pem -o StrictHostKeyChecking=no ubuntu@$IP "mkdir -p ~/te/deploy ~/te/logs"
scp -i tokyo-arb.pem deploy/tokyo_setup.sh deploy/run_tokyo_test.sh ubuntu@${IP}:~/te/deploy/
scp -i tokyo-arb.pem deriv_client.py arb_order_test.py deriv_rtt_probe.py account_check.py requirements.txt ubuntu@${IP}:~/te/
scp -i tokyo-arb.pem C:\Users\Usuario\Documents\Deriv_trade\trading-engine\.env ubuntu@${IP}:~/te/.env
```

> O `.env` precisa ficar em `~/te/.env` (mesma pasta dos `.py`) — os scripts carregam de lá.

---

## 3. Rodar o teste (SSH na VM)

```powershell
ssh -i tokyo-arb.pem ubuntu@$IP
```
Já dentro da VM:
```bash
cd ~/te
bash deploy/tokyo_setup.sh        # instala deps + confirma RTT Binance ~1-5ms
bash deploy/run_tokyo_test.sh     # RTT real + conta demo + 60 ordens --live
```

**Cheque no passo A** (`deriv_rtt_probe.py`): o sinal Binance de Tóquio deve cair p/
~1ms e o leg de ordem Deriv (`proposal`) deve aparecer — compare com os ~178ms de casa.

---

## 4. Ler o veredito

No fim de `logs/tokyo_arb_live.out`:
- **`aligned` P&L médio > 0** → arb LUCRATIVO destravado pela latência (confirmar com +amostra).
- **IC95% de `aligned-anti` acima de 0 e MAIOR que o de casa (`+0.0041`)** → a janela
  stale existe e foi capturada de Tóquio (mesmo que ainda sub-custo).
- **`aligned` ~ −0.026 e IC cruza zero** → **H3 morto mesmo co-locado** (fill reprecifica
  fresco abaixo de ~180ms). Encerra a hipótese de vez.

Baixar os logs p/ casa (no SEU PC):
```powershell
scp -i tokyo-arb.pem ubuntu@${IP}:"~/te/logs/tokyo_*.out" .
```

---

## 5. ENCERRAR (controle de custo + segurança)

```powershell
aws ec2 terminate-instances --region $REGION --instance-ids $IID
aws ec2 wait instance-terminated --region $REGION --instance-ids $IID
aws ec2 delete-security-group --region $REGION --group-id $SG
aws ec2 delete-key-pair --region $REGION --key-name tokyo-arb
Remove-Item tokyo-arb.pem
```
- **Revogue o token** da Deriv usado no teste (se gerou um dedicado).

---

## Ajustes finos (se quiser uma 2ª passada)
- Reagir ainda mais rápido: `--lookback-ms 120 --hold-s 1.0 --cooldown-s 0.8`.
- Mais amostra/poder: `--max-trades 120 --max-seconds 1200`.
- Mercado mais volátil (mais gatilhos por minuto): rodar na abertura US/EU.

## Alternativa ao scp: git clone na VM
Se preferir clonar o repo (precisa de PAT/somente-leitura, repo é privado):
```bash
git clone https://<SEU_PAT>@github.com/Vitorhrds2/deriv_trade.git
cd deriv_trade && git checkout feat/h1-momentum && cd trading-engine
# depois suba só o .env via scp e rode os scripts de deploy/
```
