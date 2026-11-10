# Relatório de Auditoria Técnica e Mapeamento de Repositório (Survey 2)

**Data da Auditoria:** 2026-11-03  
**Auditor:** Teamwork Explorer Quant Survey 2  
**Escopo:** Auditoria técnica aprofundada do repositório local (`hypothesis/`), inspeção de implementações existentes, medições históricas, bibliotecas, ferramentas de venue e mapeamento do delta exato para execução ponta a ponta e simulação empírica dos vetores arquitetônicos (Hyperliquid H84, Drift SWIFT H85, Sui DeepBookV3 H86, Kalshi FIX H87, dYdX v4 L3 e GMX v2 / CEXs Tier-2).

---

## 1. Sumário Executivo & Matriz Comparativa de Implementação

A auditoria técnica examinou todos os módulos relevantes em `docs/`, `trading-engine/`, `hypothesis-lab-os/` e `agentic-conversation/`.

A conclusão principal é que **o repositório possui uma infraestrutura quantitativa madura para análise estatística (`stats_utils.py`), um design modular de venues (`trading-engine/venues/`) e protótipos exploratórios para H84, H85 e H86. No entanto, nenhum dos vetores possui atualmente um pipeline de execução ponta a ponta plenamente funcional ou simulação empírica com proteção mecânica integrada**. Além disso, **H87 (Kalshi FIX), dYdX v4 L3 e GMX v2 / Tier-2 CEXs estão 100% ausentes em código**, existindo apenas menções arquitetônicas conceituais.

### Matriz de Estado dos Vetores Arquitetônicos

| Vetor / Hipótese | Status no Repositório | Módulos / Arquivos Existentes | O que foi Testado / Medido | Defeitos Críticos / Gaps Encontrados | Delta para Execução & Simulação Empírica |
|---|---|---|---|---|---|
| **H84: Hyperliquid Mempool/Gossip** | Refutada por infraestrutura (`docs/state_of_research.md:1197`) | `trading-engine/h84_hyperliquid_gossip_feasibility.py`, `.json`, `hyperliquid_probe.py`, `hyperliquid_paper_bot.py` | Latência REST (mediana 152ms) e WS trades (mediana 285ms, outliers até 9.5s) da AWS us-east-2. | **Bug crítico de parsing no WS `l2Book`** resultou em 0 atualizações de livro e 0 fills simulados no JSON. Zero cliente gossip P2P. Zero execução/assinatura EIP-712/msgpack. | Cliente gossip ou emulador de mempool; conector de execução com flag Post-Only/ALO; filtro de toxic flow via oráculo CEX; simulador tick-level. |
| **H85: Drift / Velocity SWIFT Rebate** | Coletando dados (`state_of_research.md:1207`) | `trading-engine/h85_continuous.sh`, `h85_drift/h85_swift_subscriber.ts`, `h85_drift_swift_maker_rebate_scan.py` | Feed SWIFT WebSocket conectado via `@velocity-exchange/sdk@0.6.1`. Capturadas 53 msgs (SOL-PERP) em us-east-2 e 17 msgs em eu-central-1b. | **Apenas listener passivo** (zero código de envio de ordens). Ordens capturadas com desvio de ~2000 bps ($60 vs $75 Coinbase) devido a **artefato de escala de preço** não corrigido. Carteira não financiada. | Correção de decodificação de escala de preço; módulo de submissão de ordens maker post-only; projeção de slot de aterrissagem; deduplicação de mensagens SWIFT; simulador de fill rate. |
| **H86: Sui DeepBookV3 Flash Loan Arb** | Refutada por iliquidez (`state_of_research.md:1224`) | `trading-engine/h86_sui/` (`h86_onchain_orderbook.py`, `h86_deepbook_execute.ts`, `h86_deepbook_scan.ts`, `h86_setup_wallet.ts`, `.env`) | 16 pools DeepBookV3 mapeados via RPC Sui. Pool SUI/WUSDC revelou spread de 11.016 bps (bid 1.68 / ask 5.8 vs spot 0.73). | **Bug fatal de lógica em `h86_deepbook_execute.ts`**: executa compra no DeepBook e tenta sacar quote asset sem implementar a perna de venda em AMM. Carteira gerada mas não financiada; `BALANCE_MANAGER_ID` vazio. | Construção completa de PTB com perna AMM (Cetus/Turbos/Kriya); ciclo Hot Potato fechado com reversão atômica; descoberta de pools líquidos reais; simulação via `sui_dryRunTransactionBlock`. |
| **H87: Kalshi FIX / PrivateLink** | Não implementado (só citado em docs conceituais) | `docs/venue_adapter_design.md:78`, `docs/phantom_ecosystem_findings.md:44` | Pesquisa de alto nível: regulada CFTC, auth RSA. Jupiter Prediction API expõe `provider=kalshi` (validado em `venues/jupiter_prediction.py`). | **Zero código FIX**, zero conexão AWS PrivateLink. Bloqueio regulatório (CFTC / US KYC). | Engine FIX (QuickFIX/Python ou socket puro); autenticação RSA; mock emulator local para pipeline livre de KYC; adaptador `KalshiVenue` em `venues/`. |
| **dYdX v4 CometBFT / L3** | Não implementado | Apenas símbolo `DYDXUSDT` em `unlock_short_bot.py` e exemplo em `agentic-conversation/README.md` | Nada testado em relação à exchange dYdX v4. | **Zero código de conectividade dYdX v4**, zero client Cosmos SDK / CometBFT. | Conector WebSocket/gRPC indexer dYdX v4; client de assinatura Cosmos SDK; envio de ordens de curto prazo com nonces determinísticos; simulador de ordem/latência. |
| **GMX v2 Data Streams & Tier-2 CEXs** | Não implementado (CEX Tier-1 D7/D8/D9/D32 refutados) | `docs/cex_arb_report.md` (D7/D8/D9), `docs/latency_arb_report.md` (D32), `docs/h3_latency_arb_report.md` | D7/D32 testaram Binance vs Bybit/OKX via REST: spread CEX 0-4 bps, latência REST 2.5s (10x pior que fees). H3 testou co-locação em Tóquio vs SP. | **Zero conector GMX v2 Data Streams**; zero conector MEXC ou Gate.io. | Conector Chainlink Low-Latency Data Streams (relatórios assinados off-chain); conectores WS MEXC e Gate.io; detector de lead-lag CEX Tier-1 -> Tier-2/GMX; simulador com fees reais. |
| **Venue Framework** | Esqueleto modular funcional | `trading-engine/venues/` (`base.py`, `registry.py`, `binance.py`, `polymarket.py`, `deriv.py`, `jupiter_prediction.py`, `jupiter_execution.py`) | Leitura Binance WS OK; Polymarket REST OK; Jupiter Prediction REST OK; Jupiter Execution validada com tx sintética e keypair de teste. | Falta extensão para os 6 novos vetores. Jupiter Execution não executada com saldo real (limite de $5 / saldo zerado). | Implementação das classes filhas `ExecutionVenue` e `PriceFeedVenue` para Hyperliquid, Velocity/Drift, Sui, Kalshi, dYdX e MEXC/Gate.io. |
| **Agentic / Orchestration** | Funcional para comunicação | `agentic-conversation/` (`local_relay.py`, `run.py`, `devin_telegram/`) | Ponte Telegram ⇄ Devin Cloud / Devin Local via HTTP relay (`~/.devin-local-relay`). | Desconectado dos scripts de trading da pasta `trading-engine/`. | Integração de telemetria e controle de runners/bots em background com alertas automatizados. |

