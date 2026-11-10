# Relatório Mestre de Auditoria Técnica: Inteligência Quantitativa, Microestrutura e Latência

**Projeto:** Quantitative Intelligence & Market Microstructure Architecture  
**Documento:** Master Technical Audit, Bug Post-Mortems, and Cross-Venue Feasibility Synthesis  
**Autor:** Equipe de Pesquisa & Engenharia Quantitativa (Consolidação de Surveys 1, 2 e 3)  
**Data da Auditoria:** 2026-11-03  
**Status:** Auditado, Retificado e Pronto para Implementação de Software  

---

## 1. Sumário Executivo

Este relatório consolida a auditoria técnica exaustiva dos seis vetores de microestrutura de mercado e latência propostos no projeto:
1. **Hyperliquid (H84)**: Mempool gossip stream L1, flag Post-Only (ALO), EIP-712 e mitigação de fluxo tóxico.
2. **Velocity Exchange / Drift Protocol (H85)**: Stream de intenção de takers SWIFT via WebSocket, leilão holandês $P(t)$, rebate maker de 0.25 bps e deduplicação.
3. **Sui DeepBookV3 (H86)**: Programmable Transaction Blocks (PTB), Hot Potato flash loan (taxa de 0.0%), pools nativos de USDC da Circle e reversão atômica de perna AMM.
4. **Kalshi FIX (H87)**: Conectividade institucional FIXT.1.1/FIX50SP2, autenticação Ed25519/RSA Tag 96, conformidade CFTC DCM Rule 38 e emulação mock de alta fidelidade.
5. **dYdX v4**: Consenso CometBFT, livro de ofertas em memória (MemCLOB), zero gás para ordens/cancelamentos e telemetria L3 de nós completos.
6. **GMX v2 & CEXs Tier-2 (MEXC / Gate.io)**: Oráculos pull de baixa latência Chainlink Data Streams, guardrail de slippage `acceptablePrice`, dinâmica de oráculo assíncrono em duas etapas e execução sintética delta-neutra.

### Principais Conclusões e Retificações de Falhas Anteriores do Repositório:
- **H84 (Hyperliquid)**: O nó não-validador com `split_client_blocks: true` de fato grava transações do mempool em disco (`~/hl/data/mempool_txs/{YYYY-MM-DD}`) com vantagem de **70ms a 150ms** sobre o WebSocket público de trades. Contudo, essa vantagem é **completamente anulada se operada fora de Tóquio** (a latência transpacífica us-east-2 → ap-northeast-1 adiciona ~150ms de RTT base). Além disso, a simulação anterior de H84 (`h84_hyperliquid_gossip_feasibility.py`) continha um **bug crítico de parsing no canal `l2Book`**, resultando em 0 atualizações de livro e 0 fills simulados. Em termos de custos, makers no Tier 0 pagam taxa positiva de +1.5 bps; rebates exigem Tier 4+ institucional ($500M+ volume).
- **H85 (Velocity / Drift)**: O protocolo migrou formalmente do pacote depreciado `@drift-labs/sdk` para `@velocity-exchange/sdk@0.6.1+` (Program ID Solana: `vELoC1audYbSYVRXn1vPaV8Axoa9oU6BYmNGZZBDZ1P`), adotando Solana USDT nativo como ativo de cotação. O suposto "desvio tóxico de 2000 bps" registrado no repositório foi um **artefato de decodificação de leilão**: o script anterior inspecionou o parâmetro `price` (que é o limite final do leilão $P_{\text{end}}$) em vez de calcular dinamicamente a curva de leilão holandês $P(t) = P_{\text{start}} + \frac{t}{D}(P_{\text{end}} - P_{\text{start}})$. O rebate de maker é fixo em **0.25 bps (0.0025%)**.
- **H86 (Sui DeepBookV3)**: O veredito anterior de "REFUTADA por iliquidez" foi causado por **consultar pools abandonados de Wormhole USDC (`wUSDC`) e usar um tipo dummy sintetizado**. A liquidez ativa reside no pool de USDC nativo emitido pela Circle (`0xe05dafb5133bcffb8d59f4e12465dc0e9faeaa05e3e342a08fe135800e3e4407`). O script anterior `h86_deepbook_execute.ts` continha uma **falha lógica fatal**: comprava SUI com USDC emprestado e tentava sacar USDC do `BalanceManager` sem implementar o swap de volta na AMM (Cetus/Turbos), impossibilitando o fechamento do Hot Potato. O flash loan do DeepBookV3 cobra **0.00% (0 bps)** e reverte com custo de gás desprezível (~0.002 SUI) se a perna AMM for desfavorável.
- **H87 (Kalshi FIX)**: A Kalshi é uma corretora regulada pela CFTC (DCM) nos EUA. Exige KYC estrito (SSN, comprovante de residência nos EUA, banco via Plaid) sob a Regra 38 da CFTC para negociação ao vivo. Acesso via AWS PrivateLink em `us-east-1` é restrito a clientes institucionais Premier/Prime. Para desbloquear o pipeline de desenvolvimento e testes empíricos automatizados, a solução arquitetural consiste em operar com suporte dual: conexão ao gateway Demo oficial e implementação de um **servidor mock FIXT.1.1/FIX50SP2 de alta fidelidade**.

---

## 2. Análise Técnica Profunda dos 6 Vetores Arquitetônicos

### 2.1 Vetor 1: Hyperliquid (H84) — Mempool Gossip, EIP-712 e Toxic Flow

