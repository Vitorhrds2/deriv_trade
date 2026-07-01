# Vanilla Options (VANILLALONGCALL/PUT) — mispricing vs. valor justo

**Branch:** `main` · **Status:** ❌ **SEM EDGE** · **Ferramentas:** `trading-engine/probe_vanilla.py`,
`trading-engine/vanilla_edge_scan.py`

## Hipótese

Vanillas são o único produto no ecossistema com payoff **convexo real** (não binário/barreira fixa):
payout = `payout_per_point * max(0, final - strike)` (CALL) ou `max(0, strike - final)` (PUT). Isso abre
espaço para um tipo de teste nunca feito aqui — mispricing de opção vs. valor justo teórico, análogo a
comparar IV implícita vs. IV realizada.

## Mecânica confirmada via probe (`probe_vanilla.py`)

- `ask_price` (custo) é sempre exatamente igual ao `stake` pedido (ex.: $10), **para qualquer strike**.
- O que varia por strike/duração é `payout_per_point` (`display_number_of_contracts`): mais alto para
  strikes OTM (mais alavancagem por dólar), mais baixo para ITM.
- 5 strikes fixos por duração (`barrier_choices`), simétricos em torno do spot.

## Método

Mesma filosofia do T3 (`t3_exotic_value_report.md`): Monte Carlo **driftless** via bootstrap de retornos
reais tick-a-tick de `1HZ100V` (demeaned para forçar martingale, premissa já validada empiricamente nos
sintéticos). Para cada strike/duração/tipo, simula 20.000 caminhos somando N retornos reais amostrados
com reposição, calcula o payoff médio simulado e seu IC95% via bootstrap, compara contra o stake pago.

`EV = payout_médio_simulado / stake - 1`. Testado em 2 durações (15m, 60m) × 5 strikes × {CALL, PUT}.

## Resultado

17 de 20 células completadas (3 perdidas por instabilidade da conexão WS de demo, que cai
sistematicamente a cada ~15-20 requests na mesma sessão — não é uma limitação do método, apenas do
ambiente de teste). Todas as 17 células, sem exceção:

| Duração | Tipo | Barrier | Strike vs Spot | EV | IC95% |
|---|---|---|---|---|---|
| 15m | CALL | +5.60 (OTM) | strike>spot | -0.1675 | [-0.2153,-0.1183] |
| 15m | CALL | +2.90/+3.00 | OTM | -0.1318 a -0.1424 | sempre <0 |
| 15m | CALL | +0.00 (ATM) | — | -0.0858 / -0.0499 | sempre <0 |
| 15m | CALL | -2.90 a -5.80 (ITM) | strike<spot | -0.0285 a -0.0416 | sempre <0 |
| 15m | PUT | +5.60 a +3.00 (ITM p/ PUT) | — | -0.0416 a -0.0700 | sempre <0 |
| 15m | PUT | +0.00 (ATM) | — | -0.0876 | [-0.1062,-0.0699] |
| 15m | PUT | -2.90 / -5.50 (OTM p/ PUT) | — | -0.1356 / -0.1948 | sempre <0 |
| 60m | CALL | +11.20 → -5.80 | OTM→ITM | -0.1306 → -0.0293 | sempre <0 |

**EV médio geral: -0.0898** (min=-0.1948, max=-0.0285). **Nenhuma célula teve IC95% cruzando zero.**

A estrutura de margem é **monotônica e coerente com precificação de opções padrão**: quanto mais OTM o
strike, maior a margem relativa cobrada (mais caro underhedge/tail risk pro market maker); quanto mais
ITM (próximo do valor intrínseco), menor a margem. Esse é exatamente o padrão esperado de um book bem
precificado — o oposto de uma assinatura de mispricing explorável.

## Veredito

**Sem edge.** A Deriv precifica Vanillas de forma consistente com o valor justo (driftless, vol real)
mais uma margem de casa que aumenta com o grau de OTM — sem inversões, sem strike/duração fora do
padrão. Refuta a hipótese de mispricing.

## Nota operacional

O WebSocket de demo da Deriv encerra a conexão de forma consistente após ~15-20 requests seguidos na
mesma sessão (não é aleatório — reproduzido de forma idêntica em múltiplas execuções). `deriv_client.py`
trata isso com `sys.exit(1)` (comportamento propositalmente agressivo para os bots ao vivo, que rodam
sob supervisor). Scripts de análise (`vanilla_edge_scan.py`) agora implementam retry com reconexão e
estado preservado (retomam de onde pararam) para lidar com isso sem depender de mudar esse
comportamento core.

## Como reproduzir

```bash
cd trading-engine
python probe_vanilla.py          # inspeciona campos brutos da API
python vanilla_edge_scan.py      # scan completo (retry automatico embutido)
```