---

## 2. Auditoria Aprofundada de `docs/state_of_research.md` e Histórico Quantitativo

### 2.1 Análise das Linhas 1190 a 1242 (H84, H85, H86)

O arquivo `docs/state_of_research.md` documenta a última grande iteração de pesquisa (2026-07-14 a 2026-07-15) em uma nova instância AWS us-east-2 (3.18.220.170, 2 vCPUs, 7.6GB RAM):

1. **H84 (Hyperliquid Gossip Protocol Market Making):**
   - **Proposta original:** Executar um nó não-validador da Hyperliquid com o parâmetro `split_client_blocks: true` para interceptar transações no mempool P2P 70-150ms antes da inclusão no bloco (finalidade), permitindo o cancelamento rápido de ordens maker expostas a fluxo tóxico (liquidações agressivas).
   - **Veredito registrado:** *REFUTADA por infraestrutura*. O nó completo exige no mínimo 32 núcleos de CPU, 128 GB de RAM e armazenamento NVMe de 500 MB/s. Na máquina de testes (2 vCPUs), houve um gap de 16x em CPU e 17x em RAM. A instância adequada (`c7i.32xlarge`) custaria ~$2.700/mês.
   - **Medições realizadas:** A REST API pública apresentou latência mediana de 152ms; o WebSocket de trades apresentou latência mediana de 285ms, mas com variabilidade extrema e picos de até 9.500ms.
   - **Conclusão registrada:** Sem a vantagem temporal do nó gossip, o formador de mercado compete via API pública contra HFTs que possuem o nó gossip, garantindo seleção adversa sistemática.

2. **H85 (Velocity Exchange / Drift SWIFT Maker Rebate):**
   - **Proposta original:** Utilizar a API SWIFT do Drift (renomeado para Velocity Exchange) para inspecionar intenções de ordens de takers 100-500ms antes da submissão on-chain na Solana, preenchendo ordens como maker para auferir rebate (ou fee zero) e fugir de fluxo tóxico.
   - **Descoberta da migração:** O repositório documentou a migração oficial de julho de 2026: pacote `@drift-labs/sdk` obsoleto substituído por `@velocity-exchange/sdk@0.6.1`, classes renomeadas (`DriftClient` → `VelocityClient`), program ID alterado para `vELoC1audYbSYVRXn1vPaV8Axoa9oU6BYmNGZZBDZ1P` e quote asset migrado de USDC para USDT na mainnet.
   - **Status registrado:** *COLETANDO DADOS*. O feed SWIFT conecta via WebSocket (`SwiftOrderSubscriber`). No scan inicial em us-east-2 (2 horas, 4 mercados), foram capturadas 53 mensagens apenas no par SOL-PERP (0 em BTC, ETH e HYPE).
   - **Alerta crítico registrado:** Todas as 53 ordens observadas continham preços cotados em ~$60 enquanto a Coinbase marcava ~$75 (desvio de ~2000 bps). O registro observa que isso pode ser um artefato de escala de precisão numérica da Drift (1e6 vs 1e9), mas que na época não foi resolvido. A coleta foi transferida para `eu-central-1b` no supervisor contínuo `h85_continuous.sh`.

