#!/usr/bin/env python3
"""
D10: DeFi Liquidation Opportunity Scan (Aave V3 via direct RPC).

Hypothesis: Aave V3 liquidations offer a profitable MEV opportunity.
When a borrower's health factor drops below 1.0, liquidators can repay debt
and seize collateral + bonus (5-10%). This scan measures:

D10a — Historical liquidation events: fetch LiquidationCall event logs from
       the Aave V3 Pool contract via eth_getLogs (free public RPC).
D10b — Estimate profitability: bonus %, total volume, frequency.
D10c — Competition/latency analysis: theoretical edge vs MEV bot reality.

No API keys needed — uses free public RPC endpoints. Read-only, no transactions.
"""
import argparse
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from typing import Optional

UA = {"User-Agent": "defi-liq-scan/1.0 (research; read-only)", "Content-Type": "application/json"}

# Aave V3 Pool contract addresses (from aave-address-book)
POOLS = {
    "ethereum": {
        "address": "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
        "rpc": "https://1rpc.io/eth",
        "rpc_backup": "https://cloudflare-eth.com",
        "block_time_s": 12,
        "log_chunk_size": 50,
        "liquidation_bonus": {"WETH": 8.5, "WBTC": 15, "USDC": 5, "DAI": 5, "USDT": 5,
                              "LINK": 10, "wstETH": 6, "AAVE": 10, "FRAX": 5},
    },
    "polygon": {
        "address": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
        "rpc": "https://polygon-rpc.com",
        "rpc_backup": "https://polygon-bor-rpc.publicnode.com",
        "block_time_s": 2,
        "log_chunk_size": 2000,
        "liquidation_bonus": {"WMATIC": 10, "USDC": 5, "DAI": 5, "USDT": 5, "WETH": 8.5},
    },
    "arbitrum": {
        "address": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
        "rpc": "https://arb1.arbitrum.io/rpc",
        "rpc_backup": "https://arbitrum-one-rpc.publicnode.com",
        "block_time_s": 0.25,
        "log_chunk_size": 5000,
        "liquidation_bonus": {"WETH": 8.5, "USDC": 5, "ARB": 10, "USDT": 5, "WBTC": 15},
    },
    "base": {
        "address": "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",
        "rpc": "https://mainnet.base.org",
        "rpc_backup": "https://base-rpc.publicnode.com",
        "block_time_s": 2,
        "log_chunk_size": 5000,
        "liquidation_bonus": {"WETH": 8.5, "USDC": 5, "cbETH": 6},
    },
}

# LiquidationCall event topic hash
# event LiquidationCall(address indexed collateralAsset, address indexed debtAsset,
#   address indexed user, uint256 debtToCover, uint256 liquidatedCollateralAmount,
#   address liquidator, bool receiveAToken)
LIQUIDATION_CALL_TOPIC = "0xe413a321e8681d831f4dbccbca790d2952b56f977908e45be37335533e005286"

# Token metadata
TOKEN_SYMBOLS = {
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "WETH",
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": "WBTC",
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC",
    "0x6b175474e89094c44da98b954eedeac495271d0f": "DAI",
    "0xdac17f958d2ee523a2206206994597c13d831ec7": "USDT",
    "0x514910771af9ca656af840dff83e8264ecf986ca": "LINK",
    "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0": "wstETH",
    "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9": "AAVE",
    "0x853d955acef822db058eb8505911ed77f175b99e": "FRAX",
    "0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270": "WMATIC",
    "0x2791bca1f2de4661ed88a30c99a7a9449aa84174": "USDC.e",
    "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359": "USDC",
    "0x82af49447d8a07e3bd95bd0d56f35241523fbab1": "WETH",
    "0x4200000000000000000000000000000000000006": "WETH",
    "0x833589fcd6edb6e08f4c7c32d4f71b54bd4d0b1c": "USDC",
    "0x2ae3f1ec7f1f5012cfeab0185fb5dabeafc1f5d7": "cbETH",
}

TOKEN_DECIMALS = {
    "WETH": 18, "WBTC": 8, "USDC": 6, "DAI": 18, "USDT": 6,
    "LINK": 18, "wstETH": 18, "AAVE": 18, "FRAX": 18,
    "WMATIC": 18, "USDC.e": 6, "ARB": 18, "cbETH": 18,
}


def rpc_post(url: str, payload: dict, timeout: int = 15) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=UA, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def get_latest_block(url: str) -> int:
    result = rpc_post(url, {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1})
    return int(result.get("result", "0x0"), 16)


def get_block_timestamp(url: str, block_hex: str) -> int:
    result = rpc_post(url, {"jsonrpc": "2.0", "method": "eth_getBlockByNumber",
                            "params": [block_hex, False], "id": 1})
    block = result.get("result", {})
    return int(block.get("timestamp", "0x0"), 16)


