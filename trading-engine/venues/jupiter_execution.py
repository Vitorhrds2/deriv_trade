"""Jupiter Prediction API -- camada de EXECUCAO (ExecutionVenue): cria ordem, assina transacao
Solana localmente, submete pra rede. Estende JupiterPredictionVenue (reusa list_events/
get_market/get_price/stream de leitura), adicionando o que precisa de carteira/assinatura.

STATUS (2026-07-02): mecanica de assinatura e o pipeline de /orders validados, EXECUCAO REAL
AINDA NAO TESTADA (carteira do usuario sem saldo).
- sign_transaction() validado com tx sintetica (instrucao Memo) + keypair de teste: assinatura
  bate exatamente com keypair.sign_message() chamado direto, message preservada -- mecanismo de
  deserializar/assinar/reserializar correto.
- get_balance() validado contra o RPC publico real (leitura, sem custo).
- create_order()/buy() testados com SOLANA_PRIVATE_KEY real do usuario contra a API real:
  - depositAmount abaixo de $5 -> 400 "Minimum order is $5" (limite da API, nao deste codigo).
  - $5 com carteira zerada -> 400 "INSUFFICIENT_FUNDS" -- confirma que a Jupiter CHECA saldo
    on-chain ANTES de devolver a tx nao assinada (nao da pra "ensaiar" sem fundos reais).
  - Ou seja: auth, lookup de market, derivacao de ownerPubkey e encoding do valor -- tudo
    validado ponta a ponta contra a API real. So falta saldo (~$5+ USDC + fracao de SOL pra
    fee) pra ver uma tx REAL da Jupiter (nao sintetica) sendo assinada e (opcionalmente,
    dry_run=False) submetida.
- submit_transaction() (sendTransaction via RPC) e o fluxo completo com dinheiro de verdade
  continuam NAO testados -- decisao explicita do usuario de nao depositar fundos ainda.

*** DINHEIRO REAL, MAINNET. LER ANTES DE USAR: ***
- POST /orders e POST /positions/{id}/claim devolvem uma transacao Solana NAO ASSINADA (base64).
  Este modulo assina localmente com SOLANA_PRIVATE_KEY (nunca sai da maquina, nunca vai pra
  Jupiter) e so SUBMETE pra rede (dinheiro se move de verdade) se dry_run=False for passado
  explicitamente em buy()/claim_position() -- o default e dry_run=True (cria a ordem do lado da
  Jupiter, assina localmente, mas NAO transmite pra Solana).
- Fees sao reais e nao triviais: ~5.3% do notional em alguns tamanhos, escalam perto de 50c (ver
  docs/phantom_ecosystem_findings.md) -- entra em qualquer calculo de EV antes de dry_run=False.
- SOLANA_PRIVATE_KEY: chave privada base58 (formato "Export Private Key" do Phantom), so em
  variavel de ambiente (.env gitignored), nunca commitada, nunca logada/printada. Mesmo padrao ja
  usado pro token da Deriv, documentado em docs/polymarket_dev_reference.md.
- POST /orders e POST /positions/{id}/claim NAO tem retry automatico aqui (diferente do _get
  herdado, que e so leitura) -- sao chamadas que MUTAM estado do lado da Jupiter; reexecutar
  cegamente apos timeout arrisca criar ordem duplicada. Se der timeout, checar
  GET /orders/status/{orderPubkey} (idempotente) antes de tentar de novo.
- RPC publico (default) tem rate-limit/confiabilidade limitados para uso serio -- SOLANA_RPC_URL
  deixa trocar por um dedicado (Helius/QuickNode/etc) quando for operar de verdade.

Contrato da API (developers.jup.ag/docs/guides/how-to-build-a-prediction-market-app-on-solana,
lido ao vivo em 2026-07-02, campos nao inventados):
  POST /orders body: {ownerPubkey, marketId, isYes, isBuy, depositAmount (string, micro-USD),
  depositMint (USDC ou JupUSD)}
  resposta (CreateOrderResponse): {transaction (base64 unsigned), txMeta: {blockhash,
  lastValidBlockHeight}, order: {orderPubkey, positionPubkey, contracts, orderCostUsd,
  estimatedTotalFeeUsd}}
  Assinatura (equivalente Python do exemplo oficial em JS -- VersionedTransaction.deserialize +
  .sign([wallet]) + connection.sendRawTransaction): deserializar com
  VersionedTransaction.from_bytes(base64.b64decode(...)), assinar a MESSAGE com
  keypair.sign_message(bytes(tx.message)), reconstruir com
  VersionedTransaction.populate(tx.message, [signature]), serializar de volta (base64) e
  submeter via sendTransaction (JSON-RPC) num RPC Solana.
"""
import asyncio
import base64
import json
import os
import urllib.error
import urllib.request
from typing import Optional

from dotenv import load_dotenv
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

