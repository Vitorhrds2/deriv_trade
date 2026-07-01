# Auditoria Retroativa — hft_arbitrage_bot (V4.0 → V6.2 Ultra-Momentum)

**Branch:** `main` · **Status:** ⚠️ **PROVISORIAMENTE REFUTADO** (consistente com H3) · **Ferramentas:** `trading-engine/audit_hft_trades.py`, `trading-engine/stats_utils.py`

## Por que esta auditoria

O `hft_bot` (índice sintético 3-exchange, `docs/antigravity-brain/proud-borg/hft_index_cracked.md`) era o
**único bot com "validação" registrada** no ecossistema, mas nunca passou pelo mesmo crivo estatístico
rigoroso (Wilson CI + bootstrap CI + comparação com controle nulo) que reprovou H1, H3, T4 e o Oráculo —
foi calibrado manualmente (V4.0 → V5.0 → V5.1 → V6.0 → V6.1 → V6.2), trocando parâmetros a cada rodada de
poucas trades. Esta auditoria aplica o mesmo padrão às trades REAIS (conta demo) já executadas.

## Método

Consolidação e deduplicação (por `contract_id`) de todos os `hft_trades*.log` existentes (locais +
puxados ao vivo da AWS via SSH), com parsing de cada evento `GATILHO ACIONADO → ORDEM EXECUTADA →
TRADE ENCERRADO`. Como o robô nunca testou uma direção "anti" (só entra na direção do choque), não existe
um grupo de controle nulo explícito nos dados — diferente de H3. O veredito aqui se apoia no Wilson/bootstrap
CI do próprio resultado observado.

**Caveat de rotulagem descoberto:** o banner de versão só é reimpresso quando o *processo* reinicia. Entre
06-30 e 07-01 os parâmetros do código foram atualizados (`threshold` 50→45) sem um restart imediato, então
várias trades genuinamente V6.2 ficaram com o banner antigo "V6.0 Momentum Rider" no log. Isolamos essas
trades pelo único jeito confiável: `|salto| < 50` só é fisicamente possível com `threshold=45` (prova
empírica de V6.2 ativo), e usamos o timestamp da primeira ocorrência como corte.

## Resultado — todas as versões (N=40, real, conta demo)

| Grupo | N | WR | IC95% Wilson | EV/trade | IC95% bootstrap | PnL total |
|---|---|---|---|---|---|---|
| V4.0 (latência pura) | 9 | 11.11% | [1.99%, 43.50%] | -$3.13 | [-$5.06, -$1.24] | -$28.15 |
| V5.0 (reversão) | 3 | 66.67% | [20.77%, 93.85%] | -$0.24 | [-$2.28, +$1.46] | -$0.71 |
| V5.1 Hotfix (reversão) | 5 | **0.00%** | [0.00%, 43.45%] | -$10.00 exato | [-$10.00, -$10.00] | -$50.00 |
| V6.0 Momentum Rider | 23 | 26.09% | [12.55%, 46.47%] | -$1.82 | [-$4.29, +$0.89] | -$41.80 |
| **Todas combinadas** | **40** | **22.50%** | **[12.32%, 37.50%]** | **-$3.02** | **[-$4.70, -$1.18]** | **-$120.66** |
| **V6.2-equivalente por parâmetro** (threshold=45, desde 2026-06-30 22:12) | **10** | **10.00%** | **[1.79%, 40.42%]** | **-$3.07** | **[-$5.63, +$0.01]** | **-$30.73** |

## Leitura do resultado

- **A amostra combinada (N=40) tem EV/trade estatisticamente negativo**: o IC95% bootstrap `[-$4.70, -$1.18]`
  **não cruza zero**. Isso by si só já derruba a alegação de "validado com ressalvas" — os dados reais
  acumulados até agora mostram perda, não neutralidade nem lucro.
- **A configuração mais atual (V6.2, N=10) é a PIOR de todas**: WR 10%, apenas 1 vitória em 10 tiros. O
  IC95% do EV/trade `[-$5.63, +$0.01]` quase não toca zero — não é 100% conclusivo com N=10, mas está no
  limiar da significância e o ponto central é fortemente negativo.
- **V5.1 (0% WR, -$10.00 exato em todas as 5 trades)** é um padrão suspeito de bug técnico (perda de 100%
  do stake toda vez, "TRADE ENCERRADO AUTOMATICAMENTE") mais do que uma leitura pura da tese de reversão —
  mas mesmo excluindo esse grupo, o quadro geral não muda de sinal.

## Reconciliação com H3 (achado não documentado antes desta sessão)

Dois documentos do lineage `proud-borg` se contradiziam sem nunca terem sido reconciliados:

