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
2. **`GET /markets/{id}` instável** — medido em 7 tentativas ao vivo (misturando curl isolado,
   Python, com e sem espera de 2-3s entre chamadas): **3 sucessos / 4 timeouts** (~40% falha).
   Descarta rate-limit por sequência (esperar não ajudou) e client (curl falhou igual ao
   Python) — parece infraestrutura/CDN inconsistente especificamente nessa rota.

## Round 3 — retestado depois de mais tempo: instabilidade é real e mais ampla que só `/markets/{id}`

Retestando mais tarde: `/markets/{id}` isolado voltou a funcionar 2/2 (confirma que é
intermitente, não permanentemente quebrado). Mas rodando o script completo mais vezes,
**`/events` também falhou** — 1 vez sozinho, e uma vez com **timeout nas 3 tentativas seguidas
mesmo com retry automático e 1.5s de backoff entre elas** (~33s de tentativas, todas sem
resposta). Ou seja: a instabilidade não é exclusiva de `/markets/{id}` nem puramente por
sequência de chamadas — parecem existir **janelas de instabilidade mais amplas** na API/CDN da
Jupiter (afetando qualquer rota por alguns segundos/minutos, depois voltando ao normal), não
apenas glitches isolados por request individual.

**Mitigações implementadas em `venues/jupiter_prediction.py`:**
- `_get()`: retry automático (3 tentativas, 1.5s de backoff) antes de desistir.
- `get_market()`: se `/markets/{id}` falhar mesmo após os retries, cai automaticamente para
  varrer `list_events()` (que já traz `pricing` embutido) — transparente pro caller,
  `get_price()` não precisou mudar.
- Isso **reduz mas não elimina** falhas — durante uma janela de instabilidade mais ampla, mesmo
  a rota de fallback pode falhar. `stream()` já tolera isso bem (`except Exception: continue`
  por symbol/ciclo — uma falha pontual não trava o loop, só pula aquele símbolo naquele ciclo).

**Conclusão prática:** adapter **validado ao vivo com dados reais** — autenticação, formato de
dados e lógica de extração de preço estão corretos. A API em si (não o código daqui) tem uma
taxa de falha intermitente não-trivial que qualquer uso em produção precisa aceitar e tratar
como esperado (retry + skip-and-continue), não como bug a "resolver" de vez.

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
- **Status atual: camada de leitura (`PriceFeedVenue`) validada ao vivo e com resiliência
  básica** (`venues/jupiter_prediction.py` — retry+backoff e fallback `/markets/{id}` →
  `/events`, ver Round 3 acima). Falta: (a) rodar por um período mais longo (horas, não
  minutos) pra medir a taxa de falha real em produção — a amostra atual é pequena (~15
  requests); (b) camada de execução (`ExecutionVenue`, assinatura de transação Solana) — ainda
  não iniciada, é uma decisão separada e precisa da wallet/chave privada Solana (mesma ressalva
  de segurança já aplicada à Polymarket).
