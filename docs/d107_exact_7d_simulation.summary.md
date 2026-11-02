Vou testar a hipótese de venda manual como uma variável explícita, não como premissa. Vou comparar, no mesmo caminho de 7 dias e com as mesmas entradas:

- hold winners até o fim;
- vender winner no boundary;
- vender no primeiro PnL positivo após o boundary;
- targets fixos de lucro;
- trailing/reversal determinísticos;
- cancellation de losers sempre no boundary.

Também vou auditar os campos reais `profit`, `bid_price`, `is_valid_to_sell` e reconstrução independente, para separar um possível problema de API de uma diferença real entre “segurar” e “realizar”.

A simulação atual não tinha saída manual como variável; estava comparando essencialmente hold. Adicionei cenários determinísticos de:

- `hold`;
- `sell_boundary`;
- `sell_target` de 10%, 25% e 50% do stake;
- `trailing_50`.

A saída manual só é permitida depois da janela de 5 minutos, sem hindsight. Vou rodar os 72 cenários Demo/Real-equivalentes sobre os mesmos 604.796 ticks, sem refazer chamadas à API.

A primeira saída manual mostrou um ponto crítico: vender no boundary sem limitar a velocidade de vendas gera milhares de ações em 7 dias e um retorno enorme. Isso é um **upper bound irrealista**, não uma prova de edge: ignora latência humana/API, rate-limit, fill histórico e capacidade de executar tantas vendas. Vou adicionar cooldowns de venda de 15s, 60s e 300s para separar o ganho estrutural do ganho impossível por turnover ilimitado.

A saída manual sem cooldown mostrou turnover impossível (milhares de vendas) e, por isso, não é uma conclusão autêntica. Estou rodando agora um segundo crivo com capacidade limitada de venda: 15s, 60s e 300s entre vendas, além de targets de `0,10x`, `0,25x` e trailing de 50%. Isso separa “vender positivo funciona” de “o simulador ganhou por assumir execução infinita”.

## Conclusão direta

**Sim: vender winners pode ser muito superior a segurar até o fim neste caminho histórico.**

**Não: isso não indica que exista um bug lucrativo na API.** O que aparece é uma estratégia diferente:

```text
cancelar losers + realizar winners + reciclar capacidade
```

O ganho da venda manual vem principalmente de:

1. evitar que winners revertam para loss/stopout;
2. liberar posições rapidamente;
3. permitir novas entradas;
4. aumentar brutalmente o turnover.

## Auditoria da API atual

Na última consulta dos contratos abertos:

- `is_valid_to_sell = 1` nos contratos;
- `is_valid_to_cancel = 0` após o boundary;
- havia múltiplas posições com P&L positivo;
- uma posição estava negativa.

Não existe evidência de que a API esteja impedindo a venda manual de winners. O D107 simplesmente não chama venda automaticamente por decisão de design. A divergência ocasional entre `profit` e reconstrução é um problema de consistência de dados/latência, não uma prova de edge. A reconciliação foi feita para não transformar contradição em winner automaticamente.

## Simulações de saída manual

Foram executados cenários determinísticos sobre os mesmos:

```text
604.796 ticks Demo
604.796 ticks Real
7 dias
605 páginas por perfil
nenhuma diferença nos timestamps/preços
sem aleatoriedade
```

<ref_snippet file="/Users/vitorhrds/Documents/Github/hypothesis/d107_exit_capacity_7d_summary.json" lines="1-14" />

### Cenário hold

Stake `$10`, banca `$104`, política de 20%:

```text
Final marcado: aproximadamente $132,74
Retorno:       +27,64%
Stopouts:      1
```

### Venda no boundary com cooldown de 300s

Mesmo stake/banca:

```text
Final marcado: aproximadamente $518,62
Retorno:       +398,68%
Compras:       2.213
Vendas:        1.023
```

Esse resultado é matematicamente interessante, mas não é uma estratégia manual humana plausível: exige aproximadamente 146 vendas por dia.

### Target de 0,25x do stake com cooldown de 60s

Stake `$10`, banca `$104`, política de 20%:

```text
Final marcado: aproximadamente $162,34
Retorno:       +56,10%
Compras:       346
Vendas:        128
Cancelamentos: 200
Stopouts:      18
Drawdown:      aproximadamente $41,09
```

Esse é o cenário manual mais interessante entre os testados porque tem menos turnover que vender todo winner no boundary. Mesmo assim, `128` vendas em 7 dias ainda significa aproximadamente 18 vendas por dia, e o fill histórico foi reconstruído por fórmula, não observado em cada venda.

### Target de 0,10x

Stake `$10`, banca `$104`, 20%:

```text
Final marcado: aproximadamente $284,55
Retorno:       +173,61%
Compras:       939
Vendas:        405
Stopouts:      12
```

O retorno aumenta, mas o volume de vendas deixa de ser realisticamente manual.

### Trailing de 50%

Stake `$10`, banca `$104`, 20%:

```text
Final marcado: aproximadamente $311,59
Retorno:       +199,60%
Compras:       1.172
Vendas:        513
Stopouts:      0
```

Também é um cenário de turnover automatizado, não uma validação de venda manual humana.

O relatório completo está em:

<ref_file file="/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/d107_exit_capacity_7d_summary.json" />

## O resultado mais importante

A simulação mostra uma diferença estrutural:

- **hold** sofre com reversões e stopouts;
- **venda de winners** realiza lucro e recicla capital;
- o ganho aumenta conforme a velocidade de venda aumenta;
- portanto, o maior componente do resultado é o turnover, não necessariamente uma previsão melhor de direção.

O cenário com cooldown zero gerou milhares de vendas e retornos absurdos. Ele deve ser descartado como upper bound irrealista, não como evidência.

## Por que ainda não posso chamar isso de edge comprovado

Mesmo usando ticks reais:

- os preços de ticks são exatos;
- as quotes atuais Demo/Real são reais;
- mas não existem snapshots históricos de `bid_price` para cada instante;
- as vendas históricas foram reconstruídas pela fórmula do multiplicador;
- não há slippage histórico de cada venda;
- não há rate limit histórico simulado no `sell`;
- milhares de contratos sobrepostos não equivalem a milhares de observações independentes;
- o caminho de 7 dias pode ter favorecido uma direção.

A implementação e os testes dos cenários estão em:

<ref_file file="/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/d107_exact_historical_simulation.py" /> <ref_file file="/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/test_d107_exact_historical_simulation.py" />

A verificação final passou com **46 testes**.

## Decisão prática

A hipótese mais promissora de curto prazo não é o D107 hold puro. É uma variante:

```text
MULTUP/MULTDOWN alternado
cancellation de losers no boundary
winner mantido apenas até target/trailing definido
venda após o boundary
cooldown de execução
limite de posições
```

O primeiro candidato para uma futura variante controlada seria:

```text
stake: $10
banca Demo: $104
capital: 20%
target: +0,25x do stake
cooldown de venda: 60s
```

Mas isso deve ser tratado como **uma nova variante experimental**, não como o D107 v0 original.

A conclusão mais honesta é:

> **Existe evidência forte de que realizar winners pode superar segurar winners neste caminho de 7 dias. Não existe ainda evidência de que isso seja uma máquina de dinheiro ou que o ganho sobreviva a execução real, slippage, rate limits, reversões e regimes diferentes.**