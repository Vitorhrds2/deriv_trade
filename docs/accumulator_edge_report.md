# Accumulators (ACCU) — primeira hipótese nova do Mega Brain 2.0

**Branch:** `main` · **Status:** ❌ **SEM EDGE** (após cross-validação; falso positivo capturado) · **Ferramentas:** `trading-engine/accumulator_edge_scan.py`, `trading-engine/accumulator_validate.py`, `trading-engine/probe_accumulator.py`

## Por que Accumulators

Produto **nunca testado** neste ecossistema (ausente de `algotrade_knowledge_hub.md` e de todos os
scripts anteriores). Mecânica distinta de tudo que já foi refutado: a cada tick, o contrato sobrevive se
o preço ficar dentro de `± tick_size_barrier%` do tick anterior; sobrevivendo, o stake cresce
`(1+growth_rate)` por tick (composto); se sair da faixa, perde tudo (knockout). `growth_rate` é escolhido
pelo trader (1-5%); a largura da barreira é calculada pela Deriv por símbolo/growth_rate.

## Método (2 medidas independentes, mesma filosofia do T3)

1. **`ticks_stayed_in`** — a própria API (`proposal.contract_details`) devolve uma amostra retrospectiva
   real (~100 instâncias) de quantos ticks contratos passados sobreviveram, por símbolo+growth_rate. Uso
   direto, sem precisar coletar histórico próprio.
2. **Validação independente** — 5.000 ticks reais de `1HZ100V` via `ticks_history`, medindo diretamente
   `P(sobreviver 1 tick) = P(|retorno| ≤ tick_size_barrier)`, comparado ao valor "justo" exigido para
   EV=0 (`1/(1+growth_rate)`, sem margem).

## Resultado 1 — scan inicial (`ticks_stayed_in`, 630 células: 10 símbolos × 5 growth rates × 16 N-alvo)

Achou um cluster aparente em `1HZ100V, growth_rate=0.03, N∈{5,8,10}`: `EV_lo` positivo (até +$0.031),
**e persistiu numa 2ª chamada independente** (não sumiu como o falso positivo clássico). Sinal
mecanicamente plausível: `growth_rate=0.02` e `0.04` no mesmo símbolo também mostravam EV **pontual**
positivo em vários N (só não cruzavam o IC95%).

## Resultado 2 — validação com histórico real (decisivo)

Medindo diretamente em 5.000 ticks reais de `1HZ100V`, a sobrevivência de 1 tick é **sistematicamente
MENOR** que o valor justo, em **todos os 5 growth rates**:

| growth_rate | Barreira/tick | P(sobrevive 1 tick) empírico | Necessário p/ EV=0 | Diferença |
|---|---|---|---|---|
| 0.01 | 0.04331% | 98.400% (IC95%[98.01%,98.71%]) | 99.010% | **-0.61pp** |
| 0.02 | 0.04048% | 97.840% (IC95%[97.40%,98.21%]) | 98.039% | **-0.20pp** |
| 0.03 | 0.03797% | 96.979% (IC95%[96.47%,97.42%]) | 97.087% | **-0.11pp** |
| 0.04 | 0.03612% | 95.939% (IC95%[95.36%,96.45%]) | 96.154% | **-0.21pp** |
| 0.05 | 0.03438% | 94.759% (IC95%[94.11%,95.34%]) | 95.238% | **-0.48pp** |

Em **todos** os casos o IC95% fica **abaixo** do valor justo — margem da casa presente e mensurável, na
direção oposta ao "candidato" do Resultado 1. Propagando para N ticks (mesmo assumindo i.i.d., leitura
generosa), `EV` e `EV_lo` são **negativos em toda combinação de growth_rate × N testada** (5 taxas × 7
horizontes = 35 células, ver `accumulator_validate.py`).

## Veredito

**O cluster do Resultado 1 era um falso positivo de amostra pequena/correlacionada** (mesmos ~100
episódios reciclados entre N=5/8/10 — não são 3 confirmações independentes, é 1 sinal correlacionado). A
validação com 5.000 ticks reais e medição direta (não retrospectiva) **refuta o edge em toda a grade**.
**Accumulators entram para a lista de "sem edge"**, no mesmo padrão de digits, touch/no-touch, rise/fall:
margem da casa embutida na largura da barreira, calibrada por símbolo/growth_rate.

Isso é uma boa demonstração do motivo pelo qual o gate de credibilidade (2ª fonte independente antes de
declarar edge) é inegociável — o mesmo tipo de artefato que o T3 pegou (drift de amostra pequena) quase
se repetiu aqui, e foi pego a tempo.

## Como reproduzir

```bash
cd trading-engine
python probe_accumulator.py         # inspeciona a resposta bruta da API (contract_details)
python accumulator_edge_scan.py     # scan inicial via ticks_stayed_in (10 simbolos x 5 growth rates)
python accumulator_validate.py      # validacao decisiva com 5000 ticks reais de 1HZ100V
```

## Próximos passos

- Rodar `accumulator_validate.py` nos outros 9 símbolos (script já genérico, só trocar `SYMBOL`) para
  fechar a grade completa com o método decisivo, não só `1HZ100V`.
- Não prosseguir com capital nesta hipótese.