from .base import ExecutionVenue
from .jupiter_prediction import BASE_URL, JupiterAPIError, JupiterAuthError, JupiterPredictionVenue
from .registry import register

USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
JUPUSD_MINT = "JuprjznTrTSp2UFa3ZBUFgwdAmtZCq4MQCwysN55USD"
_MINT_ALIASES = {"USDC": USDC_MINT, "JUPUSD": JUPUSD_MINT}
DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"


class SolanaSigningError(RuntimeError):
    """Chave ausente/invalida, ou falha ao assinar localmente -- nunca envolve rede."""
    pass


class SolanaRpcError(RuntimeError):
    """RPC Solana recusou/retornou erro pro sendTransaction ou getBalance/getTokenAccountsByOwner."""
    pass


def _resolve_mint(mint: str) -> str:
    return _MINT_ALIASES.get(mint.upper(), mint)


@register
class JupiterExecutionVenue(JupiterPredictionVenue, ExecutionVenue):
    name = "jupiter_execution"
    requires_credentials = True

    def __init__(
        self,
        api_key: Optional[str] = None,
        solana_private_key: Optional[str] = None,
        rpc_url: Optional[str] = None,
        poll_interval_s: float = 2.0,
    ):
        super().__init__(api_key=api_key, poll_interval_s=poll_interval_s)
        load_dotenv()
        secret = solana_private_key or os.getenv("SOLANA_PRIVATE_KEY")
        # os.getenv(..., DEFAULT_RPC_URL) NAO cai no default se a var existir vazia (ex.:
        # "SOLANA_RPC_URL=" no .env, copiado do .env.example) -- so cai se a var for ausente.
        # Encadear com `or` cobre os dois casos (ausente OU vazia).
        self.rpc_url = rpc_url or os.getenv("SOLANA_RPC_URL") or DEFAULT_RPC_URL
        self._keypair: Optional[Keypair] = None
        if secret:
            try:
                self._keypair = Keypair.from_base58_string(secret)
            except Exception as e:
                raise SolanaSigningError(
                    "SOLANA_PRIVATE_KEY invalida -- esperado base58 (formato 'Export Private "
                    f"Key' do Phantom): {e}"
                ) from e

    def is_authenticated(self) -> bool:
        return self._keypair is not None

    @property
    def pubkey(self) -> Optional[str]:
        return str(self._keypair.pubkey()) if self._keypair else None

    def _require_auth(self) -> None:
        if not self.is_authenticated():
            raise SolanaSigningError("SOLANA_PRIVATE_KEY nao configurada (.env) -- ver docstring do modulo")

    # ---------- Solana: assinatura local + RPC ----------

    def sign_transaction(self, tx_b64: str) -> str:
        """Deserializa a tx (base64) devolvida pela Jupiter, assina localmente com a chave da
        wallet e devolve a tx assinada, tambem em base64. NAO submete pra rede -- ver
        submit_transaction(). A chave privada nunca sai deste processo."""
        self._require_auth()
        raw = VersionedTransaction.from_bytes(base64.b64decode(tx_b64))
        signature = self._keypair.sign_message(bytes(raw.message))
        signed = VersionedTransaction.populate(raw.message, [signature])
        return base64.b64encode(bytes(signed)).decode("utf-8")

    def _rpc_call(self, payload: dict, timeout: int = 20) -> dict:
        req = urllib.request.Request(
            self.rpc_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        if "error" in data:
            raise SolanaRpcError(f"RPC {payload.get('method')} retornou erro: {data['error']}")
        return data

    def submit_transaction(self, signed_tx_b64: str, skip_preflight: bool = True, timeout: int = 20) -> str:
        """Transmite a tx JA ASSINADA pro RPC Solana (sendTransaction). A partir daqui o dinheiro
        se move de verdade -- so chamar com dry_run=False deliberado em buy()/claim_position(),
        ou diretamente se souber exatamente o que esta fazendo."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sendTransaction",
            "params": [signed_tx_b64, {"encoding": "base64", "skipPreflight": skip_preflight, "maxRetries": 3}],
        }
        data = self._rpc_call(payload, timeout=timeout)
        return data["result"]

    async def get_balance(self) -> dict:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._get_balance_sync)

    def _get_balance_sync(self) -> dict:
        self._require_auth()
        pk = self.pubkey
        sol = self._rpc_call({"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [pk]})
        usdc_resp = self._rpc_call(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [pk, {"mint": USDC_MINT}, {"encoding": "jsonParsed"}],
            }
        )
        usdc = 0.0
        for acc in usdc_resp.get("result", {}).get("value", []):
            amt = acc["account"]["data"]["parsed"]["info"]["tokenAmount"]
            usdc += float(amt.get("uiAmount") or 0)
        return {"pubkey": pk, "sol": sol["result"]["value"] / 1_000_000_000, "usdc": usdc}

    # ---------- Jupiter Prediction: /orders, /positions ----------

    def _post(self, path: str, body: dict, timeout: int = 15) -> dict:
        """POST sem retry automatico -- diferente do _get herdado (so leitura). Chamadas aqui
        MUTAM estado (criam ordem/claim de verdade do lado da Jupiter); reexecutar cegamente
        apos timeout arrisca duplicar. Ver docstring do modulo."""
        if not self.api_key:
            raise JupiterAuthError("JUPITER_API_KEY nao configurada")
        req = urllib.request.Request(
            f"{BASE_URL}{path}",
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "x-api-key": self.api_key,
                "User-Agent": "Mozilla/5.0 (compatible; hypothesis-research-bot/1.0)",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise JupiterAuthError(f"Jupiter API retornou {e.code} em POST {path}: {e.read().decode('utf-8', 'ignore')}") from e
        except (TimeoutError, urllib.error.URLError) as e:
            raise JupiterAPIError(
                f"Sem resposta em {timeout}s pra POST {path} -- NAO reexecutar automaticamente, "
                "checar GET /orders/status/{orderPubkey} primeiro (a ordem pode ja ter sido criada)"
            ) from e

    def _delete(self, path: str, timeout: int = 15) -> dict:
        if not self.api_key:
            raise JupiterAuthError("JUPITER_API_KEY nao configurada")
        req = urllib.request.Request(
            f"{BASE_URL}{path}",
            method="DELETE",
            headers={
                "x-api-key": self.api_key,
                "User-Agent": "Mozilla/5.0 (compatible; hypothesis-research-bot/1.0)",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise JupiterAuthError(f"Jupiter API retornou {e.code} em DELETE {path}: {e.read().decode('utf-8', 'ignore')}") from e

    def create_order(
        self, market_id: str, is_yes: bool, is_buy: bool, deposit_amount_usd: float, deposit_mint: str = "USDC"
    ) -> dict:
        """POST /orders -- cria a ordem do lado da Jupiter e devolve a tx nao assinada. Sozinho
        NAO move dinheiro (isso so acontece quando a tx assinada e submetida -- ver buy())."""
        self._require_auth()
        body = {
            "ownerPubkey": self.pubkey,
            "marketId": market_id,
            "isYes": is_yes,
            "isBuy": is_buy,
            "depositAmount": str(round(deposit_amount_usd * 1_000_000)),
            "depositMint": _resolve_mint(deposit_mint),
        }
        return self._post("/orders", body)

    def buy(
        self, market_id: str, is_yes: bool, deposit_amount_usd: float, deposit_mint: str = "USDC", dry_run: bool = True
    ) -> dict:
        """Fluxo completo: cria ordem -> assina localmente -> submete pra Solana SE dry_run=False.
        Default dry_run=True: cria a ordem e assina, mas NAO transmite (nenhum dinheiro se move).
        Passar dry_run=False e uma decisao explicita e deliberada de quem chama."""
        order_resp = self.create_order(market_id, is_yes, True, deposit_amount_usd, deposit_mint)
        signed_b64 = self.sign_transaction(order_resp["transaction"])
        result = {
            "order": order_resp["order"],
            "tx_meta": order_resp["txMeta"],
            "signed_tx_b64": signed_b64,
            "dry_run": dry_run,
            "submitted": False,
            "signature": None,
        }
        if not dry_run:
            result["signature"] = self.submit_transaction(signed_b64)
            result["submitted"] = True
        return result

    def get_order_status(self, order_pubkey: str) -> dict:
        """GET /orders/status/{orderPubkey} -- pending/filled/failed. Idempotente (so leitura) --
        usar pra checar antes de retentar um create_order() que deu timeout."""
        data = self._get(f"/orders/status/{order_pubkey}")
        return data.get("data", data) if isinstance(data, dict) else data

    def get_positions(self) -> list:
        self._require_auth()
        data = self._get("/positions", {"ownerPubkey": self.pubkey})
        return data.get("data", data) if isinstance(data, dict) else data

    def cancel_position(self, position_pubkey: str) -> dict:
        """DELETE /positions/{id} -- pra ordem que nao encheu (ver 'common questions' da doc oficial)."""
        return self._delete(f"/positions/{position_pubkey}")

    def claim_position(self, position_pubkey: str, dry_run: bool = True) -> dict:
        """POST /positions/{id}/claim -- resgata payout de posicao vencedora ja settled. Mesma
        logica de dry_run que buy(): default nao transmite pra Solana."""
        self._require_auth()
        resp = self._post(f"/positions/{position_pubkey}/claim", {"ownerPubkey": self.pubkey})
        signed_b64 = self.sign_transaction(resp["transaction"])
        result = {"signed_tx_b64": signed_b64, "dry_run": dry_run, "submitted": False, "signature": None}
        if not dry_run:
            result["signature"] = self.submit_transaction(signed_b64)
            result["submitted"] = True
        return result
