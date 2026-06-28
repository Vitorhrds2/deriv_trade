# 📂 Dossiê Confidencial: Fase 1 - A Batalha dos Esquadrões

**Status Operacional:** Concluído (Fase 1 Encerrada)
**Duração do Teste:** ~5.5 Horas de combate ininterrupto (10:00 - 15:30)
**Foco:** Teste de Estresse de Juros Compostos e Resiliência a Drawdowns

---

## ⏱️ Linha do Tempo das Execuções

* **10:00 (Local)** - Lançamento da Frota Original (Esquadrões 1, 2 e 3). O objetivo era validar a eficácia do *Smart Freeroll* contra o sistema tradicional e testar o Juro Composto a 100%.
* **12:39 (Local)** - Injeção do **Esquadrão 4 (50%)**. Uma tentativa de frear a insanidade do Esquadrão 3 limitando o reinvestimento.
* **13:03 (Local)** - Início do Laboratório Quantitativo. Lançamento simultâneo dos **Esquadrões 5 (0%), 6 (5%) e 7 (25%)**.
* **14:00 (Local)** - Alarme de 1 Hora: O laboratório prova que a diferença matemática na recuperação funciona perfeitamente na fase inicial de alta.
* **15:00 (Local)** - Alarme de 2 Horas: A frota de 100% (Esq. 3) afunda irreversivelmente.
* **15:15 (Local)** - Evento Cisne Negro. O mercado inverte subitamente e gera uma sequência brutal de perdas simultâneas em vários pares.
* **15:30 (Local)** - Intervenção Militar. Descoberta do "Bug das Casas Decimais" que paralisou as frotas de laboratório.

---

## 🎖️ Análise dos Esquadrões e Resultados Finais

### Esquadrão 1 (Soros Tradicional - Stake Fixa)
* **Objetivo:** Baseline. Testar a resiliência de atirar sempre com `$10` sem Freeroll.
* **Resultado:** O grande sobrevivente. Por não acumular lucros na stake, ele tomou o crash de frente, mas o prejuízo limitou-se a **$-39.08**. Sobreviveu.

### Esquadrão 2 (Linear 0% - Com Smart Freeroll)
* **Objetivo:** O mesmo do Esq 1, porém protegendo o capital inicial quando atinge 100% de lucro.
* **Resultado:** Sobreviveu bem no início, mas o Evento Cisne Negro ocorreu justamente quando as stakes dele não estavam na proteção do Freeroll, afundando a conta para **$-78.10**.

### Esquadrão 3 (Juros 100% na Fase 1)
* **Objetivo:** Tentar a recuperação ultrarrápida reaplicando todo o lucro na próxima Stake.
* **Resultado:** **RUÍNA TOTAL**. Como o WinRate não foi de 100%, ele ganhou inúmeras vezes seguidas, elevou a stake para `$37.00` e, quando tomou 1 loss, destruiu 2 horas de lucro em 1 segundo. Prejuízo de **$-85.42**. Tese matematicamente descartada.

### Esquadrões de Laboratório (4, 5, 6 e 7)
* **Objetivo:** Testar taxas mistas (50%, 0%, 5% e 25%) para encontrar o Santo Graal do *Expected Value (EV)* no longo prazo.
* **Resultado:** **DADOS COMPROMETIDOS**. Duas falhas críticas paralisaram os testes:
  1. **Falha Arquitetônica:** O orquestrador lançou clones de 25% para todas as instâncias em vez de aplicar a taxa respectiva.
  2. **Erro de Casas Decimais:** O fracionamento de 25% gerou floats como `$10.2175`, que a Deriv rejeitou de forma silenciosa, congelando as contas a partir das 14:56.

---

## 🎯 Veredito do Comando
O Juro Composto a 100% é insustentável para a volatilidade dos mercados de `1HZ`. A intervenção militar aplicará suporte paramétrico de Juros para recomeçarmos o laboratório de forma cristalina para a bateria de testes noturna.