#### Arquitetura de Consenso & Mecânica de Rede
- **Motor de Consenso:** HyperBFT, motor BFT proprietário em C++/Rust que atinge intervalos de bloco de ~200ms com finalidade determinística em slot único.
- **Transição de Estado L1:** Desenvolvido nativamente para derivativos perpétuos em CLOB, desacoplado da EVM para execução de alta frequência.
- **Rede P2P de Fofoca (Gossip Protocol):**
  - O binário oficial `hl-node` escuta nas portas TCP/UDP **4001** e **4002**. É imperativo que ambas estejam abertas publicamente para evitar depriorização por nós vizinhos.
  - O parâmetro `"split_client_blocks": true` no arquivo `~/override_gossip_config.json` força o nó a bifurcar a ingestão de blocos:
    1. Grava transações de clientes pré-consenso no disco em `~/hl/data/mempool_txs/{YYYY-MM-DD}` assim que chegam via gossip.
    2. Aplica o bloco finalizado em `~/hl/data/blocks/{YYYY-MM-DD}` após o término da rodada de consenso.
  - Essa bifurcação fornece uma vantagem de observabilidade direta de **70ms a 150ms** antes que a confirmação seja transmitida nos feeds públicos de WebSocket (`trades` e `l2Book`).

#### Mitigação de Fluxo Tóxico (Toxic Flow Avoidance)
- **Problema de Microestrutura:** Ordens a mercado agressivas (takers) ou liquidações forçadas varrem as primeiras faixas do livro de ofertas. Formadores de mercado passivos sofrem seleção adversa sistemática caso suas ordens limite de compra ou venda permaneçam descansando no livro durante o impacto.
- **Mecanismo de Defesa do Mempool:**
  1. Monitoramento do fluxo de arquivo ou anel de memória compartilhada de `~/hl/data/mempool_txs/{date}`.
  2. Ao identificar uma transação agressiva pendente cujo tamanho (`sz`) exceda o limiar de toxicidade e cuja direção seja oposta à da ordem do formador de mercado, o algoritmo despacha imediatamente um cancelamento via socket local ou RPC de nó validador.
  3. O cancelamento chega e é incluído no mesmo lote de propostas do validador, neutralizando a execução contra a ordem passiva.

#### Políticas de Ordem e Flags Post-Only (ALO)
Para garantir que o formador de mercado nunca pague taxas de taker por cruzamento acidental de spread, a API da Hyperliquid exige a flag `Alo` (Add Liquidity Only) na estrutura `order_type`:
```json
{
  "coin": "SOL",
  "is_buy": true,
  "sz": 1.0,
  "limit_px": 145.50,
  "reduce_only": false,
  "order_type": {
    "limit": {
      "tif": "Alo"
    }
  },
  "cloid": "0x0123456789abcdef0123456789abcdef"
}
```
Se a ordem cruzar o spread no momento da chegada, ela é imediatamente cancelada pelo motor da exchange sem cobrança de taxas. O identificador `cloid` (128-bit hex) permite rastreamento idempotente sem depender de IDs internos alocados pelo servidor.

#### Estrutura de Custos e Rebates de Liquidez
As taxas são calculadas sobre o volume móvel de 14 dias (`Perps Volume + 2 * Spot Volume`):
- **Tier 0 (< $5M):** Taker 4.5 bps | **Maker +1.5 bps (Taxa a Pagar)**
- **Tier 1 (≥ $5M):** Taker 4.0 bps | **Maker +1.2 bps**
- **Tier 2 (≥ $25M):** Taker 3.5 bps | **Maker +0.8 bps**
- **Tier 3 (≥ $100M):** Taker 3.0 bps | **Maker +0.4 bps**
- **Tier 4 (≥ $500M):** Taker 2.8 bps | **Maker 0.0 bps**
- **Tier 5 (≥ $2B):** Taker 2.6 bps | **Maker 0.0 bps**
- **Tier 6 (≥ $7B):** Taker 2.4 bps | **Maker 0.0 bps**

*Alerta Crucial de Engenharia:* Contas de varejo (Tier 0 a 3) **pagam** para atuar como maker. Para auferir rebates reais (taxas negativas como -0.1 bps), é mandatório celebrar acordos institucionais do Market Maker Program ou alcançar volumes institucionais Tier 4+. Em contas padrão, a estratégia só é viável se o spread médio capturado superar o custo combinado de ida e volta (> 3.0 bps).

#### Requisitos de Infraestrutura e Co-locação
- **Sistema Operacional:** Ubuntu 24.04 LTS obrigatório.
- **Hardware Mínimo para Nó Não-Validador:** 16 vCPUs, 128 GB de memória RAM, 500 GB NVMe SSD (instância AWS recomendada: `c7i.8xlarge` ou `c7i.16xlarge`, ~$1.500 a $2.700/mês).
- **Localização dos Validadores:** A esmagadora maioria dos nós validadores da Hyperliquid opera em **Tóquio, Japão** (`ap-northeast-1` / Equinix TY3/TY11). Operar a partir dos EUA (`us-east-2`) impõe um RTT de rede de ~150ms, o que destrói completamente a vantagem de 70-150ms obtida pelo mempool gossip.

---

### 2.2 Vetor 2: Drift Protocol / Velocity Exchange (H85) — SWIFT WebSocket Rebate