3. **H86 (Sui DeepBookV3 Flash Loan Arbitrage):**
   - **Proposta original:** Explorar o padrão de *Hot Potato* em Programmable Transaction Blocks (PTB) na blockchain Sui para realizar arbitragem atômica triangular entre DeepBookV3 e AMMs, com risco zero de execução na perna perdedora (se o lucro não cobrir o empréstimo, a PTB inteira reverte na VM do Move).
   - **Veredito registrado:** *REFUTADO por iliquidez*. Um scan prévio via GeckoTerminal havia sugerido 80/80 amostras com spread > 10 bps (média de 3.670 bps), simulando uma oportunidade massiva. Porém, ao consultar diretamente os nós RPC da Sui, verificou-se que o pool SUI/WUSDC (com taxa de 20 bps) possuía ordens irreais: o melhor bid era 1.68 e o melhor ask era 5.8 (spread de 11.016 bps), com bids residuais de $0.001 e asks de $1.312, contra um preço real na Coinbase de $0.73. O suposto spread de 3.670 bps era um artefato de comparar uma cotação off-chain agregada com um livro on-chain completamente abandonado.

### 2.2 Lições Históricas do Repositório sobre Latência e CEX Arb (D7, D8, D9, D32, H3, D55)

O repositório já realizou uma série exaustiva de testes de microestrutura e latência que fornecem parâmetros quantitativos estritos:

- **D32 (`docs/latency_arb_report.md`):** Testou arbitragem de latência entre Binance, Bybit e OKX via REST API. Concluiu que consultas sequenciais por REST levam ~2.5s por amostra, enquanto a divergência máxima real entre CEXs Tier-1 foi de apenas 0.02% (2 bps), contra 20 bps de taxas roundtrip de taker (razão 1:10 desfavorável). Estabeleceu que **qualquer tentativa de capturar latência exige WebSocket/FIX e arquitetura assíncrona orientada a eventos**.
- **H3 (`docs/h3_latency_arb_report.md`):** Testou lead-lag entre Binance BTCUSDT e o índice sintético da Deriv. Demonstrou que a correlação aparente de lead-lag no feed de dados (+400ms a +1.200ms) era em grande parte um **artefato de amostragem** (a Deriv emitia ticks a 1 Hz, mas o motor interno reprecificava a execução com preço fresco em tempo real). Mesmo quando o robô foi co-locado em uma instância EC2 em Tóquio (`ap-northeast-1`), reduzindo a latência do sinal da Binance de 275ms para 2.6ms, o tempo de envio da ordem para a Deriv (~216ms através de Cloudflare) continuou superando a janela de reprecificação, resultando em taxa de acerto de 0% e PnL negativo. **Regra de Ouro:** *Nunca confiar apenas na correlação do feed de market data; o edge só existe se comprovado pelo fill do motor de execução*.
- **D55 (`docs/hyperliquid_report.md`):** Avaliou a Hyperliquid contra a Binance para carry de taxa de financiamento (D55a) e divergência de basis (D55b). Provou que apenas o par LINK possuía prêmio estrutural consistente (+96.3 bps net após taxas, 0 flips de direção em 90 dias), sobrevivendo ao custo de oportunidade de capital com alavancagem ≥ 3x. Revelou que `oraclePx`, `markPx` e `midPx` na Hyperliquid possuem dinâmicas acopladas por EMA.

---

## 3. Auditoria Detalhada dos Scripts e Arquivos de Código

### 3.1 Hyperliquid H84: `h84_hyperliquid_gossip_feasibility.py` e `.json`

A inspeção do arquivo `trading-engine/h84_hyperliquid_gossip_feasibility.py` revelou um defeito analítico fundamental:

1. **Bug Crítico de Parsing do WebSocket (`l2Book`):**
   - Nas linhas 156-185, a função `simulate_market_making` tenta ler os níveis de livro da mensagem WS da Hyperliquid:
   ```python
   # Trecho em h84_hyperliquid_gossip_feasibility.py:159-181
   levels = book.get("levels", [])
   # O código tenta checar se "bid" está em levels[0] ou buscar "px" diretamente:
   if "bid" in levels[0]: ...
   bid_levels = [l for l in all_levels if "bid" in l]
   ```
   - **A estrutura real da API WebSocket da Hyperliquid para o canal `l2Book`** é:
     `{"channel": "l2Book", "data": {"coin": "BTC", "time": 1720000000000, "levels": [[{"px": "60000.0", "sz": "1.5", "n": 3}, ...], [{"px": "60001.0", "sz": "2.0", "n": 2}, ...]]}}`
     onde `levels[0]` é a lista de bids e `levels[1]` é a lista de asks.
   - Como o código procurava uma chave literal `"bid"` dentro de cada elemento de lista, **todas as verificações falhavam silenciosamente**, caindo no `else: continue` (linha 185).
   - **Consequência direta:** No arquivo `h84_hyperliquid_gossip_feasibility.json`, as métricas resultantes foram:
     `"mm_book_updates": 0`, `"mm_fills": 0`, `"spread_bps_mean": null`.
   - A simulação de market making **nunca chegou a ser executada**, limitando o script a um simples medidor de latência de ping HTTP/WS.
2. **Ausência de Mecânica de Execução:**
   - Não há implementação de autenticação L1/L2 da Hyperliquid (assinatura EIP-712 com chave privada da carteira Arbitrum/HyperBFT, empacotamento MsgPack, geração de `action` com `vaultAddress`, `nonce`, etc.).
   - Não há lógica de colocação de ordem Post-Only (Add Liquidity Only - ALO), nem tratamento de cancelamento atômico dentro de janelas de milissegundos.

