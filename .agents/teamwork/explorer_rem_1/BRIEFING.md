# BRIEFING — 2026-11-10T05:10:30Z

## Mission
Investigate Task 2: Creation and synchronization of real on-chain DeepBook V3 `BalanceManager` on Sui Mainnet using the funded wallet.

## 🔒 My Identity
- Archetype: explorer
- Roles: investigation, synthesis
- Working directory: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/explorer_rem_1
- Original parent: ae5035fc-25bf-4785-8a7f-6b28349aa17b
- Milestone: Remediation Task 2 (BalanceManager on Sui Mainnet)

## 🔒 Key Constraints
- Read-only investigation — do NOT implement directly in production code or execute on-chain transactions without worker role
- Provide exact steps, script code, object extraction, and Railway env var update procedure
- Inspect trading-engine/h86_sui/.env and .env.example, h86_setup_wallet.ts, venues/sui_deepbook_venue.py, venues/sui_bot_runner.py

## Current Parent
- Conversation ID: ae5035fc-25bf-4785-8a7f-6b28349aa17b
- Updated: 2026-11-10T05:10:30Z

## Investigation State
- **Explored paths**:
  - `ORIGINAL_REQUEST.md`, `PROJECT.md`, `DISPATCH.md`
  - `trading-engine/h86_sui/.env`, `.env.example`, `package.json`, `h86_setup_wallet.ts`, `h86_deepbook_execute.ts`
  - `trading-engine/venues/sui_deepbook_venue.py`, `sui_bot_runner.py`
  - Sui Mainnet GraphQL endpoint (`https://graphql.mainnet.sui.io/graphql`)
  - Railway Project `0b2dfdc6-81f4-4da4-af48-4f566be655d4`, Service `8ec93921-cafb-417a-9c98-9d8be72d1344`
- **Key findings**:
  - Public JSON-RPC nodes return `-32601` or 404 because JSON-RPC was removed from Sui fullnode in v1.80+.
  - Official endpoint for queries, dry-run, and transaction execution is `https://graphql.mainnet.sui.io/graphql`.
  - Operator wallet `0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9` has 5.419245048 SUI and gas coin `0x7100dfd8b3ffaafebef435a4850278ee636e5867987b647fa371a90baf9c0f54`.
  - DeepBook V3 package on Mainnet is `0x2c8d603bc51326b8c13cef9dd07031a408a48dddb541963357661df5d3204809`.
  - BalanceManager creation PTB consists of:
    1. `0x2c8d603bc51326b8c13cef9dd07031a408a48dddb541963357661df5d3204809::balance_manager::new`
    2. `0x0000000000000000000000000000000000000000000000000000000000000002::transfer::public_share_object<0x2c8d603bc51326b8c13cef9dd07031a408a48dddb541963357661df5d3204809::balance_manager::BalanceManager>(manager)`
  - Transaction building and signing tested offline with `@mysten/sui`. Sui GraphQL pre-flight verified signature with `{"success": true}`.
- **Unexplored areas**: None. All aspects of Task 2 fully investigated and verified.

## Key Decisions Made
- Provide standalone turnkey script `proposed_h86_create_balance_manager.mjs` supporting `--dry-run` and `--execute`.
- Document exact Railway MCP tool parameters (`railway_mcp:set-variables`) for Worker to synchronize `DEEPBOOK_BALANCE_MANAGER_ID`.

## Artifact Index
- `.agents/teamwork/explorer_rem_1/BRIEFING.md` — persistent memory
- `.agents/teamwork/explorer_rem_1/progress.md` — heartbeat and progress tracker
- `.agents/teamwork/explorer_rem_1/proposed_h86_create_balance_manager.mjs` — turnkey executable script
- `.agents/teamwork/explorer_rem_1/handoff.md` — final 5-component handoff report