#### Migração Oficial do Ecossistema
Em julho de 2026, a infraestrutura de derivativos de alto desempenho do Drift Protocol migrou para a **Velocity Exchange**:
- **Pacote Legado:** `@drift-labs/sdk` (descontinuado para novos mercados).
- **Pacote Ativo:** `@velocity-exchange/sdk@0.6.1+` (TypeScript).
- **Program ID Solana:** `vELoC1audYbSYVRXn1vPaV8Axoa9oU6BYmNGZZBDZ1P`.
- **Ativo de Cotação:** **Solana USDT Nativo** (`Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB`), substituindo o USDC nos mercados principais da mainnet.

#### Feed de Intenções de Takers SWIFT (Pre-Confirmation Preview)
- **Endpoint Mainnet:** `wss://swift.velocity.exchange/ws?pubkey=<WALLET_PUBKEY>`
- **Endpoint Devnet:** `wss://swift.master.velocity.exchange/ws?pubkey=<WALLET_PUBKEY>`
- **Classe do SDK:** `SwiftOrderSubscriber`.
- **Vantagem Temporal:** O feed SWIFT transmite mensagens de intenção de ordens de takers assinadas criptograficamente off-chain de **100ms a 500ms antes** de sua confirmação on-chain pelos validadores da Solana.
- **Autenticação:** Aberta a qualquer carteira Solana via assinatura Ed25519 do nonce transmitido no canal `auth` durante o handshake TLS.

#### Dinâmica do Leilão Holandês (Dutch Auction) e Resolução de Escala
As ordens de mercado e de liquidação no SWIFT são processadas como leilões holandeses decrescentes/crescentes para maximizar o preenchimento:
- **Precisões Oficiais:**
  - `PRICE_PRECISION`: $10^6$ (`1e6`)
  - `BASE_PRECISION`: $10^9$ (`1e9`)
  - `QUOTE_PRECISION`: $10^6$ (`1e6`)
- **Fórmula de Preço Instantâneo $P(t)$:**
  Para uma ordem no instante de tempo transcorrido $t \in [0, D]$, onde a duração do leilão é $D = \text{auctionDuration} \times 400\text{ms}$:
  $$P(t) = P_{\text{start}} + \frac{t}{D} \cdot (P_{\text{end}} - P_{\text{start}})$$
- **Retificação do Bug de 2000 bps:**
  No código legado `h85_swift_subscriber.ts`, o script comparava o campo `params.price` (que é $P_{\text{end}}$, o limite de proteção final do leilão) contra o preço spot da Coinbase. Um taker vendendo SOL definia $P_{\text{start}} = \$75.00$ e $P_{\text{end}} = \$60.00$. O script avaliava a ordem como um trade imediato a $\$60.00$, classificando erroneamente 100% das ordens como anomalias tóxicas. Ao calcular $P(t)$ no slot projetado de execução, o preço converge com a cotação justa de mercado.

#### Instrução On-Chain e Alinhamento de Precompiles Ed25519
Para casar a ordem como formador de mercado contra a intenção do taker, o maker invoca a instrução Solana `placeAndMakeSignedMsgPerpOrder`:
- A transação precisa incluir uma instrução nativa `Ed25519Program.createInstructionWithPublicKey` que valida a assinatura de 64 bytes do taker em relação ao payload serializado.
- **Armadilha de Implementação (`precedingIxs`):** O SDK da Velocity calcula o deslocamento da instrução Ed25519 relativo à lista de instruções da transação. Se o algoritmo adicionar instruções de computação de prioridade (`ComputeBudgetProgram.setComputeUnitPrice`), elas **devem ser passadas no array `precedingIxs`**. Omitir esse argumento faz com que a verificação de assinatura aponte para um índice errado no runtime da Solana, provocando falha silenciosa ou reversão on-chain.

#### Rebate de Maker e Corrida de Desduplicação (Jito Auctions)
- **Rebate:** O formador de mercado recebe um rebate plano de **0.25 bps (0.0025%)** sobre o valor nocional preenchido, debitado diretamente da taxa do taker.
- **Corrida de Inclusão:** Todas as firmas conectadas ao WebSocket recebem o mesmo pacote de ordem simultaneamente. Múltiplos makers geram transações competindo pelo mesmo slot. Apenas a primeira transação confirmada tem sucesso; as subsequentes falham com `OrderAlreadyFilled`.
- **Mitigação:** Implementação de cache LRU de desduplicação (`Set<signature>`) e empacotamento via Jito Bundles para garantir inclusão atômica sem desperdício de taxas em transações rejeitadas.

---

### 2.3 Vetor 3: Sui DeepBookV3 (H86) — Flash Loan Hot Potato e PTB Atômico

#### Arquitetura de Programmable Transaction Blocks (PTB)
- **ID do Pacote Core (Mainnet):** `0xdee9` (ou `0xbca0cefe720330e7bb4f2283438b68de6a0e656688db4ac90d61e71fe6151fe8`).
- **Capacidade do PTB:** Executa até 1.024 comandos Move sequenciais em uma única transação atômica. Variáveis e moedas circulam diretamente entre comandos sem escrita em storage persistente intermediário.
- **Reversão com Custo Mínimo:** Se qualquer asserção ou comando falhar dentro do PTB (ex: saída do swap insuficiente para pagar o empréstimo), **a transação inteira é abortada pela VM da Sui**, consumindo apenas o gás de execução computacional (~0.002 SUI = frações de centavo). Não há risco de perna órfã.

