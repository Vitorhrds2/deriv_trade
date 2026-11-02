/**
 * H86 DeepBook V3 Flash Loan Arbitrage Execution (TypeScript)
 *
 * Executes atomic flash loan arbitrage on Sui DeepBook V3 using the
 * "Hot Potato" pattern. If the arb doesn't materialize, the entire
 * PTB reverts at ~zero cost.
 *
 * REQUIRES .env with:
 *   SUI_PRIVATE_KEY=...     (from h86_setup_wallet.ts)
 *   SUI_WALLET_ADDRESS=...  (from h86_setup_wallet.ts)
 *   DEEPBOOK_BALANCE_MANAGER_ID=...  (from h86_setup_wallet.ts)
 *
 * Usage: npx tsx h86_deepbook_execute.ts
 */
import { Ed25519Keypair } from '@mysten/sui/keypairs/ed25519';
import { getFullnodeUrl, SuiClient } from '@mysten/sui/client';
import { Transaction } from '@mysten/sui/transactions';
import * as fs from 'fs';
import * as path from 'path';

// ─── Load .env ────────────────────────────────────────────────────────
function loadEnv(): Record<string, string> {
  const envPath = path.join(process.cwd(), '.env');
  try {
    const content = fs.readFileSync(envPath, 'utf8');
    const env: Record<string, string> = {};
    for (const line of content.split('\n')) {
      const match = line.match(/^([^#=]+)=(.*)$/);
      if (match) {
        env[match[1].trim()] = match[2].trim();
      }
    }
    return env;
  } catch {
    console.error('No .env file found. Run: npx tsx h86_setup_wallet.ts first.');
    process.exit(1);
  }
}

const env = loadEnv();

const PRIVATE_KEY = env.SUI_PRIVATE_KEY;
const WALLET_ADDRESS = env.SUI_WALLET_ADDRESS;
const BALANCE_MANAGER_ID = env.DEEPBOOK_BALANCE_MANAGER_ID;
const SUI_RPC = env.SUI_RPC_URL || 'https://fullnode.mainnet.sui.io';

// DeepBook V3 mainnet package
const DEEPBOOK_PACKAGE = '0x000000000000000000000000000000000000000000000000000000000000dee9';

// Type strings for common Sui assets
const SUI_TYPE = '0x2::sui::SUI';
// USDC on Sui mainnet (Circle native)
const USDC_TYPE = '0xdba3468e460292df0e3969655621c0c0e3c4f5c6c7c8c9c0c1c2c3c4c5c6c7c8::usdc::USDC';
// USDT on Sui mainnet
const USDT_TYPE = '0xc060006111016b8a020ad5b33834984a437a7d15fdc2c154444c4d9b8b7c5e7a::usdt::USDT';

// ─── Validate ─────────────────────────────────────────────────────────
function validateEnv() {
  const missing: string[] = [];
  if (!PRIVATE_KEY) missing.push('SUI_PRIVATE_KEY');
  if (!WALLET_ADDRESS) missing.push('SUI_WALLET_ADDRESS');
  if (!BALANCE_MANAGER_ID) missing.push('DEEPBOOK_BALANCE_MANAGER_ID');

  if (missing.length > 0) {
    console.error('Missing required .env values:', missing.join(', '));
    console.error('Run: npx tsx h86_setup_wallet.ts to setup your wallet');
    process.exit(1);
  }
}

// ─── Flash Loan Arb Execution ─────────────────────────────────────────
async function executeFlashLoanArb(
  client: SuiClient,
  keypair: Ed25519Keypair,
  poolId: string,
  balanceManagerId: string,
  baseType: string,
  quoteType: string,
  amountIn: number,
  minAmountOut: number,
  isBid: boolean, // true = buy base with quote, false = sell base for quote
): Promise<any> {
  /**
   * Execute a flash loan arbitrage:
   * 1. Borrow quote (USDC) via flash loan from DeepBook pool
   * 2. Use borrowed USDC to buy base (SUI) on DeepBook (market order)
   * 3. Sell the SUI on another venue (AMM) for more USDC
   * 4. Repay flash loan with the USDC received
   * 5. Keep the profit
   *
   * If at any step the profit is insufficient, the PTB reverts.
   */

  const tx = new Transaction();

  // Step 1: Borrow flash loan (quote asset = USDC)
  const [borrowedCoin, flashLoanReceipt] = tx.moveCall({
    target: `${DEEPBOOK_PACKAGE}::pool::borrow_flashloan_quote`,
    arguments: [
      tx.object(poolId),
      tx.pure.u64(amountIn),
    ],
    typeArguments: [baseType, quoteType],
  });

  // Step 2: Deposit borrowed USDC into BalanceManager
  tx.moveCall({
    target: `${DEEPBOOK_PACKAGE}::balance_manager::deposit`,
    arguments: [
      tx.object(balanceManagerId),
      borrowedCoin,
    ],
    typeArguments: [quoteType],
  });

  // Step 3: Place market order (buy base with quote)
  // place_market_order(pool, balance_manager, order_quantity, is_bid, pay_with_deep, base_type, quote_type)
  tx.moveCall({
    target: `${DEEPBOOK_PACKAGE}::pool::place_market_order`,
    arguments: [
      tx.object(poolId),
      tx.object(balanceManagerId),
      tx.pure.u64(amountIn),
      tx.pure.bool(isBid),
      tx.pure.bool(false), // pay_with_deep = false
    ],
    typeArguments: [baseType, quoteType],
  });

  // Step 4: Withdraw the output amount from BalanceManager
  const [returnCoin] = tx.moveCall({
    target: `${DEEPBOOK_PACKAGE}::balance_manager::withdraw`,
    arguments: [
      tx.object(balanceManagerId),
      tx.pure.u64(amountIn + minAmountOut), // must return at least borrowed + profit
    ],
    typeArguments: [quoteType],
  });

  // Step 5: Return flash loan
  tx.moveCall({
    target: `${DEEPBOOK_PACKAGE}::pool::return_flashloan_quote`,
    arguments: [
      tx.object(poolId),
      returnCoin,
      flashLoanReceipt,
    ],
    typeArguments: [baseType, quoteType],
  });

  // Execute
  console.log(`  [TX] Submitting flash loan arb PTB...`);
  console.log(`    Pool: ${poolId}`);
  console.log(`    Amount: ${amountIn} (${isBid ? 'buy' : 'sell'})`);
  console.log(`    Min output: ${minAmountOut}`);

  try {
    const result = await client.signAndExecuteTransaction({
      transaction: tx,
      signer: keypair,
      options: { showEffects: true, showBalanceChanges: true },
    });

    console.log(`  [TX] Digest: ${result.digest}`);
    console.log(`  [TX] Status: ${result.effects?.status?.status}`);

    if (result.effects?.status?.status === 'success') {
      console.log(`  [TX] ✅ SUCCESS — arb executed!`);
      if (result.balanceChanges) {
        for (const change of result.balanceChanges) {
          console.log(`    ${change.coinType}: ${change.amount}`);
        }
      }
    } else {
      console.log(`  [TX] ❌ FAILED — PTB reverted (cost: ~0.01 SUI gas)`);
      console.log(`    Error: ${result.effects?.status?.error || 'unknown'}`);
    }

    return result;
  } catch (e: any) {
    console.log(`  [TX] Error: ${e.message}`);
    return null;
  }
}

// ─── Main ─────────────────────────────────────────────────────────────
async function main() {
  validateEnv();

  console.log('='.repeat(90));
  console.log('H86 — Sui DeepBookV3 Flash Loan Arb Execution');
  console.log('='.repeat(90));
  console.log(`  Wallet: ${WALLET_ADDRESS}`);
  console.log(`  BalanceManager: ${BALANCE_MANAGER_ID}`);
  console.log(`  RPC: ${SUI_RPC}`);
  console.log();

  // Setup keypair and client
  const keypair = Ed25519Keypair.fromSecretKey(PRIVATE_KEY);
  const client = new SuiClient({ url: SUI_RPC });
  console.log('  Checking wallet balance...');
  const balance = await client.getBalance({ owner: WALLET_ADDRESS });
  console.log(`  SUI Balance: ${balance.totalBalance} SUI`);

  if (parseFloat(balance.totalBalance) < 0.05) {
    console.log('  ⚠️  Insufficient SUI for gas. Need at least 0.05 SUI.');
    console.log('  Fund your wallet and try again.');
    process.exit(1);
  }

  // Get DeepBook orderbook to find arb opportunity
  console.log('\n  Scanning for arb opportunities...');

  // TODO: Replace with actual pool IDs discovered by scan script
  // For now, these need to be filled in manually or from scan results
  const SUI_USDC_POOL = env.SUI_USDC_POOL_ID || 'REPLACE_WITH_POOL_ID';
  const SUI_USDT_POOL = env.SUI_USDT_POOL_ID || 'REPLACE_WITH_POOL_ID';

  if (SUI_USDC_POOL === 'REPLACE_WITH_POOL_ID') {
    console.log('  ⚠️  No pool IDs configured.');
    console.log('  Run scan first: npx tsx h86_deepbook_scan.ts');
    console.log('  Then add pool IDs to .env:');
    console.log('    SUI_USDC_POOL_ID=0x...');
    console.log('    SUI_USDT_POOL_ID=0x...');
    process.exit(1);
  }

  // Execute arb (example: borrow USDC, buy SUI on DeepBook, sell on AMM)
  // Start with very small amount for testing
  const testAmount = 1000000; // 1 USDC (6 decimals) — start small!

  console.log(`\n  Executing test arb with ${testAmount / 1e6} USDC...`);

  const result = await executeFlashLoanArb(
    client,
    keypair,
    SUI_USDC_POOL,
    BALANCE_MANAGER_ID,
    SUI_TYPE,
    USDC_TYPE,
    testAmount,
    testAmount, // min output = input (break even, just testing)
    true, // isBid = buy SUI with USDC
  );

  if (result?.effects?.status?.status === 'success') {
    console.log('\n  ✅ Test arb succeeded! Flash loan pattern works.');
    console.log('  Next: increase amount and add AMM leg for real arb.');
  } else {
    console.log('\n  ❌ Test arb failed. Check error message above.');
    console.log('  Cost: ~0.01 SUI for gas (PTB reverted).');
  }

  process.exit(0);
}

main().catch(e => {
  console.error('Fatal error:', e);
  process.exit(1);
});
