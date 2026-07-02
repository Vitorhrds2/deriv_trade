# Polymarket — Referência de Desenvolvimento (compilado 2026-07-02)

**Propósito:** fonte de conhecimento injetável (docs oficiais + SDKs + MCPs disponíveis) para
qualquer agente (Cascade, Devin, Antigravity) trabalhar com Polymarket neste repositório, no
mesmo espírito do `deriv-api` já configurado em `~/.gemini/config/mcp_config.json`. Compilado a
partir de `docs.polymarket.com` (oficial) + repositórios GitHub oficiais/comunidade.

## Documentação oficial

- **Índice:** https://docs.polymarket.com
- **Overview de trading:** https://docs.polymarket.com/trading/overview
- **Autenticação:** https://docs.polymarket.com/api-reference/authentication
- **Restrições geográficas:** https://docs.polymarket.com/api-reference/geoblock
- **Clients & SDKs:** https://docs.polymarket.com/developers/CLOB/clients/methods-overview

## Modelo de dados: público vs. autenticado

| Camada | Precisa de conta/credencial? | Endpoints |
|---|---|---|
| **Market data** (markets, eventos, orderbook, preços, spreads, histórico) | **Não** — 100% público | `gamma-api.polymarket.com` (Gamma — markets/eventos), `clob.polymarket.com` (book/preços), `data-api.polymarket.com` (posições/holders/trades on-chain) |
| **Trading** (postar/cancelar ordem, saldo, allowances) | **Sim** — autenticação L1+L2 | `clob.polymarket.com` (mesma base, rotas autenticadas) |
| **WebSocket público** | Não | `wss://ws-subscriptions-clob.polymarket.com/ws/market`, `wss://ws-live-data.polymarket.com` |
| **WebSocket de usuário** | Sim (L2) | `wss://ws-subscriptions-clob.polymarket.com/ws/user` |

Tudo que já rodamos até agora (`polymarket_lag_probe.py`, `pa5_collector.py`) usa **só a camada
pública** — é por isso que não precisou de nenhuma credencial nem carteira.

## Autenticação de duas camadas (só necessária para operar de verdade)

- **L1 (chave privada da carteira):** cria/deriva as credenciais de API (`createApiKey()` /
  `deriveApiKey()`) e assina as ordens localmente (EIP-712). A chave privada **nunca sai da
  máquina** — nem para a Polymarket.
- **L2 (API key + secret + passphrase, derivados do L1):** autentica requests REST — cancelar/ver
  ordens abertas, checar saldo/allowance, postar ordem já assinada.
- **Best practice oficial:** guardar a chave privada só em variável de ambiente (`.env`
  gitignored, nunca commitada) e assinar do lado do servidor — exatamente o padrão já usado neste
  repo pro token da Deriv.
