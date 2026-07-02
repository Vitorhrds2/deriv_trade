# Phantom / Solana — Prediction Markets: o que existe de verdade (2026-07-02)

**Pergunta original:** dá pra rodar hipóteses de prediction/future markets no ecossistema Phantom,
antes de configurar a Polymarket diretamente? Ponto de partida foi a resposta do próprio
"Phantom Assistant" (colada pelo usuário): Phantom nativo só cobre perps na Hyperliquid, não
prediction markets. Investigação abaixo confirma isso e acha duas rotas alternativas reais.

## 1. Phantom nativo (MCP + CLI oficiais) — só perps, confirmado

`docs.phantom.com/phantom-mcp-server/tools` e `/phantom-cli/index` (lidos na íntegra):

- Ferramentas: wallet ops (saldo, endereços, assinar/enviar tx Solana e EVM), swaps
  (`buy_token`, `portfolio_rebalance`), e **Perpetuals** (`open_perp_position`,
  `close_perp_position`, `cancel_perp_order`, `update_perp_leverage`,
  `deposit_to_hyperliquid`/`transfer_spot_to_perps`/`withdraw_from_perps`) — tudo perps via
  **Hyperliquid**, nada de prediction market.
- Redes suportadas: Solana, Ethereum/EVM (inclui **Polygon** — Phantom dá pra usar como carteira
  da própria Polymarket via `window.phantom.ethereum`, EIP-1193, se decidirem ir pela rota direta
  em vez da Solana), Bitcoin, Sui.
- **Conclusão:** se o objetivo fosse só "rodar hipótese de momentum/direção em cripto com
  alavancagem", perps na Hyperliquid via Phantom seria viável tecnicamente — mas é uma aposta
  DIRECIONAL com risco de liquidação, exatamente o tipo de coisa que H1/H3/T4/rng_bot já
  refutaram (nenhuma estratégia de adivinhar direção teve EV positivo aqui). Perps não é
  prediction market e não muda esse veredito.

## 2. World — prediction market embutido no Phantom (achado novo)

- Lançado publicamente **01/06/2026**, substituindo uma integração anterior com **Kalshi via
  DFlow** que o Phantom rodava desde dezembro/2025.
- Protocolo não-custodial: roteia ordens pra liquidity providers na Solana, não guarda fundos.
  Settlement via **Chainlink Data Streams**, payout automático em **CASH** (stablecoin Solana).
- Lista, no lançamento: contratos de **BTC Up/Down de curta duração** (mesmíssimo formato do
  PA5!) + mercados da Copa do Mundo 2026.
- **Sem API pública encontrada** — lançamento muito recente ("stealth", sem volume/liquidez
  publicados ainda). Não dá pra automatizar hoje; vale monitorar (`docs.phantom.com`,
  changelog do World) se/quando abrirem developer docs.

## 3. Jupiter Prediction API — a rota acionável agora ⭐

`developers.jup.ag/docs/guides/how-to-build-a-prediction-market-app-on-solana` +
`developers.jup.ag/docs/prediction/index` (lidos na íntegra). **Achado mais importante desta
investigação:**

- **Uma API só, agrega liquidez de Polymarket E Kalshi** (`provider=polymarket` (default) ou
  `provider=kalshi` em `GET /events`) — potencialmente resolve tanto Polymarket quanto Kalshi
  numa integração só, sem precisar da conta/wallet nativa de nenhum dos dois separadamente.
  Confirmado por fonte externa: Polymarket entrou na Solana via Jupiter em fev/2026
  (`x.com/JupiterExchange`, 01/02/2026).
- **Base URL:** `https://api.jup.ag/prediction/v1`. Precisa de API key (`x-api-key`, obtida em
  `developers.jup.ag/portal`) em **toda** chamada, inclusive leitura — não dá pra testar nem os
  endpoints públicos sem essa key primeiro.
- **Endpoints:** `GET /events` (lista, filtros `category`/`filter`/`provider`), `GET
  /events/search`, `GET /events/{id}`, `GET /markets/{id}`, `POST /orders` (compra, devolve tx
  Solana não-assinada), `GET /orders`, `GET /positions`, `DELETE /positions` (fecha), `POST
  /positions/{id}/claim` (resgate). Fluxo: `POST /orders` → assina localmente → submete pra
  Solana → keeper da Jupiter casa a ordem → posição atualiza → `claim` no settlement.