- `hft_dossier_executivo.md`: perseguir saltos da Binance sozinha é inviável (Deriv amortece via índice agregado).
- `hft_index_cracked.md`: "quebrou" a fórmula do índice (Binance 38.74% + Coinbase 53.38% + Kraken 2.66% +
  $3152.82, R²=0.928) — o que motivou o V6.0-V6.2 (gatilho pelo índice ponderado, não Binance pura).

Só que o relatório **H3** (`origin/feat/h1-momentum`, testado **co-locado em AWS Tóquio**) mostrou que o
gargalo real não é a qualidade do gatilho — é que **a perna de execução da ordem na Deriv leva ~180-220ms
independente de localização** (ela fica atrás de Cloudflare) e a Deriv **sempre reprecifica antes da ordem
chegar**. Esse problema é **agnóstico ao sinal**: trocar Binance-pura pelo índice ponderado de 3 exchanges
não resolve o gargalo que matou H3. **Os números desta auditoria (10% WR na config mais nova) são
exatamente o que H3 previu que aconteceria.**

## Veredito

**hft_bot deixa de ser tratado como "a única aposta viva do ecossistema"** e passa a ser tratado com o
mesmo rigor cético aplicado a H1/H3/T4/Oráculo: os dados reais acumulados (demo) são consistentes com
**EV negativo**, e a versão mais recente é a pior da série. Não há evidência, nesta auditoria, que justifique
alocar capital real a esta estratégia.

## Recomendação

1. **Nenhum capital real nesta estratégia** (já estava em demo — manter assim).
2. **Não investir mais engenharia tentando "salvar" o V6.2** com novos ajustes manuais de threshold/TP/SL —
   isso repetiria o padrão que já gerou 6 versões sem nunca ter sido testado com rigor. Se quiser mais dados
   antes de encerrar de vez, o bot pode seguir rodando em demo (ver operação abaixo) apenas para engordar o N.
3. **Redirecionar o esforço do Mega Brain 2.0 para hipóteses genuinamente novas** (Fase 2) em produtos que
   não tenham a mesma barreira estrutural de latência de ordem (ver `docs/mega_brain_2_new_hypotheses.md`).

## Nota operacional

O bot estava **parado na AWS** no momento desta auditoria (última sessão morreu às 2026-07-01 14:55:11
GMT-3 por queda de WebSocket, sem systemd/supervisor para reiniciar — gap de resiliência real). Se for
mantido rodando apenas para acumular mais N, precisa de um serviço systemd com auto-restart (o mesmo padrão
já usado em `synthetic_anomaly_monitor.py`), não apenas uma sessão `tmux` manual.

## Addendum (2026-07-01, pós-auditoria) — Shadow A/B ativado ao vivo

Implementado o controle nulo explícito recomendado acima: `hft_arbitrage_bot.py` agora sorteia
50/50 entre `ALIGNED` (segue o choque, comportamento histórico) e `ANTI` (contra o choque) a cada
gatilho, logando o grupo (`SHADOW_AB_TESTING=True`, `SHADOW_AB_ANTI_PROB=0.5`). De quebra, corrigido
um bug real encontrado durante a implementação: `execute_trade` reatribuía `direction` de `UP/DOWN`
para `MULTUP/MULTDOWN` **antes** do log do gatilho, o que quebraria o parsing de `audit_hft_trades.py`
em qualquer trade nova (as históricas foram geradas por uma versão anterior do código que ainda
logava `UP/DOWN`). `audit_hft_trades.py` ganhou uma seção nova (`SHADOW A/B — ALIGNED vs ANTI`) que
separa os grupos e compara EV/trade com `bootstrap_diff_ci`: IC cruzando zero confirma o problema
estrutural de latência (H3); IC não cruzando zero indicaria sinal direcional real (a favor ou contra
o momentum, dependendo do sinal).

Deploy: `hft_arbitrage_bot.py` enviado via `scp` para `/home/ubuntu/trading-engine/` (AWS
`18.199.174.178`, backup salvo como `hft_arbitrage_bot.py.bak_20260701_180505`). O bot estava
**parado** (última sessão morreu 2026-07-01 14:55 por queda de WebSocket, confirmando o gap de
resiliência já anotado na Nota Operacional) — sessão `tmux hft_bot` recriada com um wrapper de
auto-restart (`while true; do .venv/bin/python3 hft_arbitrage_bot.py; sleep 5; done`) para não
depender de reinício manual e garantir acúmulo contínuo de N em ambos os grupos. Confirmado online
às 18:07 GMT-3, autenticado na conta demo, conectado a Deriv/Binance/Coinbase/Kraken sem erros.

**Amostra ainda insuficiente para veredito** (0 trades ANTI até o momento do deploy — o sinal é raro,
restrito ao horário de ouro). Rodar `python audit_hft_trades.py` periodicamente para acompanhar o N
acumulado em cada grupo; ver seção `SHADOW A/B` da saída.

## Reproduzir

```bash
cd trading-engine
python audit_hft_trades.py
```