### 3.2 Drift / Velocity SWIFT H85: `h85_continuous.sh`, `h85_drift/` e Scans

A auditoria em `trading-engine/h85_drift/` detalha o estado técnico do conector SWIFT:

1. **Evolução dos Scripts:**
   - `h85_drift_swift_maker_rebate_scan.py` tentou conectar diretamente a `wss://swift.drift.trade/ws` via Python `websockets`. Falhou completamente com `ws_connected: false` porque o gateway SWIFT rejeita conexões de socket sem a autenticação e troca de mensagens de protocolo proprietárias do SDK.
   - O projeto migrou corretamente para TypeScript com o SDK oficial em `trading-engine/h85_drift/h85_swift_subscriber.ts`, utilizando a classe `SwiftOrderSubscriber` do pacote `@velocity-exchange/sdk@0.6.1`.
2. **Problema da Escala de Preço (Price Scaling):**
   - O log `h85_drift_swift_results.json` (linhas 18-20) exibe:
     `raw_price: 60065000, price: 60.065, price_deviation_bps: -2003.06` enquanto a Coinbase cotava SOL a $75.11.
   - O código em `h85_swift_subscriber.ts` (linhas 144-166) implementou uma heurística para adivinhar a escala dividindo por `1e6`, `1e9` ou `1e10`. Como $60.065 era o valor mais próximo de $75 entre os divisores de potência de 10, ele selecionou `1e6`.
   - No entanto, a discrepância de 20% não é explicada por um erro de 10x. Ela decorre de parâmetros específicos de ordens de leilão SWIFT: no protocolo Drift/Velocity, ordens de mercado SWIFT possuem um preço base de gatilho de leilão (`auctionStartPrice` / `auctionEndPrice`), e o parâmetro `price` dentro de `signedMsgOrderParams` pode representar o preço limite de proteção de slippage configurado pelo taker (ex: um comprador definindo um teto ou um vendedor aceitando até $60 em momento de liquidez reduzida), e não a cotação de mercado instantânea.
3. **Lacuna Operacional:**
   - `h85_swift_subscriber.ts` apenas faz o log no console. Não possui métodos para chamar `VelocityClient.placeOrder()` ou interagir com o programador de liquidez para postar o contra-fluxo maker dentro do slot de execução.
   - O wrapper `h85_continuous.sh` é um loop infinito simples que reinicia o script a cada término com pausa de 60s, acumulando logs mas sem tomar decisões ativas de trading.

### 3.3 Sui DeepBookV3 H86: `trading-engine/h86_sui/`

A inspeção em `trading-engine/h86_sui/` revelou uma inconsistência grave entre o design teórico e o código escrito em `h86_deepbook_execute.ts`:

1. **Defeito Estrutural Fatal em `h86_deepbook_execute.ts`:**
   - As linhas 94 a 150 detalham o fluxo montado na Programmable Transaction Block (PTB):
     - **Passo 1 (linha 97):** Toma emprestado USDC via flash loan do DeepBook (`borrow_flashloan_quote`). Retorna `[borrowedCoin, flashLoanReceipt]`.
     - **Passo 2 (linha 107):** Deposita o `borrowedCoin` no `BalanceManager` (`balance_manager::deposit`).
     - **Passo 3 (linha 118):** Submete ordem a mercado no pool do DeepBook (`pool::place_market_order`), gastando todo o USDC para comprar o token base (SUI).
     - **Passo 4 (linha 131):** **Aqui ocorre o erro fatal.** O script tenta sacar USDC do `BalanceManager`:
       ```typescript
       // Linha 131-138 em h86_deepbook_execute.ts
       const [returnCoin] = tx.moveCall({
         target: `${DEEPBOOK_PACKAGE}::balance_manager::withdraw`,
         arguments: [
           tx.object(balanceManagerId),
           tx.pure.u64(amountIn + minAmountOut), // tenta sacar USDC
         ],
         typeArguments: [quoteType], // quoteType = USDC
       });
       ```
     - **Passo 5 (linha 141):** Devolve `returnCoin` para quitar o flash loan (`pool::return_flashloan_quote`).
   - **Por que esse código falha categoricamente?** No Passo 3, o `BalanceManager` gastou o saldo de USDC para adquirir SUI. Portanto, o saldo de USDC no `BalanceManager` é **zero**. Tentar sacar `amountIn + minAmountOut` em USDC causará uma falha imediata de saldo insuficiente na execução do Move.
   - **A perna da AMM está ausente:** O script nunca implementou a troca dos tokens SUI recém-comprados de volta para USDC em uma AMM (Cetus, Turbos ou Kriya). Como o swap na AMM não existe na PTB, o Hot Potato `flashLoanReceipt` não pode ser fechado e a transação reverte com erro estrutural.
   - O próprio autor admitiu nas notas de rodapé (linha 248): *"Next: increase amount and add AMM leg for real arb"*, confirmando que o script era apenas um rascunho de sintaxe que nunca foi testado ou completado.
