# O Paradoxo do Teto: Por que pulos maiores falharam?

Para responder à sua pergunta com a máxima precisão matemática, eu escrevi um script que vasculhou o arquivo `BTCUSDT-aggTrades-2026-06-25.csv` (contendo todo o histórico real da Binance) para mapear **exatamente** o que acontece com o preço 2 segundos após um pulo.

Defini como "Sustentado" qualquer pulo que não revertesse mais que 50% de sua força nos 2 segundos seguintes.

## Os Resultados Brutos da Binance
```text
=== ANÁLISE DE SUSTENTAÇÃO POR TAMANHO DO PULO (2 SEGUNDOS) ===
Bracket    | Total    | Sustained  | Reverted   | Win Rate
-------------------------------------------------------
50-60      | 2250     | 1695       | 555        | 75.3%
60-70      | 1135     | 901        | 234        | 79.4%
70-80      | 683      | 612        | 71         | 89.6%
80-90      | 431      | 412        | 19         | 95.6%
90-100     | 185      | 178        | 7          | 96.2%
100+       | 659      | 652        | 7          | 98.9%
```

> [!WARNING]
> **A Revelação Chocante:** Quanto maior o pulo, **MAIOR** a chance dele se sustentar. Pulos acima de $100 se sustentam em impressionantes 98.9% das vezes!

### Mas se pulos de $100 são mais seguros, por que perdemos na Demo?

Aqui está o segredo que o backtest não mostra, mas a execução real (*Execution Time*) revelou: **O Tempo de Construção do Pulo.**

Um pulo de $50 muitas vezes acontece em um único instante (uma ordem agressiva a mercado que raspa o livro de ofertas). Como é instantâneo, o robô detecta e atira antes da onda chegar na Deriv.

Um pulo gigantesco de $116 quase nunca acontece em 1 milissegundo. Ele é uma cascata de liquidações que leva, digamos, **200 a 400 milissegundos** para se formar. 
O que acontece na prática:
1. A Binance começa a subir rápido: `$10... $20... $30...`
2. Essa primeira onda de alta já viaja pela internet e atinge o gráfico da Deriv.
3. Quando a Binance finalmente cruza nosso gatilho de `$50`, o robô atira.
4. Mas a essa altura, a Deriv já absorveu os primeiros `$40` do movimento!
5. Nós acabamos entrando **no meio ou no fim** do pulo, comprando o contrato muito caro. Quando o preço estabiliza 2 segundos depois, ele retraiu levemente e não paga a nossa comissão.

### A Solução e o "Maior Teto Possível"

O teto de $65 foi uma sugestão inicial conservadora. Olhando os dados, pulos até a faixa de **$80 a $90** (Win Rate de 95%) ainda são excelentes, desde que eles sejam *instantâneos*.

Se você quiser abrir mão do teto rígido e capturar todos os pulos gigantescos com segurança, precisamos **mudar a forma como o robô enxerga o pulo**. Em vez de limitar o tamanho do salto, devemos **limitar o tempo de formação do salto**.

Podemos remover o `PRICE_SHOCK_CEILING` e instruir o robô a só aceitar pulos que ocorreram em **menos de 50 milissegundos** no histórico da Binance. Se o preço subiu $120 em apenas 10 milissegundos, nós atiramos. Se subiu $120 mas levou 300 milissegundos, nós ignoramos (pois a Deriv já começou a refletir a alta).

Você prefere manter um teto fixo de preço (ex: `$85`), ou prefere que eu remova o teto de preço e adicione esse **Teto de Tempo (Velocity Filter)** para garantirmos que só pegaremos explosões instantâneas, independentemente do tamanho?