- **SDKs oficiais:** [`py-clob-client`](https://github.com/Polymarket/py-clob-client) (Python),
  cliente TypeScript e Rust — cobrem o fluxo de assinatura/autenticação inteiro, não é preciso
  reimplementar EIP-712 na mão.

## Restrições geográficas

Bloqueio por país segue sanções OFAC + restrições regulatórias adicionais. **Checar elegibilidade
antes de criar conta**, via endpoint público:
```python
import requests
requests.get("https://polymarket.com/api/geoblock").json()
# {"blocked": bool, "ip": ..., "country": ..., "region": ...}
```
Formulário de KYC/KYB (se necessário): linkado na própria página de geoblock.

**CONFIRMADO 2026-07-02: Brasil (BR) está bloqueado.** Testado ao vivo pelo usuário
(`{"blocked": true, "country": "BR", "region": "SP"}`) e confirmado na lista oficial de
`docs.polymarket.com/api-reference/geoblock` (BR listado como `Blocked`, não
`close-only`/`frontend UI restricted` — ou seja, bloqueia **colocação de ordem via API**, não só
a UI do site). Contexto: a SPA (regulador brasileiro de apostas) declarou em março/2026 que
nenhuma plataforma de prediction market está autorizada a operar no Brasil, e o setor de apostas
licenciado pediu formalmente o bloqueio de Polymarket/Kalshi.

- **O que NÃO é afetado:** leitura de dados públicos (Gamma/CLOB/Data API) — é por isso que o
  PA5 sempre funcionou normalmente, mesmo rodando localmente. `venues/polymarket.py` continua
  100% válido pra pesquisa/coleta.
- **O que É afetado:** colocação de ordem nova (trading de verdade) a partir de IP brasileiro.
- **VPN/evasão de geoblock é proibida pelos Termos de Serviço da Polymarket** e arrisca ação
  na conta (banimento) — não é um caminho recomendado nem algo que devo ajudar a implementar.
  Enforcement usa múltiplos sinais (IP + metadados de conta/wallet), não só IP da requisição.
- **Implicação prática:** trading real via Polymarket direta não é viável a partir do Brasil
  sem violar os Termos. A rota Jupiter Prediction API (ver
  `docs/phantom_ecosystem_findings.md`) não bloqueia Brasil — vira o caminho mais realista pra
  execução, se/quando uma hipótese justificar operar de verdade.

## O que É preciso pra criar a conta (ação humana, fora do escopo do agente)

1. Acessar `polymarket.com`, conectar/criar carteira (email via Magic.link é o caminho mais
   simples, ou MetaMask) — **isto exige aceitar Termos de Serviço e não pode ser feito por um
   agente**, é uma ação de identidade da pessoa física.
2. Rodar o check de geoblock acima (ou ver na própria UI) pra confirmar elegibilidade na sua
   região antes de depositar qualquer coisa.
3. Depositar USDC (rede Polygon) se/quando for operar de verdade — **não é necessário só pra
   pesquisa** (o que já fizemos e o PA5 continuam 100% sem depósito).
4. Se/quando decidir operar: gerar as credenciais L1/L2 a partir da própria carteira (nunca
   compartilhar a seed/chave privada com o agente) e guardar como variável de ambiente no
   servidor, mesmo padrão do `.env` da Deriv.

## MCP servers disponíveis (não existe um oficial hospedado pela Polymarket, ao contrário da Deriv)

A Deriv hospeda o próprio MCP (`https://mcp-api.deriv.com/mcp`, configurado como `deriv-api` em
`~/.gemini/config/mcp_config.json`). A Polymarket **não tem MCP oficial** — só opções de
comunidade (não auditadas por nós, código de terceiros rodando via `npx`/`uv`):

| Repo | Precisa de credencial? | Escopo |
|---|---|---|
| `pab1it0/polymarket-mcp` | **Não** | Só Gamma API (markets/eventos, leitura) |
| `suy2014/polymarket-mcp` | **Não** | Markets/orderbook/preços (Gamma+CLOB+Data, leitura) |
| `duongnv0499/polymarket-mcp-server` | Só se usar trading | Leitura + trading via `py-clob-client` oficial, tem `DEMO_MODE` |
| `amolkodan/polymarket-claude-mcp`, `PlayAINetwork/Polymarket-mcp`, `demwick/polymarket-agent-mcp` | **Sim** (`PRIVATE_KEY`) | Trading completo — não recomendado sem decisão explícita de operar com capital |

**Recomendação:** se for injetar um MCP no `~/.gemini/config/mcp_config.json` (mesmo arquivo do
`deriv-api`), usar uma das duas primeiras (sem credencial) — dá o mesmo tipo de acesso que já
temos via `polymarket_lag_probe.py`, só que exposto como ferramenta de agente em vez de script.
Não vejo necessidade de MCP com trading habilitado — nenhuma hipótese aqui passou da fase paper.

## Próximos passos sugeridos (arquitetura "ecossistema multi-corretora")

`trading-engine/` hoje é ~130 scripts avulsos sem abstração de "venue" — cada integração (Deriv,
Binance-como-feed, Polymarket) foi implementada ad-hoc. Formalizar um adapter comum (ex.:
`get_public_price`, `get_orderbook`, `place_order`, `get_balance` por venue) é pré-requisito real
antes de "escalar pra Kalshi/Binance-como-corretora/Phantom" — do contrário cada nova plataforma
vira mais um punhado de scripts soltos. Ainda não iniciado (decisão de escopo em aberto).
