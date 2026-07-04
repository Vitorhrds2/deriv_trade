# Entry Spot Lag — verificação direta (race T0-já-visto vs T+1)

**Branch:** `main` · **Status:** hipótese REFUTADA (sem race exploitável) · **Ferramenta:** `trading-engine/entry_spot_lag_test.py`

## Veredito (TL;DR)

A regra documentada em `docs/antigravity-brain/hypothesis/implementation_plan.md` ("para
contratos de Ticks, o Entry Spot é o PRÓXIMO tick T+1, nunca o T0 já conhecido") havia sido
inferida apenas por **win rate agregado** (36-38% em `rng_smoothing_exploit.py`) batendo com a
teoria. Nunca tinha sido verificada **tick-a-tick contra o dado bruto da API**. Este teste faz
essa verificação direta: **75/75 trials confirmam a regra sem exceção** — o `entry_spot` nunca
reaproveita o mesmo evento de tick (mesmo `epoch`) já visto via `subscribe_ticks` antes do `buy`.
**Sem race condition exploitável na mecânica de entrada.**

## Hipótese

> Existe uma janela de race onde o tick já conhecido (T0, visto pela subscrição de ticks ANTES
> do `buy` ser enviado) escapa como `entry_spot` oficial de um contrato de 1 tick recém-comprado,
> em vez do tick T+1 (genuinamente futuro) que a regra documentada da corretora prevê?

## Método

1. Subscreve ticks do símbolo (`1HZ10V`), guardando o último tick visto (`valor`, `epoch`,
   tempo local).
2. Para cada trial: registra `T0_visto`, dispara imediatamente `buy_direct` (CALL, 1 tick,
   stake $1, conta DEMO com trava de validação — mesmo padrão de `arb_order_test.py`).
3. Faz *poll* de `proposal_open_contract` até `entry_spot`/`entry_spot_time` aparecerem, e depois
   até `is_sold` para o profit.
4. Compara `entry_spot` retornado contra `T0_visto` por **duas métricas**: `epoch` (identidade
   real do evento de tick) e `valor` (preço cotado).

### Armadilha descoberta e corrigida durante o teste

A primeira versão do script comparava só o **valor** do preço. Em 2/30 trials nessa versão,
`entry_spot` bateu em valor com `T0_visto` — sinalizado como "race" — mas o `epoch` de ambos os
casos era **diferente** (gap de 1-2s). `1HZ10V` tem incrementos pequenos/discretos, então dois
ticks **diferentes no tempo** coincidirem em preço é esperado por acaso, não evidência de reuso
do mesmo evento. Corrigido para comparar `epoch` (identidade real) como critério primário, com
valor como diagnóstico secundário apenas.

## Resultado (75 trials, `1HZ10V`, CALL 1 tick, stake $1)

| Rodada | N | Mesmo epoch (race real) | Valor coincidiu (epoch diferente) | Gap médio |
|---|---|---|---|---|
| Piloto | 5 | 0/5 | 0/5 | 1.8s |
| Run 1 (reanalisado) | 30 | 0/30 | 2/30 (falso positivo) | 1.53s |
| Run 2 (script corrigido) | 40 | 0/40 | 0/40 | 1.48s |
| **Total** | **75** | **0/75** | **2/75** | **~1.6s** |

Gap sempre 1-2 segundos (nunca 0) em **todos** os 75 trials — consistente com tick a ~1Hz e a
regra T+1 aplicada sem exceção.

## Observação lateral (não confirmada, requer teste dedicado)

O *sanity check* de WR/EV (não o objetivo do teste, mas coletado de graça) mostrou, somando as
3 rodadas: **48 wins / 75 trials = 64.0% WR**, IC95% Wilson **[52.7%, 73.9%]** — o limite inferior
fica *marginalmente* acima do breakeven de 92% de payout (52.08%). Isso **não deve ser tratado
como edge real**:

- Todas as compras foram **CALL fixo** (nunca alternado/randomizado) — uma janela curta de
  passeio aleatório pode ter drift ascendente por puro acaso, sem significar viés persistente.
- É uma observação **pós-hoc** (o teste não foi desenhado pra medir isso) — mesmo padrão de
  "viés de múltiplos testes" que `docs/t4_long_horizon_report.md` já alertou.
- O mesmo símbolo já tem um teste **dedicado e maior** que encontrou o resultado oposto:
  `rng_smoothing_exploit.py` (Exhaustion Exploit, 50 trades) deu **exatamente 25W/25L, WR 50.00%**
  — o resultado mais limpo possível de "sem viés direcional".
- IC95% *quase* tocando o breakeven é a assinatura clássica de ruído, não sinal (ver também o
  achado único de T4 em 24 células, que não replicou).

Se quiser investigar essa observação a sério, precisa de um teste dedicado com direção
**randomizada** (coin-flip CALL/PUT, controle nulo explícito) e N bem maior antes de qualquer
conclusão — não decorre deste teste.

## Follow-up decisivo — `tick_direction_bias_test.py` (200 trials randomizados)

Teste dedicado construído especificamente para checar a observação lateral acima: CALL/PUT
sorteado 50/50 **às cegas** (sem gatilho), N=200, mesmo símbolo/duração/stake.

| Grupo | N | WR | IC95% Wilson | EV/trade |
|---|---|---|---|---|
| Combinado | 200 | 52.50% | [45.60%, 59.31%] | +$0.008 |
| Apenas CALL | 93 | 55.91% | [45.79%, 65.57%] | +$0.074 |
| Apenas PUT | 107 | 49.53% | [40.24%, 58.86%] | -$0.049 |

- WR combinado (52.50%) fica **quase exatamente no breakeven** (52.08%) e o IC95% cruza esse
  valor — sem edge estatisticamente distinguível.
- `CALL − PUT` = +$0.1225/trade, IC95% **[-0.1449, +0.3882]** — cruza zero, sem viés
  direcional detectável.

**Confirmado: a observação de 64% WR era ruído de amostra pequena e não-randomizada.** Com
controle adequado (randomização + N maior), o resultado converge para o breakeven, exatamente
como o teste dedicado anterior no mesmo símbolo (`rng_smoothing_exploit.py`, 25W/25L) já sugeria.
Fecha esta observação lateral sem edge.

## Conclusão

**Entry Spot Lag confirmado como regra robusta da corretora, sem race exploitável.** Fecha mais
uma frente de execução/timing no ecossistema — consistente com H1, H3, T4 e a auditoria do
`hft_bot`: nenhuma tese de execução/latência sobrevive ao escrutínio direto.

## Reproduzir

```bash
cd trading-engine
python entry_spot_lag_test.py --symbol 1HZ10V --trials 40 --stake 1
python tick_direction_bias_test.py --symbol 1HZ10V --trials 200 --stake 1
```