def fetch_liquidation_logs(url: str, pool_address: str, from_block: int, to_block: int) -> list:
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_getLogs",
        "params": [{
            "address": pool_address,
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
            "topics": [LIQUIDATION_CALL_TOPIC],
        }],
        "id": 1,
    }
    result = rpc_post(url, payload, timeout=30)
    if "error" in result:
        raise Exception(f"RPC error: {result['error']}")
    return result.get("result", [])


def decode_liquidation_log(log: dict, chain: str) -> Optional[dict]:
    topics = log.get("topics", [])
    data = log.get("data", "0x")
    if len(topics) < 4:
        return None

    collateral_asset = "0x" + topics[1][-40:]
    debt_asset = "0x" + topics[2][-40:]
    user = "0x" + topics[3][-40:]

    clean_data = data[2:] if data.startswith("0x") else data
    if len(clean_data) < 256:
        return None

    debt_to_cover = int(clean_data[0:64], 16)
    liquidated_collateral_amount = int(clean_data[64:128], 16)

    block_num = int(log.get("blockNumber", "0x0"), 16)
    tx_hash = log.get("transactionHash", "")

    coll_sym = get_token_symbol(collateral_asset)
    debt_sym = get_token_symbol(debt_asset)
    coll_dec = TOKEN_DECIMALS.get(coll_sym, 18)
    debt_dec = TOKEN_DECIMALS.get(debt_sym, 18)

    return {
        "chain": chain,
        "block": block_num,
        "tx_hash": tx_hash,
        "collateral_symbol": coll_sym,
        "debt_symbol": debt_sym,
        "user": user,
        "collateral_amount": liquidated_collateral_amount / (10 ** coll_dec),
        "debt_amount": debt_to_cover / (10 ** debt_dec),
    }


def get_token_symbol(address: str) -> str:
    addr_lower = address.lower()
    for key, sym in TOKEN_SYMBOLS.items():
        if key.lower() == addr_lower:
            return sym
    return address[:10]


def scan_chain(chain: str, config: dict, blocks_back: int) -> dict:
    pool = config["address"]
    rpc = config["rpc"]

    print(f"\n  [{chain}] Pool: {pool}")
    print(f"    RPC: {rpc}")

    try:
        latest = get_latest_block(rpc)
        print(f"    Latest block: {latest}")
    except Exception as e:
        print(f"    Primary RPC failed: {e}")
        try:
            rpc = config["rpc_backup"]
            print(f"    Trying backup: {rpc}")
            latest = get_latest_block(rpc)
            print(f"    Latest block: {latest}")
        except Exception as e2:
            print(f"    Backup also failed: {e2}")
            return {"chain": chain, "error": str(e2), "liquidations": []}

    CHUNK_SIZE = config.get("log_chunk_size", 2000)
    from_block = max(0, latest - blocks_back)
    all_logs = []

    days_estimate = blocks_back * config["block_time_s"] / 86400
    print(f"    Scanning {blocks_back} blocks (~{days_estimate:.1f} days), chunks of {CHUNK_SIZE}")

    current = from_block
    errors = 0
    while current <= latest:
        end = min(current + CHUNK_SIZE - 1, latest)
        try:
            logs = fetch_liquidation_logs(rpc, pool, current, end)
            all_logs.extend(logs)
            if logs:
                print(f"      Blocks {current}-{end}: {len(logs)} liquidations")
            current = end + 1
            time.sleep(0.15)
        except Exception as e:
            errors += 1
            if errors > 10:
                print(f"    Too many errors, stopping scan for {chain}")
                break
            # Try smaller chunk
            mid = (current + end) // 2
            if mid > current:
                try:
                    logs = fetch_liquidation_logs(rpc, pool, current, mid)
                    all_logs.extend(logs)
                    current = mid + 1
                    time.sleep(0.3)
                except:
                    print(f"      Blocks {current}-{mid}: error, skipping")
                    current = mid + 1
                    time.sleep(0.5)
            else:
                current = end + 1
                time.sleep(0.5)

    print(f"    Total events: {len(all_logs)}")

    liquidations = []
    for log in all_logs:
        decoded = decode_liquidation_log(log, chain)
        if decoded:
            bonus_pct = config["liquidation_bonus"].get(decoded["collateral_symbol"], 7.5)
            decoded["estimated_bonus_pct"] = bonus_pct
            liquidations.append(decoded)

    # Get time span
    if liquidations:
        first_block = liquidations[0]["block"]
        last_block = liquidations[-1]["block"]
        try:
            first_ts = get_block_timestamp(rpc, hex(first_block))
            last_ts = get_block_timestamp(rpc, hex(last_block))
            time_span_h = (last_ts - first_ts) / 3600
            print(f"    Span: {datetime.fromtimestamp(first_ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')} → "
                  f"{datetime.fromtimestamp(last_ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC "
                  f"({time_span_h:.1f}h)")
            if time_span_h > 0:
                print(f"    Rate: {len(liquidations)/time_span_h:.2f} liquidations/hour")
        except:
            pass

    return {"chain": chain, "liquidations": liquidations, "total_found": len(liquidations)}