#### O Padrão "Hot Potato" em Flash Loans
A struct Move `FlashLoan` do DeepBook V3 é definida com zero abilities:
```move
public struct FlashLoan<phantom BaseAsset, phantom QuoteAsset> {
    pool_id: ID,
    borrow_quantity: u64,
    type_asset: u8,
}
```
Como não possui `copy`, `drop`, `store` ou `key`, a struct não pode ser descartada, duplicada nem mantida em estado global. A VM da Sui exige que ela seja obrigatoriamente consumida antes do término do PTB pela função correspondente:
- Empréstimo: `deepbook::pool::borrow_flashloan_quote` (ou `base`).
- Quitação: `deepbook::pool::return_flashloan_quote` (ou `base`).
- **Taxa do Empréstimo:** Exatamente **0.00% (0 bps)**.

#### Migração de RPC e Pools Ativos de Liquidez
- **Descontinuação do JSON-RPC:** Servidores públicos da Sui retornam código de erro `-32601` para métodos legados (`sui_getObject`). A comunicação deve obrigatoriamente utilizar **GraphQL** (`https://graphql.mainnet.sui.io/graphql`) ou **gRPC** (`sui-grpc.publicnode.com:443`).
- **Pools Oficiais Líquidos:**
  - Token USDC Nativo (Circle): `0xdba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7::usdc::USDC`
  - Token DEEP: `0xdeeb7a4662eec9f2f3def03fb937a663dddaa2e215b8078a284d026b7946c270::deep::DEEP`
  - Pool `SUI_USDC`: `0xe05dafb5133bcffb8d59f4e12465dc0e9faeaa05e3e342a08fe135800e3e4407`
  - Pool `DEEP_SUI`: `0xb663828d6217467c8a1838a03793da896cbe745b150ebd57d82f814ca579fc22`
  - Pool `DEEP_USDC`: `0xf948981b806057580f91622417534f491da5f61aeaf33d0ed8e69fd5691c95ce`

#### Pipeline Completo de Arbitragem sem Risco de Perna
O fluxo atômico em 8 etapas do PTB:
1. `borrow_flashloan_quote`: Toma $Q$ USDC do DeepBookV3 `SUI_USDC` -> retorna `[borrowedCoin, flashLoanReceipt]`.
2. `cetus::pool::swap`: Troca $Q$ USDC por $S$ SUI na AMM Cetus/Turbos -> retorna `suiCoin`.
3. `deepbook::balance_manager::deposit`: Deposita $S$ SUI no Balance Manager do DeepBook.
4. `deepbook::pool::place_market_order`: Vende $S$ SUI no livro CLOB do DeepBook recebendo $Q'$ USDC no Balance Manager.
5. `deepbook::balance_manager::withdraw`: Saca $Q'$ USDC do Balance Manager.
6. `split_coin`: Divide $Q'$ USDC em $Q$ (reembolso exato) e $\Delta Q = Q' - Q$ (lucro líquido).
7. `return_flashloan_quote`: Entrega $Q$ USDC e `flashLoanReceipt`, liquidando o Hot Potato.
8. `transfer_coin`: Envia $\Delta Q$ para a carteira do operador.
*Garantia Mecânica:* Se $Q' < Q$, o passo 6 aborta por saldo insuficiente, a função do passo 7 nunca é chamada, o Hot Potato permanece em aberto e a VM da Sui reverte 100% da transação.

---

### 2.4 Vetor 4: Kalshi FIX Protocol & AWS PrivateLink (H87)

#### Estrutura Regulada CFTC e Microestrutura de Mercado
- **Enquadramento Legal:** A Kalshi é um Designated Contract Market (DCM) registrado e regulado pela Commodity Futures Trading Commission (CFTC) nos termos do Commodity Exchange Act (CEA).
- **Especificação dos Contratos:** Contratos binários de eventos com liquidação estrita a **$1.00** para desfecho favorável (YES) ou **$0.00** para desfecho desfavorável (NO).
- **Faixas de Preço:** Cotados em centavos inteiros de **$0.01 a $0.99** (1¢ a 99¢). Tamanho de tick de $0.01.
- **Motor de Execução:** CLOB determinístico com prioridade preço-tempo.

#### Especificação do Protocolo FIX
- **Padrão de Transporte:** **FIXT.1.1** com camada de aplicação **FIX50SP2** sobre TLS 1.2+.
- **Sessões e Portas (TargetCompID):**
  - Porta 8228: `KalshiNR` (Non-Retransmission) — Entrada de ordens de ultra-baixa latência sem persistência de sequência.
  - Porta 8230: `KalshiRT` (Retransmission) — Entrada de ordens com recuperação de estado via `ResendRequest`.
  - Porta 8233: `KalshiMD` (Market Data) — Livro de ofertas institucional snapshot/incremental.
  - Porta 8229: `KalshiDC` (Drop Copy) — Feed de auditoria e reconciliação de risco pós-trade.
- **Identificação da Corretora (`SenderCompID`):** UUID da chave de API (ex: `a1b2c3d4-e5f6-7890-abcd-ef0123456789`).
- **Autenticação no Logon (`35=A`):**
  - Tag 98 (`EncryptMethod`): `0` (None).
  - Tag 96 (`RawData`): Assinatura Base64 do timestamp de logon (ou string pré-hash) gerada via Ed25519 ou RSA-2048 (SHA256-PSS).
  - **Regra Rígida de Sintaxe:** Enviar a Tag 50 (`SenderSubID`) na mensagem de Logon acarreta desconexão instantânea com `35=5 Logout`. A Tag 50 só pode ser informada em mensagens transacionais (`35=D`, `35=F`).
  - **Concorrência Única:** Apenas **uma sessão FIX ativa é permitida por API Key ID**. Conexões concorrentes disparam `35=5 Logout (Text: "already exists")`.

