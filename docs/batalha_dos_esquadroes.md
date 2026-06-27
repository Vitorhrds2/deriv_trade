# 📊 Relatório Tático e Técnico: Batalha dos Esquadrões (Snapshot de 30 Minutos)

Este documento registra a análise comparativa de resiliência e agressividade entre 3 diferentes arquiteturas de gestão de risco em ambiente de teste real (Deriv DEMO).

## 🧮 Variáveis e Condições do Teste
- **Alvo:** 5 Mercados de Índices Voláteis Sintéticos da Deriv.
- **Oráculo:** Skynet Lenta (VL=2 para Disparo).
- **Tempo de Exposição Analisado:** 30 Minutos.
- **Eventos Exógenos (Drawdown):** Todos os três esquadrões sofreram perdas idênticas devido a flutuações de mercado que acionaram o Loss em momentos específicos (`1HZ25V` e `RDBEAR`).

---

## 📉 Esquadrão 1: Soros Tradicional (Sem Trava de Risco)
* **Arquitetura Matemática:** `Stake(t+1) = Stake Base = $10.00`
* **Dinâmica de Recuperação:** Fixa e Linear. Cada Win injeta lucro marginal de `+$0.96`.
* **Impacto do Drawdown:** O impacto de 1 Loss de `$-10.00` requer aproximadamente `10.4` Wins para ser matematicamente zerado.
* **PnL Global Atual:** **$-23.39**
* **Veredito Técnico:** Extremamente letárgico no *Recovery Rate*. Uma taxa de acerto (Win Rate) alta não é suficiente para neutralizar os danos quando o retorno sobre o risco (R:R) é inferior a 1:1, fazendo a curva de capital afundar a cada colapso.

---

## 🛡️ Esquadrão 2: Smart Freeroll Lineal (Sem Juros Compostos)
* **Arquitetura Matemática:** Fase 1 com `Stake(t) = 10.00`. O PnL é isolado para tentar atingir o threshold de `$10.00`.
* **Impacto do Drawdown:** Absorveu o impacto isoladamente sem comprometer a integridade de longo prazo. Após cair para o negativo, iniciou um ciclo linear de recuperação similar ao Esquadrão 1, porém segmentado.
* **PnL Global Atual:** **$-2.52**
* **Veredito Técnico:** Alta segurança contra ruínas totais (Risco engessado na Fase 1), mas falha no quesito *Time-to-Breakeven* (TTB). Com um TTB alto, o sistema passa tempo demais exposto ao risco original ($10) antes de ejetar o capital.

---

## 🚀 Esquadrão 3: Smart Freeroll Agressivo (Juros Compostos 100%)
* **Arquitetura Matemática (Fase 1):** `Stake(t+1) = Stake Base + PnL_Total` até `PnL_Total >= Stake Base`.
* **Mecânica de Recovery:** Exponencial. Quando ocorre uma perda, o lucro retido é pulverizado (o PnL cai no abismo do Loss), mas a reinicialização da stake aos `$10.00` imediatos, aliada à incorporação do lucro nas rodadas subsequentes, gera uma **Escalada Logarítmica** de recuperação.
* **PnL Global Atual:** **+$1.47 (Conta no Verde)**
* **Veredito Técnico:** É o modelo definitivo de sobrevivência em martingales invertidos (Soros). Ele sacrifica o "lucro seguro inicial" (que era minúsculo) em troca de um *Recovery Rate* brutal. Absorveu os exatos mesmos losses que o Esquadrão 1, mas recuperou o estrago na metade do tempo.

### 🔬 Telemetria dos Nodes (Esquadrão 3)
| Mercado | Win Rate | Sequência Atual | PnL Acumulado | Stake Turbinada | Status do Breakeven |
|---------|----------|-----------------|---------------|-----------------|---------------------|
| `RDBULL` | 100.0% | 6W - 0L | +$7.37 | $17.37 | Faltam ~$2.63 |
| `R_10` | 100.0% | 4W - 0L | +$4.45 | $14.45 | Faltam ~$5.55 |
| `1HZ10V` | 100.0% | 3W - 0L | +$2.85 | $12.85 | Faltam ~$7.15 |
| `1HZ25V` | 87.5% | 7W - 1L | -$4.16 | $15.84 | Recuperando Loss |
| `RDBEAR` | 50.0% | 1W - 1L | -$9.04 | $10.96 | Recuperando Loss |

> [!NOTE] 
> O `RDBULL` é o candidato mais forte a invadir a **Fase 2** nas próximas execuções. Ao bater +$10.00, o modelo realizará a extração e entrará no módulo 25/75 (Resgate vs Stake).
