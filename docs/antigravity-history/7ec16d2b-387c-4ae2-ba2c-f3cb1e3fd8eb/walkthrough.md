# Iteração 8: O Milagre dos 20 Centavos

A Skynet provou a tese matemática operando massivamente na conta Demo.
O usuário emitiu a diretriz de transição de ambiente: testar a robustez do algoritmo com os `$0.20` remanescentes em sua conta real. 

Nesta fase final de estresse hiper-assimétrico, configuramos a **Skynet HFT (Orquestrador Multi-Mercado)** com as seguintes regras de disparo:
- **Tática de Tiro:** 1000 Ticks / Duplo Virtual Loss
- **Aposta Base (Stake):** `$0.20`
- **Tática de Alavancagem:** Soros Nível 99 (Juros Compostos Infinitos). O lucro total é reinvestido indefinidamente, até perder tudo ou transformar os centavos em milhares de dólares.

**O Obstáculo da Corretora:**
A Deriv geralmente rejeita tecnicamente contratos DIGIT com stakes menores do que `$0.35`. O robô tentará enviar a ordem de `$0.20` mesmo assim. Se a API recusar (e devolver o log de "Stake too small" ou "Insufficient Balance"), precisaremos fazer a recarga fracionária até o mínimo técnico para continuarmos o milagre. A rede já está em andamento.