#### Conectividade AWS PrivateLink
- **Roteamento Privado:** Conexão direta aos gateways de ordens e dados através de endpoints de interface VPC na região AWS **`us-east-1`** (N. Virginia), contornando roteadores públicos, trânsito de internet e proxies Cloudflare.
- **Perfil de Latência:** RTT sub-milissegundo (~0.8ms) versus 25ms a 65ms na internet pública.
- **Barreira de Acesso:** Exclusivo para contas institucionais Premier/Prime com whitelisting manual de AWS Account ID junto à equipe de infraestrutura da Kalshi.

#### Barreiras Regulatórias e Abordagem de Emulação Mock
Sob a Regra 38 da CFTC, a negociação de contratos ao vivo exige KYC/AML individual obrigatório (SSN, comprovante de residência nos EUA, verificação bancária via Plaid). Investidores e desenvolvedores que não possuam cidadania ou residência formal nos EUA não podem operar na conta live.
Portanto, a solução arquitetural mandatória compreende:
1. Conexão pública à API de demonstração oficial (`demo-api.kalshi.co` e `fix.demo.kalshi.co:8228`).
2. Desenvolvimento de um **Servidor Mock FIXT.1.1/FIX50SP2 local** que emula fielmente o ciclo de vida de sessões, processa ordens limite e gera `ExecutionReport (35=8)` para validação contínua e sem bloqueios no pipeline de CI/CD.

---

### 2.5 Vetor 5: dYdX v4 (CometBFT / L3 MemCLOB)

#### Arquitetura Cosmos SDK & MemCLOB
- **Motor de Consenso:** CometBFT (BFT Proof-of-Stake) com blocos de ~0.8s a 1.1s e finalidade instantânea de slot único.
- **Livro em Memória (MemCLOB):** Ao contrário de blockchains EVM, os livros de ofertas ativas da dYdX v4 residem **exclusivamente na memória RAM** dos nós validadores.
- **Zero Gás em Operações de Ordens:** A criação, edição e cancelamento de ordens são transmitidos via gossip ponto-a-ponto entre validadores e **não cobram taxas de gás on-chain**.
- **Ciclo de Empacotamento de Blocos:**
  1. Ordens de curto prazo (Short-Term Orders) chegam ao validador e são propagadas na rede.
  2. O proponente do bloco emparelha as ordens deterministicamente na memória volátil.
  3. O bloco proposto inclui apenas os fills casados e as mutações de saldo de margem.
  4. A rede valida e comete o bloco com $\ge 2/3$ de consenso.

#### Telemetria Level 3 (L3)
- O Indexador público (`wss://indexer.dydx.trade/v4/ws`) fornece snapshots e atualizações agregadas Level 2 (market-by-price).
- Telemetria Level 3 em tempo real (dados discretos de cada ordem individual, posições na fila do livro e cancelamentos em milissegundos) exige a execução de um nó completo local com a flag `websocket-streaming-enabled` ou streaming gRPC direto na porta `9090`.

#### Tabela de Taxas e Escala de Rebates
Calculada dinamicamente sobre o volume móvel de 30 dias em USD:
- **Tier 1 (< $1M):** Taker 5.0 bps | **Maker +1.0 bps**
- **Tier 2 (≥ $1M):** Taker 4.5 bps | **Maker +1.0 bps**
- **Tier 3 (≥ $5M):** Taker 4.0 bps | **Maker +0.5 bps**
- **Tier 4 (≥ $25M):** Taker 3.5 bps | **Maker 0.0 bps**
- **Tier 5 (≥ $50M):** Taker 3.0 bps | **Maker 0.0 bps**
- **Tier 6 (≥ $100M):** Taker 2.5 bps | **Maker -0.7 bps (Rebate)**
- **Tier 7 (≥ $200M):** Taker 2.5 bps | **Maker -1.1 bps (Rebate)**

---

### 2.6 Vetor 6: GMX v2 & CEXs Tier-2 (MEXC / Gate.io)

#### Oráculo Pull Chainlink Low-Latency Data Streams
- No GMX v1, o oráculo tradicional "push" transmitia preços na Arbitrum com atraso de 1 a 3 segundos, permitindo que traders fizessem frontrunning de choques originados em CEXs.
- No GMX v2, essa assimetria foi eliminada via **Chainlink Data Streams** (oráculo "pull"): relatórios de alta frequência assinados criptograficamente off-chain por uma rede descentralizada de oráculos (DON).
- **Execução em Duas Etapas:**
  1. `OrderCreated`: O usuário emite a intenção de negociação comprometendo a margem e o parâmetro `acceptablePrice` (teto ou piso de slippage).
  2. `ExecuteOrder`: Bots mantenedores (keepers) recuperam o relatório assinado mais recente da Chainlink com carimbo de tempo compatível e liquidam a ordem na Arbitrum. Se o mercado ultrapassar `acceptablePrice`, a ordem é abortada sem preenchimento adverso.

