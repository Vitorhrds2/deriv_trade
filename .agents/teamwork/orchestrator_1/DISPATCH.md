## 2026-11-10T02:00:04Z
Configurar, validar e implantar o bot de arbitragem atômica flash loan no Sui DeepBookV3 e AMM Cetus em produção no Railway, monitorando múltiplos pares com escalonamento dinâmico de capital.

Working directory: /Users/vitorhrds/Documents/Github/hypothesis
Integrity mode: development

## Requirements

### R1. Bot de Arbitragem Multi-Pares DeepBookV3 & Cetus
Montar e operar o bot de arbitragem atômica flash loan para execução de produção na Sui Mainnet utilizando o saldo da carteira (5.419245048 SUI) e o conector em `trading-engine/venues/sui_deepbook_venue.py`. O bot deve monitorar continuamente spreads e oportunidades de arbitragem nos 4 pares:
- SUI/USDC
- DEEP/SUI
- DEEP/USDC
- CETUS/SUI

### R2. Parâmetro Inicial e Escalonamento Dinâmico de Capital
Definir o parâmetro inicial de empréstimo flash loan `flash_borrow_amount = 1_000_000_000` (1.000 USDC nativo, 6 decimais) para a fase inicial. Implementar a verificação periódica automatizada do saldo de lucro líquido em USDC nativo na carteira Sui para transicionar o valor de empréstimo para 5.000 USDC e posteriormente atingir a meta de 10.000 USDC.

### R3. Implantação Contínua no Railway
Implantar o bot como serviço em execução contínua no Railway utilizando @[plugin:railway], com a região (Frankfurt ou Oregon) definida pela equipe com base em menor latência. Assegurar a injeção segura de credenciais e chaves privadas exclusivamente através de variáveis de ambiente do Railway.

### R4. Verificação Programática
Implementar testes automatizados e rotina de validação com simulação dry-run de PTBs (`dryRunTransactionBlock`) para verificar a construção correta das transações atômicas de 8 passos nos pares configurados, a lógica de escalonamento de capital e a inicialização saudável do serviço antes e durante a operação contínua.

## Acceptance Criteria

### Core Functionality & Pair Coverage
- [ ] O bot monitora ativamente as cotações e spreads nos 4 pares: SUI/USDC, DEEP/SUI, DEEP/USDC e CETUS/SUI.
- [ ] O valor inicial de `flash_borrow_amount` está configurado para 1.000 USDC (1.000.000.000 unidades).
- [ ] As transações de arbitragem constroem e submetem PTBs atômicos de 8 passos em Move (empréstimo Hot Potato a 0 bps no DeepBookV3, troca no Cetus e quitação do empréstimo com garantia de zero leg risk).

### Capital Scaling
- [ ] O bot verifica periodicamente o saldo de USDC nativo acumulado na carteira.
- [ ] O parâmetro de empréstimo escala automaticamente de 1.000 USDC para 5.000 USDC e 10.000 USDC conforme o lucro líquido acumulado atinge os patamares estipulados.

### Infrastructure & Deployment
- [ ] O bot está provisionado e em execução contínua no Railway na região definida (Frankfurt ou Oregon).
- [ ] O serviço possui reinicialização automática configurada e emite logs detalhados de monitoramento e execução.
- [ ] Nenhuma chave privada ou segredo da carteira é versionado no repositório git ou registrado em arquivos locais sem proteção.

### Programmatic Verification
- [ ] Testes automatizados executam e validam a construção dos PTBs para os 4 pares sem erros.
- [ ] Simulação via `dryRunTransactionBlock` valida que operações sem lucro revertem de forma limpa na VM do Move com consumo mínimo de gás (~0.002 SUI).
- [ ] Testes unitários validam a lógica do gatilho de escalonamento dinâmico de capital.

---

## 2026-11-10T04:11:09Z
**Task**: Os valores da carteira com SUI está em /Users/vitorhrds/Documents/Github/hypothesis/trading-engine/h86_sui/.env e as definições das chaves detalhadas estão em /Users/vitorhrds/Documents/Github/hypothesis/trading-engine/h86_sui/.env.example, verifique e suba no serviço sui-deepbook-arb-bot do railway

**Additional Context**:
O usuário informou onde estão armazenadas as credenciais reais da carteira com os 5.419245048 SUI (`/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/h86_sui/.env` e `/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/h86_sui/.env.example`). Verifique esses arquivos imediatamente, sincronize as variáveis/chaves no conector/runner e injete-as no serviço `sui-deepbook-arb-bot` no Railway para ativar a operação real com a carteira financiada.

