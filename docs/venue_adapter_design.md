# Design — Adapter Multi-Corretora (`trading-engine/venues/`)

**Status:** esqueleto inicial, validado ao vivo (2026-07-02). Não migra nada existente — é
100% aditivo, zero risco pro `hft_bot` em produção (`hft_arbitrage_bot.py` e `deriv_client.py`
não foram tocados, só importados/envelopados).

## Por que agora

`trading-engine/` tem ~130 scripts avulsos; cada integração de venue (Deriv, Binance/Coinbase/
Kraken como feed, Polymarket) foi implementada ad-hoc, com a MESMA lógica de WS/REST reescrita
em cada script novo (ex.: a assinatura do bookTicker da Binance aparece quase idêntica em
`passive_trigger_probe.py`, `hft_arbitrage_bot.py`, e agora de novo se eu não tivesse
consolidado). Pedido explícito de preparar terreno pra Kalshi/Binance-como-corretora/Phantom
torna isso não-opcional: sem uma interface comum, cada venue nova é mais um punhado de scripts
soltos, não um "ecossistema".

## O que existe hoje

```
trading-engine/venues/
├── __init__.py       # exporta PriceFeedVenue, ExecutionVenue, register, get_venue, list_venues
├── base.py            # as duas interfaces (ABC)
├── registry.py         # @register + get_venue()/list_venues()
├── binance.py          # BinanceVenue — WS-push, so leitura, validado ao vivo
├── polymarket.py        # PolymarketVenue — REST-poll, so leitura, validado ao vivo
└── deriv.py             # DerivVenue — envelopa deriv_client.DerivClient (nao modificado)
```

### Duas camadas de interface (`base.py`), de propósito

- **`PriceFeedVenue`** — o que toda venue tem em comum de verdade: preço público.
  `connect()`/`disconnect()`/`get_price(symbol)`/`stream(symbols, on_update)`. Binance/Coinbase/
  Kraken só terão isso (nunca vão virar venue de execução aqui). Cobre também a metade pública de
  Deriv/Polymarket/Kalshi.
- **`ExecutionVenue(PriceFeedVenue)`** — adiciona `requires_credentials`, `is_authenticated()`,
  `get_balance()`. **Deliberadamente não força um `place_order()` único** — contratos de opção
  da Deriv (barrier/duration/multiplier/growth_rate) e shares de mercado de previsão da
  Polymarket/Kalshi (preço 0-1) e spot da Binance-corretora são formatos genuinamente diferentes;
  fingir uma assinatura comum esconderia bug em vez de simplificar. Cada venue expõe seus
  próprios métodos de execução nativos (ex.: `DerivVenue.client.buy_contract(...)`) — o que é
  comum fica só em descoberta/introspecção.

### Validação ao vivo (2026-07-02)

```
BINANCE OK -> 376 updates em 3s (WS bookTicker btcusdt)
POLYMARKET OK -> slug resolvido, token CLOB, best ask=0.53 (REST book)
list_venues() -> ['binance', 'deriv', 'polymarket']; requires_credentials correto em cada uma
```

`DerivVenue` só foi validado estruturalmente (import + registro), não abri uma conexão
autenticada nova de propósito — reusa `deriv_client.py` sem alterar nada nele.

### `PolymarketVenue` é ilustrativo, não substitui o trabalho do Carlos

`trading-engine/polymarket_lag_probe.py` (branch `feat/polymarket-arb`, ainda não mergeada) já
tem a lógica completa (descoberta de janela Up/Down, lead-lag, A/B PAPER) — é o que roda no PA5
agora. `venues/polymarket.py` reimplementa só o primitivo genérico "preço por token" pra provar
que a interface funciona sem depender de um branch não-mergeado. **Quando `feat/polymarket-arb`
mergear, trocar a reimplementação por import direto das funções de lá** (evitar duas fontes de
verdade pra mesma chamada HTTP).

## Plano de migração (nada disso foi feito ainda — é a ordem sugerida)

1. **Consolidar os feeds duplicados** (Binance/Coinbase/Kraken) nos scripts que os reimplementam
   hoje (`hft_arbitrage_bot.py`, futuros probes) pra usar `venues.binance`/uma futura
   `venues.coinbase`/`venues.kraken` — risco baixo (comportamento idêntico, só remove
   duplicação), mas `hft_arbitrage_bot.py` está rodando ao vivo, então isso exige o mesmo
   cuidado de deploy/backup que qualquer mudança nele já tem hoje.
2. **Não mexer em `deriv_client.py`** — já é a única implementação, não há duplicação pra
   consolidar; `venues/deriv.py` é só uma capa fina por cima.
3. **Só then** adicionar venues novas de verdade (abaixo).

## Pesquisa necessária antes de codar Kalshi / Binance-corretora / Phantom

Nenhuma das três tem design pronto ainda — só levantamento do que falta:

- **Kalshi** — regulada nos EUA (CFTC), API REST nativa com auth por API key (RSA, não
  EIP-712/wallet crypto) ainda não pesquisada em detalhe. **Mas a Jupiter Prediction API (achada
  na investigação do Phantom, ver acima) já expõe `provider=kalshi` na mesma API usada pra
  Polymarket** — pode cobrir o caso de uso sem precisar da integração nativa Kalshi de imediato.
  Existe risco de elegibilidade geográfica diferente em qualquer uma das rotas (verificar antes
  de assumir que "é só trocar a URL").
- **Binance-como-corretora** (diferente de Binance-como-feed, já coberto): precisa de API
  key+secret HMAC, é ordem real de spot/futures com capital de verdade — nenhuma hipótese deste
  repo até hoje justificou isso (H1/H3/T4 usam Binance só como sinal, nunca como onde executar).
  Ficaria um `BinanceExecutionVenue(ExecutionVenue)` separado do `BinanceVenue` atual.
- **"Phantom"** — respondido em 2026-07-02 (ver `docs/phantom_ecosystem_findings.md`). Phantom em
  si (MCP/CLI oficiais) só automatiza **perps na Hyperliquid**, não prediction markets. Mas o
  ecossistema Solana ao redor tem duas rotas de verdade pra prediction market, achadas nessa
  investigação: **World** (app de prediction market embutido no próprio Phantom desde 01/06/2026,
  sem API pública encontrada ainda) e **Jupiter Prediction API** (`api.jup.ag/prediction/v1`,
  documentada, agrega liquidez de **Polymarket E Kalshi** na mesma API, paga em USDC/JupUSD via
  carteira Solana/Phantom). Jupiter é a rota acionável agora — ver `venues/jupiter_prediction.py`
  (esqueleto, ainda não testado, precisa de API key).

**Recomendação:** não escalar pra nenhuma das três até uma hipótese (PA5 ou outra) provar edge
real — mesma lógica do `docs/state_of_research.md`: arquitetura sem sinal validado pra explorar
é esforço sem retorno esperado.
