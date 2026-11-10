Implementar em produção quatro melhorias de alta rentabilidade no bot de arbitragem: rota reversa bidirecional DeepBook <-> Cetus, dimensionamento analítico ótimo de empréstimo (Q* Optimal Sizing), priorização de rotas e proteção de cofre (DEEP/SUI vs DEEP/USDC), e integração de cotação e execução atômica com a Turbos Finance CLMM.

Working directory: /Users/vitorhrds/Documents/Github/hypothesis
Integrity mode: development

## Requirements

### R1. Arbitragem Bidirecional (DeepBook <-> Cetus)
Implementar a rota reversa de arbitragem para captura de spreads negativos (Cetus Price > DeepBook Ask): tomar flashloan atômico no DeepBook determinando dinamicamente o ativo de empréstimo conforme o par e liquidez, comprar a mercado no DeepBook (Ask) e vender na Cetus, quitando o empréstimo no mesmo PTB e retendo o lucro líquido.

### R2. Dimensionamento Analítico Ótimo de Empréstimo (Q* Optimal Sizing)
Implementar o cálculo analítico do volume ótimo de borrow (Q*) baseado na inclinação de impacto da pool Cetus e no spread disponível, substituindo o dimensionamento estático pelo livro do DeepBook por tranches dinâmicas ajustadas (ex: $100 - $150 USDC) que passem com lucro líquido positivo na Move VM sem rejeições pré-voo por slippage excessivo.

### R3. Priorização de Rotas e Proteção de Vault
Priorizar oportunidades de arbitragem no par DEEP/SUI (maior liquidez na Cetus e taxa zero de taker) sobre DEEP/USDC e verificar programaticamente a disponibilidade de saldo em caixa no cofre do DeepBook antes de disparar transações, prevenindo abortos por `EInsufficientVaultBalance` (abort code 2).

### R4. Suporte Multi-DEX com Turbos Finance
Integrar a Turbos Finance CLMM com suporte tanto para consulta contínua de cotações em tempo real no scanner (`params.amm_target = "turbos"`) quanto para a construção e execução atômica de transações PTB de arbitragem DeepBook <-> Turbos, além das rotas existentes com Cetus.

### R5. Suíte de Testes, Integridade Hot Potato e Deploy do Bot Runner
Garantir que todos os 85+ testes existentes em `trading-engine/tests` continuem passando 100%, preservar a atomicidade e garantia de Zero Leg Risk via Move VM Hot Potato PTB, validar simulações pré-voo e integridade de consumo de gas, e atualizar o bot runner configurado para execução real direta (live execution).

## Acceptance Criteria

### Testes e Integridade Atômica
- [ ] 100% dos testes existentes em `trading-engine/tests` passam com sucesso sem regressões.
- [ ] Todas as novas rotas e fluxos preservam a estrutura atômica de Hot Potato na Move VM com Zero Leg Risk.
- [ ] Simulações pré-voo e estimativas de gas são validadas antes do envio de transações.

### Execução e Estratégias de Arbitragem
- [ ] A rota reversa DeepBook Ask -> Cetus é executada com sucesso com flashloan dinâmico quando Cetus Price > DeepBook Ask.
- [ ] O algoritmo Q* calcula tranches ótimas de volume de empréstimo adaptadas ao impacto de preço na Cetus.
- [ ] O mecanismo de checagem de saldo do cofre do DeepBook impede disparos quando o cofre estiver sem saldo suficiente.
- [ ] O scanner e executor realizam arbitragem em tempo real com a Turbos Finance CLMM de forma atômica.
- [ ] O bot runner está atualizado e operacional em modo de execução real direta (live execution).
