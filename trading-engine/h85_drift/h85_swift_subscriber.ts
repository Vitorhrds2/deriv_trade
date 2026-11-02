/**
 * H85 — Velocity Exchange (formerly Drift) SWIFT API Maker Rebate Scan (TypeScript)
 *
 * Uses the official Velocity SDK SwiftOrderSubscriber to listen for
 * taker order intents 100-500ms before on-chain submission.
 *
 * No credentials needed — uses a throwaway keypair for SWIFT auth.
 * Read-only: listens to orders, compares to Coinbase price, calculates EV.
 *
 * Migration: @drift-labs/sdk → @velocity-exchange/sdk (July 2026)
 *  - DriftClient → VelocityClient
 *  - DriftEnv → VelocityEnv
 *  - Program ID: vELoC1audYbSYVRXn1vPaV8Axoa9oU6BYmNGZZBDZ1P
 *  - Quote asset: USDT (not USDC) on mainnet
 *  - SWIFT fills now evaluated at projected landing slot (Section 5.20)
 *
 * Usage: npx tsx h85_swift_subscriber.ts
 */
import { Connection, Keypair } from '@solana/web3.js';
import {
  VelocityClient,
  initialize,
  Wallet,
  SwiftOrderSubscriber,
  type SwiftOrderMessage,
  type SignedMsgOrderParamsMessage,
} from '@velocity-exchange/sdk';

// ─── Config ───────────────────────────────────────────────────────────
const SOLANA_RPC = 'https://api.mainnet-beta.solana.com';
const DURATION_SECONDS = 7200; // 2 hours total (all markets simultaneous)
const MARKETS = [
  { name: 'SOL-PERP', index: 0, coinbase: 'SOL' },
  { name: 'BTC-PERP', index: 1, coinbase: 'BTC' },
  { name: 'ETH-PERP', index: 2, coinbase: 'ETH' },
  { name: 'HYPE-PERP', index: 3, coinbase: 'HYPE' },
];

// Coinbase for reference price (Binance blocked in US AWS)
async function getCoinbasePrice(symbol: string): Promise<number | null> {
  try {
    const resp = await fetch(`https://api.coinbase.com/v2/prices/${symbol}-USD/spot`);
    if (resp.ok) {
      const data = await resp.json() as any;
      return parseFloat(data.data.amount);
    }
  } catch (e) {
    // ignore
  }
  return null;
}