#### Microestrutura e Latência em CEXs Tier-2
- **MEXC Global:** Oferece taxas agressivas de spot maker a **0.00%** e taker a 5 bps. O WebSocket (`wss://wbs.mexc.com/ws`) encerra a conexão após 30 segundos de inatividade caso canais de bookTicker não sejam assinados imediatamente.
- **Gate.io (API v4):** O protocolo WebSocket v4 (`wss://api.gateio.ws/ws/v4/`) suporta inserção e cancelamento de ordens diretamente via socket, reduzindo a latência de trânsito em **30% em Spot** e **40% em Futuros** comparado a requisições REST tradicionais. Contudo, impõe controles rigorosos de Order-to-Trade Ratio (OTR) para penalizar estratégias de spam de cancelamentos.
- **Atraso Estrutural de Transferência de Capital:**
  Arbitragem física (comprar no DEX e transferir para a CEX para vender) sofre com tempos de processamento de saque e loteamento em carteiras frias de **5 a 30 minutos** na MEXC e Gate.io.
  *Diretriz Estratégica:* A captura de edge deve operar exclusivamente sob o modelo **sintético delta-neutro** (manter margem pré-alocada em ambos os ambientes e executar posições opostas de perpétuos ou pares sintéticos simultaneamente).

---

## 3. Registro de Timestamps e Linhagem das Fontes Oficiais

| Protocolo / Ferramenta | Fonte Oficial / Repositório | Identificador de Versão / Tag | Timestamp de Consulta |
| :--- | :--- | :--- | :--- |
| **Hyperliquid L1** | `github.com/hyperliquid-dex/node` | Ubuntu 24.04 specs, Ports 4001/4002 | 2026-11-03T04:32:00Z |
| **Hyperliquid API** | `hyperliquid.gitbook.io/hyperliquid-docs` | API v1, ALO TIF, Gossip Mempool | 2026-11-03T04:32:00Z |
| **Velocity Exchange** | `@velocity-exchange/sdk` (npm) | `v0.6.1` / Program `vELoC1...` | 2026-11-03T04:32:00Z |
| **Velocity SWIFT** | `docs.velocity.exchange` | Dutch Auction $P(t)$, 0.25 bps rebate | 2026-11-03T04:32:00Z |
| **Sui DeepBook V3** | `github.com/MystenLabs/deepbookv3` | Move Packages, Hot Potato Flash Loan | 2026-11-03T04:32:00Z |
| **DeepBook TS SDK** | `@mysten/deepbook-v3` (`constants.ts`) | USDC Circle `0xdba34672...`, SUI `0xe05dafb5...` | 2026-11-03T04:32:00Z |
| **Sui RPC Migration** | `docs.sui.io/develop/accessing-data` | JSON-RPC Deprecation, GraphQL/gRPC | 2026-11-03T04:37:00Z |
| **Kalshi FIX** | `kalshi-fix.mintlify.app` | FIXT.1.1 / FIX50SP2, Ed25519 Tag 96 | 2026-11-03T04:32:00Z |
| **Kalshi Regulatory** | CFTC DCM Rule 38 filings | CFTC Event Contracts, US KYC/AML | 2026-11-03T04:37:00Z |
| **dYdX v4 Chain** | `github.com/dydxprotocol/v4-chain` | Cosmos SDK `x/clob`, MemCLOB RAM | 2026-11-03T04:32:00Z |
| **dYdX Indexer** | `indexer.dydx.trade/v4` | Sub-100ms orderbooks, L3 gRPC spec | 2026-11-03T04:37:00Z |
| **GMX v2** | `gmxio.gitbook.io/gmx/v/v2/` | Chainlink Data Streams, 2-step router | 2026-11-03T04:32:00Z |
| **Gate.io API v4** | `gate.io/docs/developers/apiv4/` | WebSocket v4 Trading, OTR Monitor | 2026-11-03T04:32:00Z |
| **MEXC Developer** | `mexcdevelop.github.io/apidocs/` | Spot v3 REST / WebSocket Specs | 2026-11-03T04:32:00Z |

---

## 4. Mapeamento Comparativo do Repositório: Existente vs Demandado

A auditoria exaustiva do repositório local (`hypothesis/`) mapeou a discrepância exata entre o código previamente escrito e o que é demandado para a execução completa:

```
+---------------------------------------------------------------------------------------------------------+
|                                    MAPEAMENTO COMPARATIVO DE CÓDIGO                                     |
+---------------------------------------------------------------------------------------------------------+
| Vetor             | Estado no Repositório Local              | Estado Demandado para Execução & Sim     |
+-------------------+------------------------------------------+------------------------------------------+
| 1. Hyperliquid    | Medidor de latência REST/WS com bug      | Conector completo EIP-712, ordens ALO,   |
|    (H84)          | de parsing no l2Book (0 fills gerados)   | emulador de mempool e filtro tóxico      |
|                   |                                          |                                          |
| 2. Velocity SWIFT | Listener passivo TypeScript capturando   | Decodificador de leilão holandês P(t),   |
|    (H85)          | ordens com falso alarme de desvio 2000bps| conector maker post-only e desduplicação |
|                   |                                          |                                          |
| 3. Sui DeepBookV3 | Rascunho PTB incompleto sem swap AMM,    | PTB atômica de 8 passos (Flash loan ->   |
|    (H86)          | pool morto wUSDC e carteira sem saldo    | AMM swap -> CLOB fill -> Repay Hot Potato|
|                   |                                          |                                          |
| 4. Kalshi FIX     | Menções em docs; leitura via proxy       | Motor FIXT.1.1/FIX50SP2, auth Ed25519/RSA|
|    (H87)          | Jupiter Prediction (provider=kalshi)     | e servidor mock de alta fidelidade       |
|                   |                                          |                                          |
| 5. dYdX v4        | Zero linhas de código no repositório     | Conector WebSocket/gRPC indexador L3 e   |
|    (CometBFT)     |                                          | client de ordens Cosmos SDK em memória   |
|                   |                                          |                                          |
| 6. GMX v2 & CEXs  | Testes antigos de REST CEX Tier-1 (D32)  | Conector Chainlink Data Streams pull,    |
|    Tier-2         | refutados por latência de 2.5s           | WebSockets MEXC/Gate.io e hedge sintético|
+---------------------------------------------------------------------------------------------------------+
```

