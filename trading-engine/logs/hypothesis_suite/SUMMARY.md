# Mega Brain — Hypothesis Suite Summary

## boom_crash — T2: Boom/Crash SPIKE_TIMING

**Status:** OK (exit=0) (127s)

```
  KS vs exponencial: D=0.0387  crit(0.05)~0.0882  -> NAO rejeita exp (aprox; Lilliefors seria + rigoroso)
  P(gap>2*mediana | gap>mediana) = 49.6%  IC95% [40.3%, 59.7%]  (memoryless ~50%)

  hazard por idade (normalizada):
    [0.00,0.30) risco=  238 ev=  53 h=22.27%  ###########
    [0.30,0.60) risco=  185 ev=  53 h=28.65%  ##############
    [0.60,0.90) risco=  132 ev=  39 h=29.55%  ###############
    [0.90,1.20) risco=   93 ev=  24 h=25.81%  #############
    [1.20,1.50) risco=   69 ev=  14 h=20.29%  ##########
    [1.50,1.80) risco=   55 ev=  11 h=20.00%  ##########
    [1.80,2.10) risco=   44 ev=   9 h=20.45%  ##########
    [2.10,2.39) risco=   35 ev=   9 h=25.71%  #############
    [2.39,2.69) risco=   26 ev=   7 h=26.92%  #############
    [2.69,2.99) risco=   19 ev=   7 h=36.84%  ##################

  ----------------------------------------------------------------------
  VEREDITO: MEMORYLESS nao rejeitado (k=1 dentro do IC). Sem edge de timing: P(spike) ~ taxa base independ. da idade. => T2 REFUTADA.
==========================================================================
```

## accumulator — Fase 2: Accumulators edge scan

**Status:** OK (exit=0) (12s)

```
  N=  5 ticks | sobreviveram  80/100 ( 80.0%, IC95%[ 71.1%, 86.7%]) | payout= 1.276x | EV=$+0.0210 | EV_lo=$-0.0923
  N=  8 ticks | sobreviveram  73/100 ( 73.0%, IC95%[ 63.6%, 80.7%]) | payout= 1.477x | EV=$+0.0785 | EV_lo=$-0.0608
  N= 10 ticks | sobreviveram  63/100 ( 63.0%, IC95%[ 53.2%, 71.8%]) | payout= 1.629x | EV=$+0.0262 | EV_lo=$-0.1331
  N= 15 ticks | sobreviveram  53/100 ( 53.0%, IC95%[ 43.3%, 62.5%]) | payout= 2.079x | EV=$+0.1018 | EV_lo=$-0.1001
  N= 20 ticks | sobreviveram  40/100 ( 40.0%, IC95%[ 30.9%, 49.8%]) | payout= 2.653x | EV=$+0.0613 | EV_lo=$-0.1791
  N= 30 ticks | sobreviveram  25/100 ( 25.0%, IC95%[ 17.5%, 34.3%]) | payout= 4.322x | EV=$+0.0805 | EV_lo=$-0.2417
  N= 40 ticks | sobreviveram  17/100 ( 17.0%, IC95%[ 10.9%, 25.5%]) | payout= 7.040x | EV=$+0.1968 | EV_lo=$-0.2331
  N= 50 ticks | sobreviveram   9/100 (  9.0%, IC95%[  4.8%, 16.2%]) | payout=11.467x | EV=$+0.0321 | EV_lo=$-0.4487

======================================================================
VEREDITO FINAL — 630 celulas testadas (symbol x growth_rate x N)
======================================================================
>>> 1 candidato(s) a edge (EV_lo > 0):
    1HZ50V g=0.02 N=2: EV_lo=$+0.0019 (P_emp=100.0%, N_amostra=100)

>>> PRE-REQUISITO antes de qualquer capital: confirmar com uma 2a amostra
    independente (rodar de novo em outro momento) -- viés de multiplos testes
    (630 celulas testadas, esperar ~31.5 falsos positivos a 5%).
```

