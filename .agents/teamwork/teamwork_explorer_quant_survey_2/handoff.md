# Handoff Report — Survey 2: Repository Audit & Delta Mapping

## 1. Observation

Direct observations and evidence gathered from the local codebase:

- **`docs/state_of_research.md` (lines 1196–1242):**
  - Section 52 documents H84, H85, H86 tested on 2026-07-14 in an AWS `us-east-2` instance (2 vCPUs, 7.6GB RAM).
  - H84 (*Hyperliquid Gossip*): Refuted due to infrastructure gap (non-validator node requires 32 cores, 128GB RAM; instance had 2 vCPUs; c7i.32xlarge costs ~$2,700/mo). Public REST median = 152ms, WS trade median = 285ms (outliers to 9.5s). Files deleted on us-east-2 on 2026-07-15.
  - H85 (*Velocity SWIFT*): Migrated `@drift-labs/sdk` → `@velocity-exchange/sdk@0.6.1`, program ID `vELoC1audYbSYVRXn1vPaV8Axoa9oU6BYmNGZZBDZ1P`, quote asset USDT. 53 messages in SOL-PERP with ~$60 price vs $75 Coinbase (2000 bps deviation noted as possible scaling artifact). Moved to `eu-central-1b` running `h85_continuous.sh` in tmux `h85_swift`.
  - H86 (*Sui DeepBookV3*): 16 pools mapped via RPC. Discovered SUI/WUSDC pool (20 bps fee) has bid=1.68, ask=5.8 (spread 11,016 bps) against Coinbase SUI=$0.73. Refuted as illiquid pool; 3670 bps spread was an artifact of comparing GeckoTerminal with an inactive pool.
  - H87 (*Kalshi FIX*), dYdX v4 L3, and GMX v2: Not mentioned in `state_of_research.md` or `hypotheses-data.ts`.
- **`trading-engine/h84_hyperliquid_gossip_feasibility.py` & `.json`:**
  - Lines 156–185: Parsing bug in `simulate_market_making`: searched for `"bid"` key inside `levels[0]`, whereas Hyperliquid WS `l2Book` format returns `levels: [bids_list, asks_list]` as nested arrays.
  - `h84_hyperliquid_gossip_feasibility.json` lines 146–149: Resulted in `"mm_book_updates": 0`, `"mm_fills": 0`, `"spread_bps_mean": null`. Zero execution or EIP-712 signing logic.
- **`trading-engine/h85_drift/h85_swift_subscriber.ts`:**
  - Lines 112–117: Subscribes to `SwiftOrderSubscriber` from `@velocity-exchange/sdk`.
  - Lines 144–172: Divides price by 1e6/1e9/1e10 based on nearest distance to Coinbase, producing ~$60 vs $75 due to interpreting auction parameters as spot quotes.
  - No order placement or maker fill logic exists; it is purely a passive listener.
- **`trading-engine/h86_sui/h86_deepbook_execute.ts` & `.env`:**
  - Lines 97–150: Fatal logic bug in PTB execution graph. Borrows USDC via `borrow_flashloan_quote`, deposits into `BalanceManager`, places market order buying SUI, and then immediately tries to withdraw USDC (`withdraw` quoteType USDC) to repay the loan. The second leg (swapping SUI back to USDC on an AMM like Cetus/Turbos/Kriya) was never implemented.
  - Line 248 comment verbatim: `"Next: increase amount and add AMM leg for real arb."`
  - `.env` line 11: `DEEPBOOK_BALANCE_MANAGER_ID=` is blank; wallet address `0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9` has 0 SUI balance.
- **`trading-engine/venues/`:**
  - `base.py` & `registry.py`: Extensible two-layer architecture (`PriceFeedVenue` and `ExecutionVenue`) with `@register` decorator.
  - Existing adapters: `binance.py` (WS bookTicker read), `polymarket.py` (REST Gamma/CLOB read), `deriv.py` (WS DerivClient wrap), `jupiter_prediction.py` (REST Jupiter Prediction API with Cloudflare User-Agent bypass and retry/fallback), `jupiter_execution.py` (Solana tx signing validated via Memo instruction; no live execution due to $5 min order / zero balance).
- **`agentic-conversation/`:**
  - Operational HTTP relay (`local_relay.py`) and Telegram bot (`devin_telegram/`), currently unintegrated with trading-engine execution loops.

## 2. Logic Chain