---

## 5. Post-Mortems Detalhados dos Bugs e Falhas Históricas do Repositório

### 5.1 Post-Mortem 1: Bug de Parsing do WebSocket `l2Book` da Hyperliquid (H84)
- **Arquivo Afetado:** `trading-engine/h84_hyperliquid_gossip_feasibility.py` (Linhas 156-185).
- **Evidência no Artefato de Resultado:** `trading-engine/h84_hyperliquid_gossip_feasibility.json` registrou:
  ```json
  "mm_book_updates": 0,
  "mm_fills": 0,
  "spread_bps_mean": null
  ```
- **Causa Raiz Técnica:**
  A mensagem WebSocket real emitida pelo canal `l2Book` da Hyperliquid possui o seguinte formato:
  ```json
  {
    "channel": "l2Book",
    "data": {
      "coin": "SOL",
      "time": 1720000000000,
      "levels": [
        [{"px": "145.50", "sz": "10.0", "n": 3}, ...],
        [{"px": "145.52", "sz": "8.5", "n": 2}, ...]
      ]
    }
  }
  ```
  Na linha 172, a função `simulate_market_making` executava:
  ```python
  if "bid" in levels[0]: ...
  bid_levels = [l for l in all_levels if "bid" in l]
  ```
  Como o motor da Hyperliquid não utiliza a chave literal `"bid"` em cada nível de preço — e sim um array ordenado onde `levels[0]` é a lista de bids e `levels[1]` é a lista de asks —, todas as iterações caíam silenciosamente na cláusula `else: continue`.
- **Impacto no Projeto:** O teste de viabilidade de market making de H84 nunca chegou a rodar de fato. O script mediu apenas a latência de ping HTTP e WebSocket, mas gerou conclusões sem base de simulação de livro.
- **Correção Aplicada:** Desempacotar diretamente `bids = data["levels"][0]` e `asks = data["levels"][1]`, convertendo `float(bid["px"])` e `float(bid["sz"])`.

---

### 5.2 Post-Mortem 2: Bug de Escala e Interpretação do Leilão SWIFT da Drift/Velocity (H85)
- **Arquivo Afetado:** `trading-engine/h85_drift/h85_swift_subscriber.ts` (Linhas 144-166).
- **Evidência no Artefato de Resultado:** `h85_drift_swift_results.json` registrou desvio contínuo de -2003 bps em relação ao oráculo de mercado ($60 vs $75 na Coinbase).
- **Causa Raiz Técnica:**
  O script assumiu que o campo `params.price` representava a cotação instantânea de mercado da ordem do taker. Ele tentou aplicar divisores de potência de 10 (`1e6`, `1e9`, `1e10`) para adivinhar a escala numérica. Contudo, em ordens de leilão holandês da Velocity (`SignedMsgOrderParamsMessage`), o parâmetro `price` representa o preço limite extremo de proteção do taker ($P_{\text{end}}$). O preço ao qual a ordem realmente pode ser preenchida varia no tempo conforme $P(t) = P_{\text{start}} + \frac{t}{D}(P_{\text{end}} - P_{\text{start}})$.
- **Impacto no Projeto:** O algoritmo classificou erroneamente todas as ordens de takers do feed SWIFT como fluxo tóxico extremo com 20% de desvio, recomendando a rejeição de 100% dos preenchimentos e paralisando a coleta de rebates.
- **Correção Aplicada:** Implementar a decodificação de `auctionStartPrice`, `auctionEndPrice` e `auctionDuration`, projetando o slot de execução para calcular o valor real de mercado $P(t)$ no momento da captura.

---

### 5.3 Post-Mortem 3: Bug de Ausência da Perna AMM e Token Falso no Sui DeepBookV3 (H86)
- **Arquivo Afetado:** `trading-engine/h86_sui/h86_deepbook_execute.ts` (Linhas 94-150) e `h86_onchain_orderbook.py`.
- **Evidência de Falha:**
  1. A tentativa de execução do PTB falhou sistematicamente por saldo insuficiente na VM Move.
  2. A consulta on-chain apontou spreads absurdos de 11.016 bps (bid 1.68 / ask 5.8 vs spot 0.73).
- **Causa Raiz Técnica:**
  1. **A Perna AMM Estava Ausente:** No script `h86_deepbook_execute.ts`, a transação tomava USDC emprestado via `borrow_flashloan_quote`, depositava no `BalanceManager` e comprava SUI no DeepBook. Logo em seguida, tentava invocar `balance_manager::withdraw` pedindo USDC para devolver o flash loan! Como todo o USDC havia sido gasto na compra de SUI, o saldo de USDC no `BalanceManager` era rigorosamente zero. O script nunca enviou os tokens SUI para troca em uma AMM (Cetus ou Turbos). Sem o swap de retorno para USDC, o Hot Potato `FlashLoan` não podia ser quitado e a VM Move abortava a execução.
  2. **Endereço Obsoleto de Token:** O script consultava o pool SUI/WUSDC de ponte Wormhole, um contrato legado abandonado após a migração da Sui para o token nativo de USDC emitido pela Circle (`0xdba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7::usdc::USDC`).
