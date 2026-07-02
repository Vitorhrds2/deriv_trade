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

## Teste ao vivo (2026-07-02) — Round 1: key antiga (36 chars, formato UUID)

Timeout consistente (3 tentativas). Key claramente inválida recebia `401` limpo e rápido, mas a
key real travava igual a "sem key nenhuma" — apontava pra algo do lado da conta/key no backend
da Jupiter, não rede/código. Ação sugerida ao usuário: conferir/regenerar a key no portal.

## Round 2: key nova (`jup_...`, 68 chars) — RESOLVIDO, adapter validado ao vivo

Usuário gerou uma key nova com prefixo `jup_` (formato correto — a key antiga provavelmente era
o credencial errado copiado do portal). Diagnóstico revelou **dois problemas reais, ambos
corrigidos**:

1. **`403 Forbidden ("error code: 1010")` no adapter Python, mas curl funcionava** — `error code:
   1010` é o código do WAF da Cloudflare pra "assinatura de browser bloqueada". O `urllib` do
   Python manda `User-Agent: Python-urllib/3.13` por padrão, que o WAF na frente da `api.jup.ag`
   rejeita mesmo com a key correta; `curl` passa porque manda um UA diferente. **Fix**: adicionado
   `User-Agent` explícito em `venues/jupiter_prediction.py::_get()`. Depois do fix, `list_events()`
   passou a retornar dados reais (10 eventos, ex. *"What price will Bitcoin hit in July?"*, com
   `pricing` já embutido por market).
2. **`GET /markets/{id}` instável** — funcionou 1x, depois travou (timeout puro, sem resposta)
   em 3 tentativas seguidas, reproduzido tanto via `curl` isolado quanto via Python — ou seja,
   **não é bug de client**, é a rota específica se comportando de forma inconsistente no lado da
   Jupiter (rate-limit mais agressivo nela, ou instabilidade real do backend — não deu pra
   confirmar qual). Como `/events` **já traz `pricing` embutido em cada market** (não precisa de
   uma chamada por market), a recomendação registrada no código é: pra polling de preço em
   produção, preferir extrair de `list_events()` em vez de `get_market()`/`get_price()`
   individual — mais barato E evita a rota flaky. Não implementei esse fallback automático agora
   (instabilidade não confirmada como persistente, evitando engenharia prematura) — só
   documentado como próximo passo se `stream()` for usado de verdade.

**Conclusão prática:** adapter **parcialmente validado ao vivo** — leitura de eventos/mercados
(`list_events`) funciona 100% com dados reais da Polymarket via Jupiter. Preço por-market
individual (`get_price`/`get_market`) funciona mas com confiabilidade a confirmar; usar via
`list_events` é o caminho mais robusto por ora.

**Nota de segurança:** durante o diagnóstico um `curl -v` chegou a ecoar a API key completa no
output de debug (comportamento normal do `-v`, mas potencialmente sensível) — o arquivo temporário
que continha isso foi apagado imediatamente; a key não foi exposta em nenhum arquivo do repo nem
ficará em nenhum commit.

## Recomendação

- **Não vale a pena perseguir "Phantom nativo" nem "World"** agora — o primeiro é só perps
  (direção, já refutado como classe de estratégia aqui), o segundo não tem API.
- **Jupiter Prediction API é a rota de execução mais realista pra hipóteses em prediction
  markets** — mesma cobertura de mercado da Polymarket (CLOB/EIP-712 direto está de fato inviável
  a partir do Brasil, ver `docs/polymarket_dev_reference.md`), potencialmente cobre Kalshi de
  graça, usa carteira Solana (Phantom) em vez de Polygon/MetaMask, e **não bloqueia Brasil**.
- **Status atual: `list_events()` validado ao vivo com dados reais** (`venues/jupiter_prediction.py`,
  commit pendente). Falta: (a) confirmar se a instabilidade do `/markets/{id}` é persistente ou
  transitória (retestar mais espaçado no tempo), (b) decidir se vale implementar o fallback via
  `list_events()` pra `get_price`, (c) camada de execução (`ExecutionVenue`, assinatura de
  transação Solana) — ainda não iniciada, é uma decisão separada e precisa da wallet/chave
  privada Solana (mesma ressalva de segurança já aplicada à Polymarket).
