# Deploy AWS — D17 Unlock Short (paper)

Sobe 2 simulacoes paper como servicos systemd numa EC2 (Amazon Linux 2023):

- `d17-sim10k` — equity $10k, sem Discord.
- `d17-sim100` — equity $100, tag `sim100`, com notificacoes Discord.

Ambas usam so a stdlib do Python 3 (paper mode nao precisa de pip nem de keys Binance).

## Instancia (referencia)

- Tipo: `t4g.micro` (ARM64, free-tier eligible). `t4g.nano` NAO e permitido nesta conta (Free Tier restrito).
- AMI: Amazon Linux 2023 arm64.
- Regiao: `ap-northeast-1`.
- Nome/tag: `d17-unlock-short`.
- Key pair: `d17-unlock-short` (PEM guardado localmente em `~/.ssh/d17-unlock-short.pem`, fora do repo).
- Security group: `d17-unlock-short-sg` (SSH 22 apenas do IP do admin).

## Passos

```bash
# 1. copiar codigo + deploy p/ a instancia
scp -i ~/.ssh/d17-unlock-short.pem unlock_short_bot.py token_unlock_scan.py unlock_data.py ec2-user@<IP>:/home/ec2-user/d17/
scp -i ~/.ssh/d17-unlock-short.pem -r deploy ec2-user@<IP>:/home/ec2-user/d17/deploy

# 2. criar o env do webhook NA INSTANCIA (nao vai ao repo)
ssh -i ~/.ssh/d17-unlock-short.pem ec2-user@<IP> \
  'umask 077; echo "DISCORD_WEBHOOK_URL=<webhook>" > /home/ec2-user/d17/sim100.env'

# 3. instalar e iniciar os servicos
ssh -i ~/.ssh/d17-unlock-short.pem ec2-user@<IP> 'bash /home/ec2-user/d17/deploy/setup_remote.sh'
```

## Operacao

```bash
# status / logs
systemctl status d17-sim10k d17-sim100
journalctl -u d17-sim100 -f          # segue notificacoes/erros
# reiniciar / parar
sudo systemctl restart d17-sim100
sudo systemctl stop d17-sim10k
```

Os servicos tem `Restart=always` e `enable`, logo sobem sozinhos apos reboot/crash.
Estado persistido em `/home/ec2-user/d17/unlock_short_state*.json`.

## Seguranca

- `sim100.env` (webhook) fica so na instancia, `chmod 600`, fora do git.
- Paper mode: precos reais, sem ordens, sem keys, sem dinheiro. `--live` permanece travado.
- SSH liberado so para o IP do admin; se o IP mudar, atualizar o ingress do SG.