- **Impacto no Projeto:** O vetor H86 foi erroneamente rotulado como "REFUTADO por iliquidez estrutural", quando na verdade a liquidez existe no contrato correto e o código continha um erro clássico de lógica contábil de arbitragem.
- **Correção Aplicada:** Reconstruir o grafo do PTB com os pares oficiais nativos, incorporando a perna de troca SUI → USDC na AMM antes da retirada e quitação do Hot Potato.

---

## 6. Análise de Viabilidade Jurídica, Regulatória e KYC

### 6.1 Kalshi e Regra 38 da CFTC
- **Regulamentação Federal:** Como DCM sob supervisão da CFTC, a Kalshi é legalmente proibida de fornecer acesso à negociação real sem cumprir os padrões federais de KYC/AML e Customer Identification Program (CIP).
- **Requisitos de Cadastro Real:**
  1. Número de Seguridade Social dos EUA (SSN) ou EIN corporativo registrado nos EUA.
  2. Endereço residencial ou sede fiscal válida nos Estados Unidos.
  3. Conta bancária sediada nos EUA vinculada via Plaid.
- **Viabilidade Prática:** O acesso de contas reais é restrito a cidadãos ou entidades corporativas dos EUA. Para o pipeline de desenvolvimento quantitativo independente, a conformidade e a testabilidade são asseguradas via **Kalshi Demo Environment** e **High-Fidelity FIX Mock Server**.

### 6.2 CEXs Tier-2 (MEXC e Gate.io)
- **Exigências de KYC:** Tanto a MEXC quanto a Gate.io exigem verificação de identidade KYC (Passaporte/ID e biometria facial) para limites operacionais plenos de trading de derivativos e saques de capital.
- **Risco de Congelamento de Fundos:** Contas operadas via scripts automatizados sem identificação correm risco elevado de retenção cautelar de fundos sob compliance internacional.
- **Solução Operacional:** Utilizar MEXC e Gate.io como **fontes líderes de dados de mercado (WebSockets públicos de cotação sem login)** para antecipar disparos de preço, e executar arbitragem e hedge sintético em protocolos on-chain permissionless (Hyperliquid e dYdX v4).

### 6.3 Ambientes 100% Permissionless (Sem KYC)
Os seguintes vetores são **100% livres de barreiras regulatórias e restrições de KYC**:
1. **Hyperliquid Testnet & Mainnet:** Interação direta via chave privada EVM e assinatura EIP-712. Faucet gratuito em testnet.
2. **Velocity / Drift SWIFT:** O feed SWIFT conecta com qualquer chave pública Solana e a execução ocorre on-chain de forma descentralizada.
3. **Sui DeepBookV3:** Operação direta na blockchain Sui via PTB com chaves locais Ed25519 e faucet na testnet.
4. **dYdX v4 Testnet & Indexer:** Assinatura via Cosmos SDK Bech32 sem intermediação de custódia centralizada.
5. **GMX v2:** Transações na Arbitrum One ou Sepolia via contratos inteligentes não-custodiais.

---

## 7. Roteiro Operacional e Arquitetura de Software (Milestones M3 a M5)

Com as especificações auditadas, as falhas de código depuradas e as credenciais de teste configuradas, o projeto avança para a construção dos módulos de software e validação empírica:

1. **M3: Conectores e Módulos de Execução Ponta a Ponta:**
   - Construção dos adaptadores derivados de `UnifiedVenue`:
     - `HyperliquidVenue`: Ingestão EIP-712, flags ALO, parsing corrigido de `l2Book` e leitor de mempool.
     - `VelocitySwiftVenue`: Listener SWIFT, decodificador de leilão holandês $P(t)$, flags post-only e desduplicação.
     - `SuiDeepBookVenue`: Construtor de PTB de 8 etapas via GraphQL, orquestrando Hot Potato e swap Cetus.
     - `KalshiFixVenue`: Cliente FIXT.1.1/FIX50SP2 com autenticação Ed25519 Tag 96 e roteamento dual (Mock/Demo).
     - `DydxV4Venue`: Leitor L3 de indexador e executor de ordens de curto prazo em memória.
     - `GmxCexVenue`: Avaliador de Chainlink Data Streams pull e conector WebSocket concorrente MEXC/Gate.io.

2. **M4: Bateria de Testes E2E e Auditoria de Integridade (4-Tier & Challenger):**
   - Publicação de `TEST_READY.md` cobrindo testes unitários, testes de integração de rede, reversão determinística de PTBs e simulação de concorrência.
   - Auditoria Forense estrita para garantir ausência de resultados mockados ou facadas lógicas.

3. **M5: Simulação Empírica Orientada a Eventos e Relatório Final:**
   - Execução de replay de ticks e medição matemática rigorosa do Valor Esperado ($\mathbb{E}[\text{PnL}]$), slippage, taxas líquidas, rebate capture e taxa de preenchimento (fill rate).
   - Consolidação final dos resultados empíricos em relatório executivo com recomendações definitivas de alocação de capital.