- **Moeda:** deposita em USDC ou JupUSD via carteira Solana (Phantom serve). Contratos a $1,
  preço = probabilidade (70¢ YES = 70%).
- **Restrição geográfica:** bloqueia IPs dos **EUA e Coreia do Sul** — não menciona Brasil.
  Verificar de qualquer forma antes de operar de verdade.
- **⚠️ Ressalva importante pro PA5:** a arquitetura da Jupiter (`docs/prediction/index`,
  "Orderbook & Price Discovery") descreve **keeper network + market makers próprios da Jupiter**,
  não um espelho 1:1 em tempo real do book da Polymarket. Ou seja: **a tese do PA5 (lag entre
  Binance e o book "stale" da Polymarket) não pode ser assumida como válida pra o mesmo mercado
  via Jupiter sem testar de novo** — pode ter lag melhor, pior, ou descorrelacionado do book
  nativo da Polymarket. Tratar como venue nova pra fins de hipótese, não como atalho pro mesmo
  resultado.
- **⚠️ Fees são reais** (ao contrário do swap de token da Phantom, que é sem taxa): cobradas em
  toda ordem executada, escalam com tamanho e com proximidade de 50¢ (mais incerteza = mais taxa).
  Exemplo da doc: 100 contratos a $0.25 ($25 de custo) paga **$1.32 de taxa** (~5.3% do
  notional) — mesma categoria de "custo pode comer o sinal" que já matou H1/H3/T4 e o hft_bot.
  Precisa entrar em qualquer cálculo de EV antes de cogitar operar.

## Teste ao vivo (2026-07-02, `JUPITER_API_KEY` configurada)

Resultado **inconclusivo, não é bug no adapter**. Diagnóstico feito via curl direto (isolando
Python/código):

| Chamada | Resultado |
|---|---|
| `api.jup.ag/` (raiz do domínio) | `404` em 0.05s — domínio saudável, resposta rápida |
| `api.jup.ag/prediction/v1` (sem subpath) | `404` em 0.2s — rota base existe |
| `.../prediction/v1/events` **sem** header de auth | timeout (10s, `STATUS:000`) |
| `.../prediction/v1/events` com key **inválida de propósito** | `401` limpo em 0.04s |
| `.../prediction/v1/events` com a **key real do usuário** | timeout (15-30s, `STATUS:000`) — 3 tentativas |
| `status.jup.ag` | banner "All services are online" (sem outage geral declarado) |

Key real confirmada com formato/tamanho normais (36 chars, formato UUID, sem aspas/espaço
sobrando no `.env` — comparado byte-a-byte trimmed vs. raw, idêntico). O padrão estranho: uma
key **claramente inválida** recebe rejeição rápida (401), mas a key real trava exatamente como
"sem key nenhuma" — sugere que o problema está do lado da conta/key no backend da Jupiter (key
ainda não ativada, precisa de algum passo extra no portal tipo escolher plano/tier, ou
propagação/cache que ainda não pegou), não um erro de rede, geoblock, ou código daqui.

**Ação sugerida pro usuário** (não consigo ver o portal por vocês): conferir no
`developers.jup.ag/portal` se a key aparece como ativa, se falta selecionar algum plano/tier
gratuito, ou gerar uma key nova. Evitei bater repetidamente na key real pra não gastar rate
limit à toa — só retestar depois de checar o portal.

## Recomendação

- **Não vale a pena perseguir "Phantom nativo" nem "World"** agora — o primeiro é só perps
  (direção, já refutado como classe de estratégia aqui), o segundo não tem API.
- **Jupiter Prediction API é candidata real** a substituir a integração direta Polymarket
  CLOB/EIP-712 planejada — mesma cobertura de mercado, potencialmente cobre Kalshi de graça, e
  usa carteira Solana (Phantom) em vez de Polygon/MetaMask. Ação necessária pra prosseguir:
  **conta no `developers.jup.ag/portal` pra gerar a API key** (ação do usuário, mesmo tipo de
  limite já explicado pra Polymarket — não posso criar essa conta).
- Esqueleto de adapter (`trading-engine/venues/jupiter_prediction.py`) já criado, **não testado**
  (bloqueado até ter a API key). Assim que a key existir, validar `GET /events` ao vivo antes de
  qualquer coisa — mesma disciplina usada pra validar `BinanceVenue`/`PolymarketVenue`.
