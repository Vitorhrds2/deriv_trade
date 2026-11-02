Sim, essa preocupação foi testada diretamente. O resultado **não indica uma diferença Demo × Real no feed de ticks**.

## Comparação real executada

Usei o mesmo `DERIV_APP_ID` e `DERIV_API_TOKEN`, alternando apenas:

```python
use_demo=True
use_demo=False
```

Ambas as contas foram autenticadas corretamente.

### Ticks dos últimos 7 dias

| Métrica | Demo | Real |
|---|---:|---:|
| Ticks coletados | 604.796 | 604.796 |
| Requests | 605 | 605 |
| Cobertura | 604.800s | 604.800s |
| Intervalo mediano | 1s | 1s |
| Maior gap | 6s | 6s |
| Timestamps iguais | — | Sim |
| Preços iguais | — | Sim |

O comparador encontrou:

```text
identical_times_and_prices = true
first_difference = null
```

<ref_snippet file="/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/d107_exact_7d_simulation.summary.json" lines="248-267" />

Portanto, a hipótese de que a Demo estaria recebendo uma série de ticks artificialmente favorável **não foi sustentada pelos dados**.

## Comparação das quotes

Também foram feitas proposals read-only em ambas as contas:

| Stake | Direção | Demo ask | Real ask | Fee | Commission |
|---:|---|---:|---:|---:|---:|
| `$1` | MULTUP | `$1,04` | `$1,04` | `$0,04` | `$0,02` |
| `$1` | MULTDOWN | `$1,04` | `$1,04` | `$0,04` | `$0,02` |
| `$10` | MULTUP | `$10,44` | `$10,44` | `$0,44` | `$0,15` |
| `$10` | MULTDOWN | `$10,44` | `$10,44` | `$0,44` | `$0,15` |

<ref_snippet file="/Users/vitorhrds/Documents/Github/hypothesis/d107_exact_7d_simulation.summary.json" lines="10-121" /> <ref_snippet file="/Users/vitorhrds/Documents/Github/hypothesis/d107_exact_7d_simulation.summary.json" lines="136-240" />

Houve pequenas diferenças no `spot` de algumas proposals porque as requisições Demo e Real ocorreram em instantes diferentes. O custo econômico do contrato foi igual.

## Resultado das simulações Demo versus Real

Como:

1. os ticks foram idênticos;
2. ask price, cancellation fee e commission foram iguais;
3. o algoritmo e os parâmetros foram iguais;

os resultados simulados Demo e Real foram essencialmente idênticos.

Isso significa que **não apareceu uma ameaça Demo-only na série de mercado nem no pricing atual dos contratos**.

## Onde ainda poderia existir uma diferença Demo/Real

A comparação de ticks não elimina diferenças em:

- execução de `buy`;
- execução de `sell`;
- rate limiting;
- latência e reprecificação;
- liquidação/stop-out;
- permissões da conta;
- comportamento do gateway autenticado;
- disponibilidade de contratos;
- tratamento de posições perpétuas;
- saques e restrições operacionais.

A Demo pode ter o mesmo feed e o mesmo preço de proposal, mas ainda assim uma ordem real poderia ter comportamento diferente no momento da execução.

## O que já foi confirmado

Na Demo, a venda automática em 3x foi testada:

```text
8 posições elegíveis
8 vendas aceitas
0 falhas
P&L realizado: +$30,06
```

Isso confirma a mecânica no ambiente Demo, mas não é uma prova de execução Real.

## Conclusão

A hipótese “a Demo recebe ticks melhores para atrair desenvolvedores” **não encontrou evidência**:

- os 604.796 ticks Demo e Real foram exatamente iguais;
- os timestamps também foram iguais;
- os preços de proposal, fees e commissions foram iguais;
- o resultado simulado foi igual nos dois perfis.

A explicação mais provável para o resultado atual é:

```text
movimento real do índice
+
sobrevivência seletiva dos winners
+
400x
+
cancellation dos losers
+
venda automática em 3x
```

A única parte que ainda não pode ser provada por simulação histórica é a execução de uma ordem real. Para eliminar definitivamente a hipótese de diferença no execution layer, seria necessário um canário Real de tamanho mínimo, com autorização explícita, usando exatamente o mesmo mecanismo de venda em 3x. Nenhuma ordem Real foi executada até agora.