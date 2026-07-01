# T2 — Boom/Crash SPIKE_TIMING (memória de spike)

**Branch:** consolidado de `feat/synthetic-anomaly-monitor` → `main` · **Status:** ❌ **REFUTADA**
(replicado 2x, independente) · **Ferramentas:** `trading-engine/boom_timing_test.py`,
`trading-engine/boom_memory_test.py`, `trading-engine/boom_crash_analyzer.py`

## Hipótese

Boom/Crash têm um spike gigante (~30-50x o movimento normal) a cada N ticks em média (N=300/500/600/
900/1000, conforme o símbolo). Pergunta: o intervalo entre spikes é **memoryless** (geométrico/
exponencial puro, "cada tick é um dado sendo jogado de novo") ou tem **memória** (hazard rate cresce
com o tempo desde o último spike, i.e., um spike "atrasado" fica mais provável)? Se houver memória, é
uma vantagem estrutural real e nova: dá pra saber que um spike está "atrasado" e posicionar entrada
(ex.: multiplier) antes dele.

## Método (versão rigorosa, `boom_timing_test.py`)

Corrige dois bugs do coletor original (`boom_crash_analyzer.py`): (1) detecção de spike por
**magnitude calibrada** (`|retorno| > 8x mediana` na direção do índice) em vez de "qualquer tick
positivo" (que conta ruído de drift como spike); (2) paginação com **dedup por epoch** (a versão antiga
reusava a mesma janela e inflava ticks nominais sem dados novos).

Testa em **pool multi-símbolo normalizado** (gap/N por símbolo, já que sob o nulo cada gap/N ~ Exp(1)
independente do N nominal) — 6 símbolos: BOOM300N/500/1000, CRASH300N/500/1000. Quatro testes
estatísticos independentes:

1. **CV** (desvio/média dos gaps) — memoryless espera ≈1.0.
2. **Weibull shape k** via MLE + IC95% bootstrap — k=1 memoryless; k>1 hazard crescente (edge real);
   k<1 clustering.
3. **KS vs. exponencial** — testa se a distribuição empírica rejeita a exponencial teórica.
4. **Sobrevivência condicional** `P(gap>2·mediana | gap>mediana)` — memoryless espera ≈50%.

## Resultado — replicado 2x de forma independente

**Coleta fresca (177 gaps normalizados, 6 símbolos, ticks recentes):**
- CV = 1.046
- Weibull k = **1.000**, IC95% **[0.898, 1.129]**
- KS: D=0.0434 (crit=0.1022) → não rejeita exponencial
- Sobrevivência condicional: 48.9%, IC95%[36.8%, 60.2%]

**Dataset antigo (208 gaps, só BOOM500, janela de tempo diferente):**
- CV = 1.008
- Weibull k = **1.024**, IC95% **[0.935, 1.134]**
- KS: D=0.0461 (crit=0.0943) → não rejeita exponencial
- Sobrevivência condicional: 42.3%, IC95%[32.7%, 55.9%]

Os dois ICs de `k` se sobrepõem quase totalmente e ambos centram em 1.0. A hazard rate por idade
normalizada não mostra tendência monotônica crescente em nenhuma das duas coletas (oscila entre ~12%
e ~40% sem padrão de crescimento com a idade).

## Veredito

**T2 refutada, com replicação independente.** O intervalo entre spikes de Boom/Crash é consistente com
processo **memoryless** (geométrico/exponencial) em todos os 4 testes, nas duas coletas. "Spike
atrasado" é a falácia do apostador aplicada a um processo sem memória — não há sinal de timing
explorável. Mesmo padrão de conclusão dos demais produtos testados nesta rodada (Accumulators, Jump
Indices, Vanillas): a Deriv não deixa estrutura temporal ou de precificação explorável nos produtos
sintéticos testados até agora.

## Como reproduzir

```bash
cd trading-engine
python boom_timing_test.py                                    # coleta fresca, pool multi-simbolo
python boom_timing_test.py --offline boom_distances.txt --offline-n 500   # replica com dado antigo
```
