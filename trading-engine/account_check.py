"""Validacao de conta (read-only): lista as contas e o account_type classificado
pela API da Deriv, para confirmar com EVIDENCIA qual e demo vs real antes de
qualquer ordem. Nao envia ordens, nao negocia - apenas GET na lista de contas.
"""
import json
import os
import sys
import urllib.request

from dotenv import load_dotenv

for _p in [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
    r"C:\Users\Usuario\Documents\Deriv_trade\trading-engine\.env",
]:
    if os.path.exists(_p):
        load_dotenv(_p)
        break

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")


def main():
    if not API_TOKEN or not APP_ID:
        print("ERRO: token/app_id ausentes (.env).")
        return
    req = urllib.request.Request("https://api.derivws.com/trading/v1/options/accounts")
    req.add_header("Authorization", f"Bearer {API_TOKEN}")
    req.add_header("Deriv-App-ID", str(APP_ID))
    with urllib.request.urlopen(req) as r:
        data = json.loads(r.read().decode())

    print("=" * 72)
    print("CONTAS VINCULADAS AO TOKEN (.env DERIV_API_TOKEN):")
    print("=" * 72)
    for acc in data.get("data", []):
        at = acc.get("account_type")
        flag = "  <== DEMO" if at == "demo" else "  <== REAL"
        print(f"  account_id={acc.get('account_id')} | type={at} | "
              f"currency={acc.get('currency')} | loginid={acc.get('loginid', acc.get('login_id','?'))}{flag}")
    print("=" * 72)
    print("\nJSON bruto (1a conta) para inspecao de campos:")
    if data.get("data"):
        print(json.dumps(data["data"][0], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