2. **Estado das Credenciais e Infraestrutura Sui:**
   - O arquivo `trading-engine/h86_sui/.env` possui uma chave privada gerada (`SUI_PRIVATE_KEY=suiprivkey1qzrf...`), com o endereço `0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9`.
   - Essa carteira tem **saldo zero de SUI** e o campo `DEEPBOOK_BALANCE_MANAGER_ID` está em branco. Para criar um `BalanceManager` no DeepBookV3, é necessário submeter uma transação on-chain que consome gás em SUI.
   - `h86_onchain_orderbook.py` provou conclusivamente que o pool SUI/WUSDC monitorado estava sem formadores de mercado ativos, com spread superior a 100%.

### 3.4 Arquitetura do Adapter de Venues (`trading-engine/venues/`)

O diretório `trading-engine/venues/` foi criado em 2026-07-02 (`docs/venue_adapter_design.md`) para padronizar conexões entre plataformas.

1. **Abstração Base (`base.py`):**
   - Define `PriceFeedVenue(ABC)` para dados públicos de mercado (`connect`, `disconnect`, `get_price`, `stream`). Utiliza a dataclass `PriceUpdate(venue, symbol, price, ts, raw)`.
   - Define `ExecutionVenue(PriceFeedVenue)` para venues onde ordens reais podem ser colocadas (`requires_credentials = True`, `is_authenticated`, `get_balance`).
   - **Decisão deliberada:** O design optou por **não criar um método `place_order()` genérico** em `ExecutionVenue`, reconhecendo que opções binárias da Deriv, shares binários de previsão (Polymarket/Kalshi) e contratos perpétuos (Hyperliquid/Drift/dYdX) possuem estruturas de ordem fundamentalmente incompatíveis. Cada venue expõe seus métodos nativos de envio.
2. **Registro Desacoplado (`registry.py`):**
   - Utiliza um dicionário global e um decorator `@register` que permite que qualquer nova classe venue se auto-registre pelo atributo `name`, eliminando dispatchers acoplados.
3. **Implementações Existentes:**
   - `binance.py`: `BinanceVenue` implementa leitura de WebSocket do stream `/bookTicker`.
   - `polymarket.py`: `PolymarketVenue` implementa leitura REST dos livros Gamma e CLOB da Polymarket via HTTP polling.
   - `deriv.py`: `DerivVenue` envelopa o cliente existente `DerivClient`, fornecendo leitura e execução de contratos sintéticos.
   - `jupiter_prediction.py`: `JupiterPredictionVenue` consome a API da Jupiter Prediction (`api.jup.ag/prediction/v1`), que agrega liquidez tanto da Polymarket quanto da Kalshi. Implementa contramedidas vitais validadas ao vivo: User-Agent customizado para contornar o WAF da Cloudflare (erro 1010), retentativas com backoff de 1.5s e fallback automático de `/markets/{id}` para `/events`.
   - `jupiter_execution.py`: `JupiterExecutionVenue` implementa assinatura local de transações Solana usando a biblioteca `solders` (`VersionedTransaction`), validada com transações sintéticas (instrução Memo). No entanto, não realizou transações reais na mainnet por exigência de saldo mínimo ($5 USDC + SOL para gás).

### 3.5 Infraestrutura de Orquestração (`agentic-conversation/`)

O diretório `agentic-conversation/` implementa uma ponte bidirecional entre agentes de IA e Telegram:

1. **Relay HTTP (`local_relay.py`):**
   - Servidor HTTP leve executado localmente (porta 8787 por padrão), expondo endpoints REST (`POST /message`, `GET /events`, `GET /status`) sobre arquivos JSONL em disco (`~/.devin-local-relay/inbox.jsonl` e `outbox.jsonl`).
   - Permite comunicação segura via Tailscale/ngrok com autenticação via bearer token (`RELAY_TOKEN`).
2. **Bot Telegram (`devin_telegram/`):**
   - Roteador de comandos (`/new`, `/attach`, `/local`, `/queue`, `/flush`, `/status`, `/watch`), permitindo despachar tarefas para instâncias do Devin na nuvem ou processos locais no computador de desenvolvimento.
3. **Mapeamento para o Pipeline Quantitativo:**
   - Atualmente, esta camada opera de forma totalmente independente de `trading-engine/`. Os scripts de trading usam `telegram_alerts.py` ou `cloud_shadow_discord_monitor.py` de forma avulsa. O relay pode ser unificado para fornecer telemetria em tempo real das simulações empíricas dos novos vetores.

---

## 4. Mapeamento do Delta Exato: O que Existe vs o que é Exigido

Abaixo está o detalhamento técnico do delta necessário para elevar cada um dos 6 vetores arquitetônicos ao estado de software executável ponta a ponta e simulação empírica rigorosa.

