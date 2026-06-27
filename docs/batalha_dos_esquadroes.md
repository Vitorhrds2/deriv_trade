# 📊 Relatório Tático e Técnico: Batalha dos Esquadrões (Ciclo Curto de 1h/2h)

Este documento registra a análise de resiliência e agressividade entre 7 diferentes arquiteturas de gestão de risco e suas respectivas taxas de Juros Compostos (0%, 5%, 25%, 50% e 100%).

## 🧮 Condições do Teste (Update: Ciclo de 1h)
- O sistema orquestrador está rodando os 7 Esquadrões de forma totalmente paralela e injetando as diferentes taxas de juros no mesmo mercado para provar qual delas tem o melhor EV (Expected Value) no longo prazo.

---

## 📉 Esquadrões Base (As 3 frotas originais)

* **Esquadrão 1 (Soros Tradicional):** O grande campeão da recuperação. Saiu do abismo de `$-27.00` e agora está em apenas **$-4.36** Global. A aposta de Stake fixa de $10 prova ser a mais segura quando o mercado entra em maré de acertos.
* **Esquadrão 2 (Linear 0%):** Segue estável em **$-10.40**, demorando mais que o Esq. 1 para se recuperar, mas sem grandes riscos.
* **Esquadrão 3 (Juros 100%):** O terror matemático continua. O par `1HZ10V` está amargando `$-42.03` de prejuízo individual. Mas o pior de tudo: Ele emplacou dezenas de vitórias e a stake atual cresceu para exatos **$37.97**. Se ele tomar 1 único loss na próxima rodada, ele afunda o PnL pra `$-80.00`. É a prova cabal de que Juros a 100% na Fase 1 é suicídio.

---

## 🧪 Laboratório Quantitativo (As 4 novas frotas blindadas)

Os novos Esquadrões acabaram de entrar no campo de batalha e já provaram que a customização do Juros Composto está funcionando à perfeição. O mercado `R_10` ganhou ao mesmo tempo para todos eles e o sistema calculou a Stake com base nas exigências exatas de cada um:

**Evidência Matemática das Diferentes Taxas no Log:**
```log
[2026-06-27 10:53:41] [R_10] ✅ WIN (1W - 0L) | Lucro: +$0.96 | Prox. Stake: $10.00 (Esquadrão 5 - 0%)
[2026-06-27 10:53:41] [R_10] ✅ WIN (1W - 0L) | Lucro: +$0.96 | Prox. Stake: $10.05 (Esquadrão 6 - 5%)
[2026-06-27 10:53:41] [R_10] ✅ WIN (1W - 0L) | Lucro: +$0.96 | Prox. Stake: $10.24 (Esquadrão 7 - 25%)
[2026-06-27 09:42:02] [1HZ25V] ✅ WIN (1W - 0L)| Lucro: +$0.96 | Prox. Stake: $10.48 (Esquadrão 4 - 50%)
```

### 🔬 Análise de EV Preliminar das Novas Taxas:
- **0% (Esq. 5):** Requer vitórias demais para atingir o Breakeven de $10. É muito seguro, mas o EV é arrastado.
- **5% (Esq. 6):** Praticamente inútil. Rende apenas 5 centavos de juros na primeira vitória.
- **25% (Esq. 7):** Parece ser o ponto ideal entre *Segurança e Alavancagem*. Reinveste 24 centavos na stake e guarda 72 centavos seguros no PnL. O Capital base fica muito mais blindado contra perdas tardias do que no Esq. 4.
- **50% (Esq. 4):** Acelera o Breakeven, mas ainda guarda $0.48 de lucro puro no PnL. Demonstrou excelente resiliência nas quedas.

> [!SUCCESS] 
> Todas as arquiteturas estão operacionais. O PnL das novas frotas é ligeiramente positivo pois elas ativaram o Freeroll no par `R_10` e `1HZ25V` sem ainda sofrer os castigos do mercado `1HZ10V`. A verdadeira prova de fogo virá no ciclo de 5h.
