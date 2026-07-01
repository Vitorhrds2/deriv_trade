import csv
from datetime import datetime
from collections import defaultdict
import math

# Analysis script to find the optimal PRICE_SHOCK_CEILING
# We want to see how the "2-second sustain rate" drops as the jump size increases.

def analyze_ceiling(csv_file):
    print(f"Loading {csv_file}...")
    
    # Store prices by timestamp (ms)
    prices_by_ms = {}
    with open(csv_file, 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or not row[0].isdigit():
                continue
            ts_ms = int(row[5]) // 1000 # Convert microsecond to ms
            price = float(row[1])
            prices_by_ms[ts_ms] = price
            
    sorted_ts = sorted(prices_by_ms.keys())
    
    # We will simulate the HFT jump detection: jump > $50 within 500ms
    # Then we categorize by jump size and check if it sustained after 2 seconds.
    
    jump_brackets = {
        "50-60": {"total": 0, "sustained": 0, "reverted": 0},
        "60-70": {"total": 0, "sustained": 0, "reverted": 0},
        "70-80": {"total": 0, "sustained": 0, "reverted": 0},
        "80-90": {"total": 0, "sustained": 0, "reverted": 0},
        "90-100": {"total": 0, "sustained": 0, "reverted": 0},
        "100+": {"total": 0, "sustained": 0, "reverted": 0}
    }
    
    # Helper to find price at target_ts or closest after
    def get_price_at(target_ts):
        # Binary search for closest
        left, right = 0, len(sorted_ts) - 1
        best_ts = sorted_ts[-1]
        while left <= right:
            mid = (left + right) // 2
            if sorted_ts[mid] >= target_ts:
                best_ts = sorted_ts[mid]
                right = mid - 1
            else:
                left = mid + 1
        # Se for mais de 5 segundos de diferença, não tem dado
        if best_ts - target_ts > 5000:
            return None
        return prices_by_ms[best_ts]

    for i in range(len(sorted_ts)):
        ts = sorted_ts[i]
        price = prices_by_ms[ts]
        
        # Look back up to 500ms
        past_ts = ts - 500
        past_price = None
        # Naive lookup for past price
        for j in range(i-1, -1, -1):
            if sorted_ts[j] <= past_ts:
                past_price = prices_by_ms[sorted_ts[j]]
                break
        
        if past_price is None:
            continue
            
        diff = price - past_price
        
        # Só olhamos pulos absolutos maiores que 50
        if abs(diff) >= 50.0:
            # Check price 2.0s (2000ms) after 'ts'
            future_ts = ts + 2000
            future_price = get_price_at(future_ts)
            
            if future_price is not None:
                # Did it sustain?
                # If UP jump, future_price must be > past_price (or maybe > price - something?)
                # Actually, our bot's logic for win:
                # We buy UP at `price`, we need to sell at > `price` + commission.
                # Since we don't know commission perfectly, let's just see if future_price > price
                # Or at least if future_price didn't revert significantly.
                # Reverting fully means future_price <= past_price
                
                # A true sustain means it held at least the jump. 
                # Let's see if future_price is closer to `price` or `past_price`.
                revert_amount = diff - (future_price - past_price)
                
                # If it's an UP jump (diff > 0):
                # price is High, past_price is Low. future_price > price means it kept going up.
                # future_price < past_price means full revert.
                
                # We will define "Sustained" as: future_price didn't retrace more than 50% of the jump.
                # Meaning if it jumped $100, future_price is at least $50 above past_price.
                if diff > 0:
                    sustained = (future_price - past_price) > (diff * 0.5)
                else:
                    sustained = (future_price - past_price) < (diff * 0.5)
                    
                abs_diff = abs(diff)
                
                if 50 <= abs_diff < 60:
                    bracket = "50-60"
                elif 60 <= abs_diff < 70:
                    bracket = "60-70"
                elif 70 <= abs_diff < 80:
                    bracket = "70-80"
                elif 80 <= abs_diff < 90:
                    bracket = "80-90"
                elif 90 <= abs_diff < 100:
                    bracket = "90-100"
                else:
                    bracket = "100+"
                    
                jump_brackets[bracket]["total"] += 1
                if sustained:
                    jump_brackets[bracket]["sustained"] += 1
                else:
                    jump_brackets[bracket]["reverted"] += 1

    print("\n=== ANÁLISE DE SUSTENTAÇÃO POR TAMANHO DO PULO (2 SEGUNDOS) ===")
    print("Sustentação = O preço não retraiu mais que 50% do pulo original após 2 segundos.")
    print(f"{'Bracket':<10} | {'Total':<8} | {'Sustained':<10} | {'Reverted':<10} | {'Win Rate'}")
    print("-" * 55)
    for b, data in jump_brackets.items():
        total = data["total"]
        if total > 0:
            rate = (data["sustained"] / total) * 100
        else:
            rate = 0.0
        print(f"{b:<10} | {total:<8} | {data['sustained']:<10} | {data['reverted']:<10} | {rate:.1f}%")

if __name__ == "__main__":
    analyze_ceiling("BTCUSDT-aggTrades-2026-06-25.csv")