```
+---------------------------------------------------------------------------------------------------+
|                                  ARQUITETURA DE DELTA QUANTITATIVO                                |
+---------------------------------------------------------------------------------------------------+
| 1. HYPERLIQUID H84:                                                                               |
|    Existe: Latency benchmark REST/WS + Script com parsing bug de l2Book                           |
|    Delta:  Emulador Gossip/Mempool + Conector EIP-712/msgpack + Flag ALO + Toxic Flow Filter      |
|                                                                                                   |
| 2. DRIFT / VELOCITY SWIFT H85:                                                                    |
|    Existe: Listener passivo @velocity-exchange/sdk em TS coletando msgs com desvio 2000bps        |
|    Delta:  Fix de escala de preço + Desduplicação + Submissão Maker Post-Only + Landing Slot Sim  |
|                                                                                                   |
| 3. SUI DEEPBOOKV3 H86:                                                                            |
|    Existe: Mapeamento de 16 pools + Script PTB execute com perna AMM ausente e carteira zerada    |
|    Delta:  PTB completa (Flashloan -> Swap DeepBook -> Swap AMM Cetus -> Repay) + DryRun Sim     |
|                                                                                                   |
| 4. KALSHI FIX H87:                                                                                |
|    Existe: Menções conceituais em docs + Rota de leitura via Jupiter prediction provider=kalshi   |
|    Delta:  Conector FIX 4.4/5.0 + Motor Mock/Emulador (Bypass KYC) + VenueAdapter Kalshi          |
|                                                                                                   |
| 5. dYdX v4 COMETBFT / L3:                                                                         |
|    Existe: NADA em código (apenas símbolo DYDXUSDT de spot shorting D17)                          |
|    Delta:  Conector Indexer WS/gRPC + Client Cosmos SDK + Nonce Manager + Simulador Lead-Lag     |
|                                                                                                   |
| 6. GMX v2 & CEXs TIER-2:                                                                          |
|    Existe: Auditorias D7/D8/D9/D32 em CEXs Tier-1 via REST (refutadas por latência 2.5s)          |
|    Delta:  Conector Chainlink Data Streams + Conectores WS MEXC & Gate.io + Simulador Oráculo-CEX |
+---------------------------------------------------------------------------------------------------+
```

### 4.1 Vetor 1 — Hyperliquid Mempool/Gossip (H84)
- **O que já existe:**
  - `trading-engine/h84_hyperliquid_gossip_feasibility.py` (código de conexão WS com URL `wss://api.hyperliquid.xyz/ws` e medições de latência REST).
  - Constantes de taxas: Maker rebate +0.1 bps (-0.001%), Taker fee 3.5 bps (0.035%).
  - Módulos auxiliares `hyperliquid_probe.py` e `hyperliquid_paper_bot.py` para funding rate.
- **O que falta para execução ponta a ponta:**
  - **Correção do parser de livro:** Atualizar a função de processamento de `l2Book` para desempacotar `data["levels"][0]` (bids) e `data["levels"][1]` (asks).
  - **Cliente Gossip ou Emulador de Mempool:** Como o nó validador completo exige servidor de $2.700/mês inacessível em ambiente de desenvolvimento, construir um emulador de fluxo de mempool (ou consumir stream de nó gossip remoto caso configurado) com injeção de atraso calibrado (70-150ms).
  - **Módulo de Assinatura EIP-712 / MsgPack:** Implementar empacotamento nativo de ordens `OrderRequest` (asset, isBuy, limitPx, sz, reducing, orderType com `{"limit": {"tif": "Alo"}}`).
  - **Mecânica de Proteção:** Flag Add-Liquidity-Only (ALO / Post-Only) mandatória para garantir que a ordem nunca pague taxa de taker de 3.5 bps.
  - **Filtro de Fluxo Tóxico:** Módulo que compara variações bruscas em exchanges líderes (Binance bookTicker via `BinanceVenue`) nos últimos 50-100ms para disparar cancelamentos imediatos antes que transações agressivas do mempool atinjam o livro.
  - **Simulação Empírica:** Mapear distribuição de fills hipotéticos contra trades reais e calcular PnL líquido deduzindo perdas de seleção adversa.

### 4.2 Vetor 2 — Drift / Velocity SWIFT Maker Rebate (H85)
- **O que já existe:**
  - Projeto TypeScript em `trading-engine/h85_drift/` configurado com `@velocity-exchange/sdk@0.6.1` e `@solana/web3.js`.
  - Conexão funcional com o feed SWIFT via `SwiftOrderSubscriber` em `h85_swift_subscriber.ts`.
  - Monitor contínuo `h85_continuous.sh` com histórico de mensagens capturadas.
- **O que falta para execução ponta a ponta:**
  - **Resolução da Escala e Decodificação de Parâmetros:** Tratar a decodificação exata do payload de leilão SWIFT: isolar `auctionStartPrice`, `auctionEndPrice`, `price` e `baseAssetAmount` usando as estruturas oficiais da Velocity (`SignedMsgOrderParamsMessage`), resolvendo o desvio aparente de 2000 bps contra a Coinbase.
  - **Deduplicação de Mensagens:** Filtro baseado no hash da assinatura (`signature`) da ordem do taker para ignorar retransmissões em múltiplos nós ou por delegados.
  - **Conector de Execução Maker:** Implementar o envio de transação de preenchimento (`place_order` ou `fill_order`) com flag `PostOnly` assinada localmente com Keypair da Solana.
  - **Projeção de Slot de Aterrissagem (Landing Slot):** O protocolo SWIFT casa ordens com validade condicionada ao slot Solana de inclusão. O módulo deve consultar o slot atual via RPC websocket (`slotSubscribe`) e projetar o slot futuro de confirmação.
  - **Simulador Empírico:** Medir a latência entre o recebimento da mensagem SWIFT e o tempo teórico de inclusão on-chain, calculando a taxa de sucesso de cancelamento/ajuste antes que o taker seja liquidado contra o livro.

### 4.3 Vetor 3 — Sui DeepBookV3 PTB / Hot Potato (H86)
- **O que já existe:**
  - Mapeamento on-chain completo de 16 pools e suas taxas em `h86_deepbook_onchain_results.json`.
  - Script gerador de carteira Ed25519 em `h86_setup_wallet.ts` e chave salva em `h86_sui/.env`.
  - Código parcial de Programmable Transaction Block em `h86_deepbook_execute.ts` demonstrando chamadas a `borrow_flashloan_quote` e `return_flashloan_quote`.
