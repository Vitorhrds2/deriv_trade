# Jump Indices (JD10/25/50/75/100) — SPIKE_TIMING e viés de direção

**Branch:** `main` · **Status:** ❌ **SEM EDGE** (2 sinais candidatos, ambos refutados por amostra maior) · **Ferramentas:** `trading-engine/jump_index_spike_scan.py`

## Hipótese

Documentação pública da Deriv: Jump Indices "pulam" em média a cada ~20min, direção 50/50, salto
~30x o movimento normal. Testável: (1) a direção é **realmente** 50/50? (2) o processo de saltos é
**memoryless** (geométrico/exponencial puro) ou existe uma estrutura de "temporizador" (hazard rate
crescente com o tempo desde o último salto) — o que seria uma vantagem estrutural real, nunca antes
testada neste ecossistema (todos os testes anteriores assumiam memorylessness em índices de
volatilidade pura, nunca em Jump Indices).

## Método

Detecção de saltos via `|retorno tick-a-tick| > 10x mediana` do movimento normal, sobre histórico real
via `ticks_history` (paginado). Para cada símbolo: viés de direção (Wilson CI vs 50%), coeficiente de
variação dos gaps entre saltos (CV≈1 esperado se memoryless), e hazard rate por faixa de "ticks desde o
último salto" (deveria ser ~constante se memoryless).

## Resultado 1 — amostra inicial (20.000 ticks/símbolo, ~5.6h, N=12-19 saltos)

`JD50` acusou um viés de direção aparentemente forte: **13/14 saltos UP (92.9%, IC95%[68.5%,98.7%])** —
sob H0 50/50, P(≥13 de 14) ≈ 0.09%, o que pareceria significativo isoladamente.

## Resultado 2 — validação com amostra maior (decisivo)

Re-testando `JD50` sozinho com 80.000 ticks (22.2h, N=50 saltos): **25/50 UP = exatamente 50.0%**
(IC95%[36.6%,63.4%]). **O viés desapareceu por completo** — era um fluke de amostra pequena (N=14),
o mesmo padrão do falso positivo já visto em Accumulators.

Rodando todos os 5 símbolos com 60.000 ticks (N=37-49 saltos cada), nenhum mostra viés de direção fora
do IC95%:

| Símbolo | N saltos | % UP | Gap médio | CV (gaps) |
|---|---|---|---|---|
| JD10 | 49 | 49.0% | 20.4min | 0.92 |
| JD25 | 37 | 51.4% | 26.9min | 0.84 |
| JD50 | 41 | 56.1% | 24.0min | 0.93 |
| JD75 | 47 | 44.7% | 21.3min | 1.18 |
| JD100 | 47 | 53.2% | 21.5min | 0.87 |

Todos os CV ficam entre 0.84-1.18 (compatível com processo memoryless, CV teórico=1). Nenhum símbolo
mostra hazard rate crescente com o tempo desde o último salto (todas as faixas testadas ficam na mesma
ordem de grandeza, sem tendência) — **sem evidência de "temporizador"**.

## Veredito

**Direção 50/50 confirmada** (como documentado) e **timing memoryless confirmado** (sem estrutura de
"salto atrasado" explorável). O único sinal candidato (`JD50` 92.9% UP) foi um **falso positivo de
amostra pequena**, refutado ao quadruplicar o N — mesma disciplina que já havia pego o falso positivo em
Accumulators. Jump Indices entram para a lista de "sem edge".

## Como reproduzir

```bash
cd trading-engine
python jump_index_spike_scan.py                      # todos os 5 simbolos, 20k ticks (rapido)
python jump_index_spike_scan.py JD50 80000            # 1 simbolo, amostra grande (validacao)
python jump_index_spike_scan.py JD10,JD25,JD50,JD75,JD100 60000   # grade completa, amostra media-alta
```

## Nota

`Step Index` (`stpRNG`, `stpRNG2-5`) é outra família de produto nunca testada, descoberta durante esta
investigação (`active_symbols`, submarket `step_index`). Mecânica: passo fixo por tick, 50/50, sem
"jump" — candidato natural para a próxima rodada se quiser esgotar todas as famílias de produto restantes.