1. **Premise 1:** The user request demands end-to-end software and empirical simulation proving or disproving edge across 6 specific architectural vectors: H84 (Hyperliquid mempool/gossip), H85 (Drift SWIFT), H86 (Sui DeepBookV3 Hot Potato), H87 (Kalshi FIX), dYdX v4 L3, and GMX v2 / Tier-2 CEXs.
2. **Premise 2:** Analysis of existing code reveals that H84, H85, and H86 were exploratory probes with major technical limitations:
   - H84 has a WebSocket book-parsing defect (0 updates/fills) and lacks execution signing and gossip feeds.
   - H85 has an unresolved price-scale artifact (~2000 bps) and zero order placement logic.
   - H86 has a fatal bug omitting the AMM leg in the PTB and targeted an illiquid pool without funding.
3. **Premise 3:** Analysis of H87 (Kalshi FIX), dYdX v4, and GMX v2 / Tier-2 CEXs reveals they have 0% code representation in the repository.
4. **Premise 4:** The venue framework (`trading-engine/venues/`) is modular and ready to accept new connectors adhering to `PriceFeedVenue` and `ExecutionVenue`.
5. **Inference / Conclusion:** To fulfill the mandate, the team must:
   - Correct the bugs in H84, H85, and H86.
   - Build complete PTB atomic logic for H86 and maker execution for H85.
   - Develop connectors from scratch for H87 (with FIX mock/emulator to bypass CFTC/KYC blocks), dYdX v4, and GMX v2 / Tier-2 CEXs.
   - Execute empirical simulations with real fee hurdles and statistical rigor via `stats_utils.py`.

## 3. Caveats

- **Infrastructure Constraints:** Hyperliquid non-validator node hardware (32 cores, 128GB RAM) cannot be hosted on standard developer workstations or small EC2 instances; simulation must rely on gossip emulation or remote feeds.
- **Regulatory Barriers:** Kalshi requires US entity KYC and CFTC accreditation for PrivateLink/FIX; Polymarket blocks Brazilian IPs for order placement. A local FIX mock emulator is mandatory for unhindered development.
- **On-chain Balances:** Solana and Sui wallets currently have zero balance, precluding mainnet transaction broadcasting unless funded or simulated via dry-run RPCs (`sui_dryRunTransactionBlock`).

## 4. Conclusion

The repository state is thoroughly audited and mapped:
- **Available foundations:** `trading-engine/venues/` abstraction, `stats_utils.py` statistical testing, `agentic-conversation/` relay, and initial API reconnaissance for H84-H86.
- **Critical defects to fix:** Hyperliquid WS book parser bug in `h84_hyperliquid_gossip_feasibility.py`, price scaling and passive-only limitation in `h85_swift_subscriber.ts`, missing AMM leg in `h86_deepbook_execute.ts`.
- **New modules required:** Full connectors and empirical simulators for H87 (Kalshi FIX + Mock), dYdX v4 CometBFT L3, and GMX v2 Data Streams / Tier-2 CEXs (MEXC/Gate.io).
- Full detailed findings and delta specification are written in `repo_audit_mapping.md`.

## 5. Verification Method

To independently verify the observations made in this audit:

1. **Verify H84 Parser Bug & Latency Data:**
   - Inspect `trading-engine/h84_hyperliquid_gossip_feasibility.py` lines 156–185.
   - Inspect `trading-engine/h84_hyperliquid_gossip_feasibility.json` lines 146–149 to confirm `"mm_book_updates": 0`.
2. **Verify H85 Velocity Migration & Deviation:**
   - Inspect `trading-engine/h85_drift/h85_swift_subscriber.ts` lines 18–27 and 144–172.
   - Inspect `trading-engine/h85_drift/h85_drift_swift_results.json` lines 17–20 to confirm `price: 60.065` vs `initial_ref_price: 75.11`.
3. **Verify H86 Missing AMM Leg & Illiquidity:**
   - Inspect `trading-engine/h86_sui/h86_deepbook_execute.ts` lines 118–150 and line 248.
   - Inspect `trading-engine/h86_sui/h86_deepbook_onchain_results.json` lines 144–145 to confirm bid=1.68 and ask=5.8.
4. **Verify Absence of H87, dYdX v4, GMX v2 Connectors:**
   - Search for FIX or dYdX connectors in `trading-engine/venues/`: only `binance.py`, `polymarket.py`, `deriv.py`, `jupiter_prediction.py`, `jupiter_execution.py` exist.