- **O que falta para execução ponta a ponta:**
  - **Correção Completa do Grafo da PTB:** Inserir a perna obrigatória de swap na AMM:
    1. `borrow_flashloan_quote(pool, amount)` → recebe `[borrowedCoin, receipt]`.
    2. `deposit(balanceManager, borrowedCoin)` → deposita USDC.
    3. `place_market_order(pool, balanceManager, amount, isBid=true)` → compra SUI.
    4. `withdraw(balanceManager, suiAmount)` → saca SUI do BalanceManager.
    5. **Perna AMM (Cetus / Turbos):** invocar `cetus_clmm::pool::swap` passando os tokens SUI e recebendo de volta tokens USDC com verificação estrita de `min_output`.
    6. `return_flashloan_quote(pool, returnedUsdcCoin, receipt)` → liquida o Hot Potato.
  - **Validação de Reversão Atômica:** Garantir que se a perna 5 gerar menos USDC do que o valor do empréstimo acrescido das taxas, a PTB aborte na execução do Move sem persistir alterações de saldo.
  - **Descoberta de Pools com Liquidez Real:** Identificar pares ativos (como SUI/USDC native emitido pela Circle em `0xdba3468e...`, em substituição ao pool defasado de WUSDC de ponte).
  - **Ativação da Carteira:** Financiar a carteira com SUI mínimo para taxa de transação e criar o objeto `BalanceManager`.
  - **Simulador Empírico sem Risco de Capital:** Utilizar a chamada RPC `sui_dryRunTransactionBlock` para simular a execução da PTB completa contra o estado atual da rede principal, inspecionando mudanças de saldo de balanço (`balanceChanges`) e custos exatos de gás.

### 4.4 Vetor 4 — Kalshi FIX / AWS PrivateLink (H87)
- **O que já existe:**
  - Mapeamento documental do protocolo Kalshi em `docs/venue_adapter_design.md` e `docs/phantom_ecosystem_findings.md`.
  - Adapter `JupiterPredictionVenue` em `trading-engine/venues/jupiter_prediction.py`, que já suporta consulta a mercados da Kalshi via rota proxy agregada (`provider=kalshi`).
- **O que falta para execução ponta a ponta:**
  - **Motor FIX Nativo:** Módulo cliente FIX (QuickFIX/Python ou parser binário/socket assíncrono puro) implementando mensagens da especificação Kalshi FIX: `Logon (35=A)`, `Heartbeat (35=0)`, `NewOrderSingle (35=D)`, `OrderCancelRequest (35=F)`, `ExecutionReport (35=8)` e `MarketDataRequest (35=V)`.
  - **Camada de Autenticação RSA:** Geração de assinatura criptográfica RSA SHA-256 com chave privada e timestamp para o handshake de login.
  - **Tratamento de Barreiras Regulatórias / Mock Emulator (Conforme R3 do Pedido Original):** Como a Kalshi exige KYC de residente dos EUA e credenciamento regulatório CFTC para acesso institucional via AWS PrivateLink, é mandatório construir um **servidor mock/emulador de FIX local**:
    - Deve responder às mensagens FIX padrão com latência parametrizável (1-10ms).
    - Permitir testar a máquina de estados, o envio de ordens e a reconciliação de preenchimentos sem bloqueios burocráticos.
  - **Conector de Venue:** Classe `KalshiVenue(ExecutionVenue)` registrada em `trading-engine/venues/`.
  - **Simulador de Lead-Lag:** Comparar movimentações de probabilidade da Kalshi contra o livro subjacente ou contra a Polymarket via Jupiter API para calcular o edge líquido.

### 4.5 Vetor 5 — dYdX v4 CometBFT / Layer 3
- **O que já existe:**
  - Nenhuma linha de código referente ao protocolo dYdX v4.
- **O que falta para execução ponta a ponta:**
  - **Compreensão Arquitetônica:** dYdX v4 opera como uma app-chain Cosmos SDK autônoma com consenso CometBFT. O livro de ofertas de alta frequência reside na memória volátil dos validadores (off-chain matching) e os blocos são gerados a cada ~1.0-1.5s para liquidação on-chain.
  - **Conector de Market Data:** Cliente WebSocket conectado ao Indexer da dYdX v4 (`wss://indexer.dydx.trade/v4/ws`), consumindo canais `v4_markets`, `v4_orderbook` e `v4_trades`.
  - **Módulo de Execução e Assinatura:** Conector baseado em transações Cosmos SDK (usando chaves secp256k1 e protobuf), assinando mensagens `MsgPlaceOrder` com controle rigoroso de `subaccountId`, `clientId`, `orderFlags` (Short-Term vs Long-Term) e `goodTilOneof` (para evitar ordens zumbi).
  - **Mitigação de Latência:** Como as ordens de curto prazo (Short-Term Orders) não pagam taxa de gás on-chain mas expiram em poucos blocos, implementar gerenciamento assíncrono de nonces e reconciliação rápida.
  - **Conector de Venue:** Classe `DydxV4Venue(ExecutionVenue)` integrada em `trading-engine/venues/`.
  - **Simulação Empírica:** Mapear lead-lag dos preços de futuros perpétuos da dYdX v4 contra Binance/Hyperliquid em ticks de alta volatilidade.