// ─── Main ─────────────────────────────────────────────────────────────
async function main() {
  console.log('='.repeat(90));
  console.log('H85 — Velocity Exchange (formerly Drift) SWIFT API Maker Rebate Scan');
  console.log('='.repeat(90));
  console.log(`  Solana RPC: ${SOLANA_RPC}`);
  console.log(`  Markets: ${MARKETS.map(m => m.name).join(', ')}`);
  console.log(`  Duration: ${DURATION_SECONDS}s per market`);
  console.log();

  // Setup Solana connection + throwaway wallet
  const connection = new Connection(SOLANA_RPC, 'processed');
  const wallet = new Wallet(Keypair.generate());

  console.log('  [Setup] Initializing Velocity SDK...');
  const sdkConfig = initialize({ env: 'mainnet-beta' as any });

  const velocityClient = new VelocityClient({
    connection,
    wallet,
    env: sdkConfig.env,
    accountSubscription: {
      type: 'websocket',
      commitment: 'processed',
    },
  });

  try {
    console.log('  [Setup] Subscribing VelocityClient...');
    await velocityClient.subscribe();
    console.log('  [Setup] VelocityClient subscribed OK');
  } catch (e: any) {
    console.log(`  [Setup] VelocityClient subscribe error: ${e.message}`);
    console.log('  [Setup] Continuing with SWIFT subscriber only...');
  }

  const allResults: any = {};
  const startTime = Date.now();

  // Subscribe to ALL markets simultaneously
  console.log(`\n  [Setup] Subscribing to ${MARKETS.length} markets simultaneously...`);

  for (const market of MARKETS) {
    console.log(`\n  [${market.name}] Setting up subscriber...`);

    // Get reference price
    const coinbaseSym = market.coinbase || market.name.split('-')[0];
    const refPrice = await getCoinbasePrice(coinbaseSym);
    if (refPrice) {
      console.log(`  [${market.name}] Coinbase ${coinbaseSym}-USD: $${refPrice.toFixed(4)}`);
    } else {
      console.log(`  [${market.name}] Could not get Coinbase price for ${coinbaseSym}`);
    }

    // Track SWIFT messages
    const swiftMessages: any[] = [];
    let msgCount = 0;

    // Create SWIFT subscriber for this market
    const swiftSubscriber = new SwiftOrderSubscriber({
      velocityClient: velocityClient,
      velocityEnv: 'mainnet-beta' as any,
      marketIndexes: [market.index],
      keypair: Keypair.generate(),
    });

    // Define order callback
    const onOrder = async (
      orderMessageRaw: SwiftOrderMessage,
      signedMessage: SignedMsgOrderParamsMessage | any,
      isDelegateSigner?: boolean
    ) => {
      msgCount++;
      const ts = Date.now();
      const elapsed = (ts - startTime) / 1000;

      // Extract order details
      const orderInfo: any = {
        market: market.name,
        ts,
        elapsed_s: elapsed.toFixed(1),
        msgCount,
        isDelegateSigner: isDelegateSigner || false,
      };

      // Try to extract price from signed message
      if (signedMessage) {
        try {
          const params = (signedMessage as any).signedMsgOrderParams ||
                         (signedMessage as any).params ||
                         signedMessage;
          if (params.price !== undefined) {
            const rawPrice = params.price.toNumber ? params.price.toNumber() : Number(params.price);
            const price1e6 = rawPrice / 1e6;
            const price1e9 = rawPrice / 1e9;
            const price1e10 = rawPrice / 1e10;
            let price = price1e6;
            if (refPrice && refPrice > 0) {
              const candidates = [
                { scale: '1e6', val: price1e6 },
                { scale: '1e9', val: price1e9 },
                { scale: '1e10', val: price1e10 },
                { scale: 'raw', val: rawPrice },
              ];
              let best = candidates[0];
              for (const c of candidates) {
                if (Math.abs(c.val - refPrice) < Math.abs(best.val - refPrice)) {
                  best = c;
                }
              }
              price = best.val;
              orderInfo.price_scale = best.scale;
              orderInfo.raw_price = rawPrice;
            }
            orderInfo.price = price;
            if (refPrice && refPrice > 0) {
              orderInfo.price_deviation_bps =
                ((price - refPrice) / refPrice) * 10000;
            }
          }
          if (params.baseAmount !== undefined) {
            const rawAmt = params.baseAmount.toNumber ? params.baseAmount.toNumber() : Number(params.baseAmount);
            orderInfo.baseAmount = rawAmt / 1e9;
          }
          if (params.direction !== undefined) {
            const dir = params.direction;
            orderInfo.direction = typeof dir === 'object' ? (dir.long ? 'buy' : 'sell') : (typeof dir === 'number' ? (dir === 0 ? 'buy' : 'sell') : dir);
          }
          if (params.orderType !== undefined) orderInfo.orderType = params.orderType;
          if (params.marketIndex !== undefined) orderInfo.marketIndex = params.marketIndex;
          if (params.auctionDuration !== undefined) orderInfo.auctionDuration = params.auctionDuration;
        } catch (e: any) {
          orderInfo.parseError = `could not extract params: ${e.message}`;
        }
      }

      swiftMessages.push(orderInfo);

      // Log first 10 messages and every 50th
      if (msgCount <= 10 || msgCount % 50 === 0) {
        console.log(`  [${market.name}] #${msgCount} (${elapsed.toFixed(0)}s):`, JSON.stringify(orderInfo).slice(0, 200));
      }
    };

    // Subscribe to SWIFT feed
    try {
      await swiftSubscriber.subscribe(onOrder);
      console.log(`  [${market.name}] Subscribed!`);
    } catch (e: any) {
      console.log(`  [${market.name}] Subscribe error: ${e.message}`);
    }

    allResults[market.name] = {
      swift_msg_count: 0,
      ref_price_samples: 0,
      initial_ref_price: refPrice,
      messages: swiftMessages,
      ref_prices: [] as any[],
      subscriber: swiftSubscriber,
      coinbaseSym,
    };

    // Small delay between subscriptions to avoid overwhelming
    await new Promise(r => setTimeout(r, 2000));
  }

  console.log(`\n  All ${MARKETS.length} markets subscribed. Listening for ${DURATION_SECONDS}s (${DURATION_SECONDS/60}min)...`);
  console.log(`  Start time: ${new Date(startTime).toISOString()}`);
  console.log(`  End time: ${new Date(startTime + DURATION_SECONDS * 1000).toISOString()}`);

  // Wait for duration, polling reference prices every 30s and printing status every 60s
  const waitStart = Date.now();
  while (Date.now() - waitStart < DURATION_SECONDS * 1000) {
    await new Promise(r => setTimeout(r, 30000));

    // Update reference prices
    for (const market of MARKETS) {
      const r = allResults[market.name];
      if (!r) continue;
      const p = await getCoinbasePrice(r.coinbaseSym);
      if (p) {
        r.ref_prices.push({ ts: Date.now(), price: p });
        r.ref_price_samples = r.ref_prices.length;
      }
      r.swift_msg_count = r.messages.length;
    }

    // Status update every 60s
    const elapsed = (Date.now() - waitStart) / 1000;
    if (elapsed % 60 < 30) {
      const totalMsgs = MARKETS.reduce((sum, m) => sum + (allResults[m.name]?.swift_msg_count || 0), 0);
      console.log(`\n  [Status] ${elapsed.toFixed(0)}s elapsed | ${totalMsgs} total msgs | ${new Date().toISOString()}`);
      for (const market of MARKETS) {
        const r = allResults[market.name];
        if (r) {
          console.log(`    ${market.name}: ${r.swift_msg_count} msgs, ref=$${r.initial_ref_price?.toFixed(2) || 'N/A'}`);
        }
      }
    }
  }

  // Unsubscribe all
  for (const market of MARKETS) {
    const r = allResults[market.name];
    if (r?.subscriber) {
      try { await r.subscriber.unsubscribe(); } catch (e: any) {}
      delete r.subscriber; // Don't serialize the subscriber
    }
  }

  // Print per-market summaries
  for (const market of MARKETS) {
    const r = allResults[market.name];
    if (!r) continue;
    console.log(`\n  ${market.name} Summary:`);
    console.log(`    SWIFT messages received: ${r.swift_msg_count}`);
    console.log(`    Reference price samples: ${r.ref_price_samples}`);

    if (r.messages.length > 0) {
      const deviations = r.messages
        .filter((m: any) => m.price_deviation_bps !== undefined)
        .map((m: any) => m.price_deviation_bps);
      if (deviations.length > 0) {
        const meanDev = deviations.reduce((a: number, b: number) => a + b, 0) / deviations.length;
        const maxDev = Math.max(...deviations.map(Math.abs));
        console.log(`    Price deviations from Coinbase:`);
        console.log(`      mean: ${meanDev.toFixed(2)}bps  max: ${maxDev.toFixed(2)}bps`);
        console.log(`      samples: ${deviations.length}`);
      }

      const toxicCount = r.messages.filter(
        (m: any) => m.price_deviation_bps !== undefined && Math.abs(m.price_deviation_bps) > 20
      ).length;
      const nonToxicCount = r.swift_msg_count - toxicCount;
      console.log(`    Toxic orders (>20bps deviation): ${toxicCount}/${r.swift_msg_count}`);
      console.log(`    Non-toxic (fillable): ${nonToxicCount}/${r.swift_msg_count}`);
      if (r.swift_msg_count > 0) {
        const toxicRate = toxicCount / r.swift_msg_count;
        console.log(`    Toxic rate: ${(toxicRate * 100).toFixed(1)}%`);
        console.log(`    With SWIFT: reject toxic (${(toxicRate * 100).toFixed(1)}%), fill non-toxic (${((1-toxicRate) * 100).toFixed(1)}%)`);
      }
    }

    r.messages = r.messages.slice(0, 500); // save up to 500
    r.ref_prices = r.ref_prices.slice(-60); // keep last 60 ref prices
  }

  // Final verdict
  console.log(`\n${'='.repeat(90)}`);
  console.log('VEREDITO FINAL — H85 Drift SWIFT Maker Rebate');
  console.log('='.repeat(90));

  const totalMsgs = Object.values(allResults).reduce((sum: number, r: any) => sum + r.swift_msg_count, 0);
  console.log(`\n  Total SWIFT messages: ${totalMsgs}`);

  if (totalMsgs > 0) {
    console.log(`  SWIFT FEED IS ACTIVE via Drift SDK`);
    console.log(`  Next steps:`);
    console.log(`    1. Fund Solana wallet with USDC for Drift collateral`);
    console.log(`    2. Implement Post-Only maker order placement`);
    console.log(`    3. Add toxic flow filter using Coinbase WS as oracle`);
    console.log(`    4. Start with small size to validate fill rates`);
  } else {
    console.log(`  No SWIFT messages received.`);
    console.log(`  Possible reasons:`);
    console.log(`    - Low trading activity during scan period`);
    console.log(`    - SWIFT not widely used by takers yet`);
    console.log(`    - Need longer scan duration`);
  }

  // Save results
  const fs = await import('fs');
  const output = {
    ts: new Date().toISOString(),
    hypothesis: 'H85',
    platform: 'Velocity Exchange (formerly Drift) (Solana)',
    swift_ws: 'via @velocity-exchange/sdk SwiftOrderSubscriber',
    results: allResults,
  };
  fs.writeFileSync('h85_drift_swift_results.json', JSON.stringify(output, null, 2));
  console.log(`\n  Results saved to h85_drift_swift_results.json`);

  // Cleanup
  try {
    await velocityClient.unsubscribe();
  } catch (e: any) {
    // ignore
  }
  process.exit(0);
}

main().catch(e => {
  console.error('Fatal error:', e);
  process.exit(1);
});