def run_scan(output_file: str, chains: list, blocks_back: int):
    print("D10: DeFi Liquidation Opportunity Scan (Aave V3 via RPC)")
    print(f"Chains: {', '.join(chains)}")
    print(f"Method: eth_getLogs on LiquidationCall event (no API key)")
    print(f"{'='*80}")

    all_results = []
    all_liquidations = []

    for chain in chains:
        config = POOLS.get(chain)
        if not config:
            continue
        result = scan_chain(chain, config, blocks_back)
        all_results.append(result)
        all_liquidations.extend(result.get("liquidations", []))

    output = {
        "results": all_results,
        "liquidations": all_liquidations,
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "blocks_scanned": blocks_back,
    }
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2, default=str)

    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY — {len(chains)} chains\n")

    if not all_liquidations:
        print("No liquidation events found. Possible causes:")
        print("  - RPC blocked eth_getLogs (try different RPC)")
        print("  - Block range too small")
        print("  - No liquidations in the period")
    else:
        print(f"Total liquidation events: {len(all_liquidations)}\n")

        by_chain = {}
        for l in all_liquidations:
            by_chain.setdefault(l["chain"], []).append(l)

        print(f"{'Chain':12s} {'Events':>7s} {'Collaterals':>30s} {'Avg Bonus':>10s}")
        print("-" * 65)
        for chain, liqs in sorted(by_chain.items()):
            collaterals = set(l["collateral_symbol"] for l in liqs)
            avg_bonus = sum(l["estimated_bonus_pct"] for l in liqs) / len(liqs)
            print(f"{chain:12s} {len(liqs):7d} {', '.join(sorted(collaterals)):30s} {avg_bonus:9.1f}%")

        # Top 10 by debt
        print(f"\nTop 10 by debt amount:")
        for l in sorted(all_liquidations, key=lambda x: x["debt_amount"], reverse=True)[:10]:
            print(f"  {l['chain']:10s} blk={l['block']:>10d} {l['collateral_symbol']:8s}→{l['debt_symbol']:8s} "
                  f"debt={l['debt_amount']:>14.4f} bonus={l['estimated_bonus_pct']:.1f}%")

        # Profitability
        print(f"\n{'='*80}")
        print(f"PROFITABILITY ANALYSIS\n")

        print(f"  Total events: {len(all_liquidations)}")
        print(f"  Avg bonus %: {sum(l['estimated_bonus_pct'] for l in all_liquidations)/len(all_liquidations):.1f}%")

        # Stablecoin debt liquidations (where we can estimate USD)
        stable = [l for l in all_liquidations if l["debt_symbol"] in ("USDC", "DAI", "USDT", "USDC.e")]
        if stable:
            total_stable_debt = sum(l["debt_amount"] for l in stable)
            avg_stable_debt = total_stable_debt / len(stable)
            total_est_bonus = sum(l["debt_amount"] * l["estimated_bonus_pct"] / 100 for l in stable)
            print(f"\n  Stablecoin debt liquidations: {len(stable)}")
            print(f"  Total stable debt liquidated: ${total_stable_debt:,.0f}")
            print(f"  Total estimated bonus: ${total_est_bonus:,.0f}")
            print(f"  Avg bonus per event: ${total_est_bonus/len(stable):,.0f}")

        print(f"\n  COMPETITION REALITY:")
        print(f"  - MEV bots detect + execute liquidations in <1 block (~12s ETH)")
        print(f"  - Our RPC scan latency: ~30-60s (block time + RPC + processing)")
        print(f"  - Most liquidations captured by 1-3 specialized bots")
        print(f"  - Gas: $20-100/tx (ETH), $0.10-0.50 (L2)")
        print(f"  - Realistic capture rate for new bot: <1%")
        print(f"  - Flash loans: no capital needed, but MEV competition is fierce")


def main():
    parser = argparse.ArgumentParser(description="D10 DeFi Liquidation Scan")
    parser.add_argument("--output", type=str, default="defi_liquidation_samples.json")
    parser.add_argument("--chains", type=str, nargs="+",
                        default=["ethereum", "polygon", "arbitrum", "base"])
    parser.add_argument("--blocks", type=int, default=100000)
    args = parser.parse_args()

    output_path = os.path.join(os.path.dirname(__file__), args.output)
    run_scan(output_path, args.chains, args.blocks)


if __name__ == "__main__":
    main()