### 4.6 Vetor 6 — GMX v2 Data Streams & CEXs Tier-2 (MEXC / Gate.io)
- **O que já existe:**
  - Relatórios de auditoria D7 e D32 documentando que CEX-CEX em Tier-1 (Binance vs Bybit vs OKX) tem spread nulo (0-4 bps) e que REST API é inviável (2.5s).
- **O que falta para execução ponta a ponta:**
  - **Módulo GMX v2 & Chainlink Data Streams:**
    - GMX v2 não usa orderbook tradicional nem AMM pura; utiliza oráculos de baixa latência assinados off-chain pela rede descentralizada da Chainlink (Data Streams).
    - O trader submete uma intenção de ordem on-chain (`CreateOrder`), e os Keepers executam a ordem injetando a cotação assinada fresca da Chainlink.
    - O vetor de arbitragem consiste em identificar quando os relatórios do Chainlink Data Stream apresentam atraso de propagação em relação ao bookTicker das CEXs líderes durante picos de momentum.
  - **Conectores WebSocket para CEXs Tier-2:**
    - **MEXC:** Conector WebSocket para `wss://wbs.mexc.com/ws` (canal `spot@public.bookTicker.v3.api` ou perpétuos), explorando política de taxas agressiva (0% maker em vários pares).
    - **Gate.io:** Conector WebSocket para `wss://fx-ws.gateio.ws/v4/ws` ou `wss://api.gateio.ws/ws/v4/` (canal `futures.book_ticker`).
    - **Tese do Tier-2:** Exchanges menores sofrem de menor presença institucional de formadores de mercado de ultra-baixa latência (co-location), permitindo que disparos de preço originados na Binance demorem de 50ms a 300ms para se refletirem nos livros locais.
  - **Motor de Execução e Arbitragem:**
    - Módulo que escuta simultaneamente Binance WS, MEXC WS, Gate.io WS e Chainlink Stream, calculando o spread transitório líquido de taxas de taker (ex: 2 bps na MEXC, 5 bps na Gate.io).
  - **Simulador Empírico:** Gravação sincronizada de múltiplos feeds em alta frequência com análise de valor esperado líquido usando `stats_utils.py`.

---

## 5. Auditoria de Dependências e Ambiente de Execução

1. **Python (`trading-engine/`):**
   - Python 3.13 / virtualenv ativo.
   - Bibliotecas instaladas e verificadas: `websockets`, `requests`, `python-dotenv`, `solders` (para Solana), `base58`.
   - Utilitários reutilizáveis: `stats_utils.py` (essencial para intervalos de confiança Wilson e Bootstrap), `risk_guardrails.py`, `telegram_alerts.py`.
2. **Node.js / TypeScript (`trading-engine/h85_drift/`, `h86_sui/`):**
   - Node.js v20+ / `tsx` / `typescript`.
   - Pacotes instalados:
     - `@solana/web3.js`
     - `@drift-labs/sdk` / `@velocity-exchange/sdk` (em `h85_drift`)
     - `@mysten/sui` v1.20+, `@mysten/deepbook-v3` v1.5+ (em `h86_sui`)
3. **Contas e Credenciais Presentes no Workspace:**
   - `.env` principal em `trading-engine/`: contém tokens de API Deriv, chaves Jupiter e Solana (Phantom).
   - `.env` em `trading-engine/h86_sui/`: contém par de chaves da Sui (`SUI_PRIVATE_KEY` e `SUI_WALLET_ADDRESS`), aguardando saldo.
   - `.env` em `agentic-conversation/`: configuração do Telegram bot.

---

## 6. Conclusões e Recomendações Técnicas para os Próximos Passos

1. **Correção Imediata dos Bugs Críticos Identificados:**
   - No **H84**, corrigir a rotina de desempacotamento de arrays da mensagem WebSocket `l2Book` da Hyperliquid para destravar a captura de spreads e book updates.
   - No **H85**, ajustar os divisores de precisão numérica e o parsing de parâmetros do leilão SWIFT na Velocity para eliminar a falsa distorção de 2000 bps.
   - No **H86**, reestruturar a PTB em TypeScript para incluir a perna de troca SUI → USDC em AMM (Cetus) antes da quitação do empréstimo relâmpago, validando tudo via simulação `sui_dryRunTransactionBlock`.
2. **Estratégia para H87, dYdX v4 e GMX/CEX Tier-2:**
   - Para o **H87 (Kalshi)**, implementar o adaptador com suporte dual: conexão ao emulador mock local FIX para desenvolvimento e testes empíricos de latência sem restrições regulatórias, e compatibilidade com a rota Jupiter Prediction API para consumo prático de dados.
   - Para o **dYdX v4**, construir o conector indexer WS + simulador de envio com ordens short-term.
   - Para o **GMX v2 e CEXs Tier-2**, implementar a captura concorrente via WebSocket da Binance, MEXC e Gate.io com cálculo contínuo de divergência e simulação de PnL líquido.
3. **Integração ao Venue Adapter:**
   - Todas as novas interfaces devem herdar de `PriceFeedVenue` e `ExecutionVenue` em `trading-engine/venues/base.py`, mantendo a assinatura limpa do ecossistema e preservando a integridade do código em produção.

---
*Relatório de auditoria concluído e verificado contra os artefatos locais do repositório.*
