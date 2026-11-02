import asyncio
import os
import sys
import json
import numpy as np
import scipy.stats as stats

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
token = os.getenv('DERIV_API_TOKEN')
app_id = os.getenv('DERIV_APP_ID')

async def fetch_ticks(client, symbol, total_count=5000):
    prices = []
    times = []
    end = 'latest'
    while len(prices) < total_count:
        batch_size = min(5000, total_count - len(prices))
        req = {
            'ticks_history': symbol,
            'end': end,
            'count': batch_size,
            'style': 'ticks'
        }
        resp = await client.send_request(req)
        if 'error' in resp:
            print(f"Error fetching {symbol}: {resp['error']}")
            break
        history = resp.get('history', {})
        batch_prices = history.get('prices', [])
        batch_times = history.get('times', [])
        if not batch_prices:
            break
        if prices:
            prices = batch_prices[:-1] + prices
            times = batch_times[:-1] + times
        else:
            prices = batch_prices
            times = batch_times
        end = str(batch_times[0])
        if len(batch_prices) < 2:
            break
        await asyncio.sleep(0.1)
    return np.array(prices, dtype=np.float64), np.array(times, dtype=np.int64)

async def main():
    client = DerivClient(app_id=app_id, api_token=token, use_demo=True)
    await client.connect()
    print("Connected! Account:", client.account_id)
    
    baskets = ['WLDUSD', 'WLDEUR', 'WLDGBP', 'WLDAUD', 'WLDXAU']
    
    # 1. Fetch concurrent ticks for all baskets and real forex pairs
    print("\n=== FETCHING BASKET TICKS & REAL FOREX PAIRS ===")
    data = {}
    for sym in baskets + ['frxEURUSD', 'frxGBPUSD', 'frxAUDUSD']:
        p, t = await fetch_ticks(client, sym, total_count=3000)
        data[sym] = (p, t)
        print(f"  {sym:12s}: {len(p)} ticks. Range: {p[0]:.4f} -> {p[-1]:.4f}")

    # Check alignment and cross-correlations
    # Let's find common timestamps between WLDEUR, WLDUSD and frxEURUSD
    t_eur = data['WLDEUR'][1]
    t_usd = data['WLDUSD'][1]
    t_real = data['frxEURUSD'][1]
    
    # Let's map timestamps to prices
    map_eur = dict(zip(data['WLDEUR'][1], data['WLDEUR'][0]))
    map_usd = dict(zip(data['WLDUSD'][1], data['WLDUSD'][0]))
    map_real = dict(zip(data['frxEURUSD'][1], data['frxEURUSD'][0]))
    
    common_ts = sorted(list(set(map_eur.keys()) & set(map_usd.keys()) & set(map_real.keys())))
    print(f"\nCommon aligned timestamps between WLDEUR, WLDUSD, frxEURUSD: {len(common_ts)}")
    
    if len(common_ts) > 50:
        p_eur = np.array([map_eur[ts] for ts in common_ts])
        p_usd = np.array([map_usd[ts] for ts in common_ts])
        p_real = np.array([map_real[ts] for ts in common_ts])
        
        ret_eur = np.diff(np.log(p_eur))
        ret_usd = np.diff(np.log(p_usd))
        ret_real = np.diff(np.log(p_real))
        
        # Implied EURUSD return from basket: ret(WLDEUR) - ret(WLDUSD)
        ret_implied = ret_eur - ret_usd
        
        corr_real_implied = np.corrcoef(ret_real, ret_implied)[0, 1]
        corr_eur_real = np.corrcoef(ret_eur, ret_real)[0, 1]
        corr_usd_real = np.corrcoef(ret_usd, ret_real)[0, 1]
        
        print(f"\n--- CORRELATION TEST (Real Forex vs Basket) ---")
        print(f"Corr(ret_implied(WLDEUR/WLDUSD), ret(frxEURUSD)): {corr_real_implied:+.4f}")
        print(f"Corr(ret(WLDEUR), ret(frxEURUSD)):               {corr_eur_real:+.4f}")
        print(f"Corr(ret(WLDUSD), ret(frxEURUSD)):               {corr_usd_real:+.4f}")
        
        if abs(corr_real_implied) > 0.8:
            print("  ==> BASKETS ARE STRONGLY DERIVED FROM REAL FOREX!")
        else:
            print("  ==> BASKETS ARE NOT DIRECTLY DRIVEN BY REAL FOREX (Synthetic PRNG or distinct weighting)!")

    # 2. Check contract proposals and pricing on WLDUSD and WLDEUR
    print("\n=== CONTRACT PROPOSALS & MULTIPLIERS ON WLDUSD / WLDEUR ===")
    for sym in ['WLDUSD', 'WLDEUR']:
        for ct in ['MULTUP', 'MULTDOWN']:
            for mult in [50, 100, 200, 400]:
                prop = await client.send_request({
                    'proposal': 1,
                    'amount': 10.0,
                    'basis': 'stake',
                    'contract_type': ct,
                    'currency': 'USD',
                    'underlying_symbol': sym,
                    'multiplier': mult,
                    'cancellation': '5m'
                })
                if 'error' not in prop:
                    p = prop.get('proposal', {})
                    fee = p.get('cancellation', {}).get('ask_price')
                    comm = p.get('commission')
                    print(f"  {sym} {ct} {mult}x (5m cancel): fee=${fee} comm=${comm} ask=${p.get('ask_price')}")
                else:
                    err = prop['error'].get('message')
                    # Try without cancellation
                    prop2 = await client.send_request({
                        'proposal': 1,
                        'amount': 10.0,
                        'basis': 'stake',
                        'contract_type': ct,
                        'currency': 'USD',
                        'underlying_symbol': sym,
                        'multiplier': mult
                    })
                    if 'error' not in prop2:
                        p2 = prop2.get('proposal', {})
                        comm = p2.get('commission')
                        print(f"  {sym} {ct} {mult}x (no cancel): comm=${comm} ask=${p2.get('ask_price')}")
                    else:
                        print(f"  {sym} {ct} {mult}x: Error = {prop2['error'].get('message')}")

    # 3. Check CALL / PUT proposals on WLDUSD and WLDEUR
    print("\n=== CALL / PUT PROPOSALS ON WLDUSD / WLDEUR ===")
    for sym in ['WLDUSD', 'WLDEUR']:
        for ct in ['CALL', 'CALLE', 'PUT', 'PUTE']:
            prop = await client.send_request({
                'proposal': 1,
                'amount': 10.0,
                'basis': 'stake',
                'contract_type': ct,
                'currency': 'USD',
                'underlying_symbol': sym,
                'duration': 15,
                'duration_unit': 'm'
            })
            p = prop.get('proposal', {})
            payout = p.get('payout')
            ask = p.get('ask_price')
            ratio_str = f"{payout/ask:.4f}" if (payout and ask) else "N/A"
            print(f"  {sym} {ct:5s} 15m: Payout=${payout} Ask=${ask} Ratio={ratio_str}")

    if client.ws:
        await client.ws.close()

if __name__ == '__main__':
    asyncio.run(main())
