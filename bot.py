import os
import json
import asyncio
import httpx
from dotenv import load_dotenv

from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

load_dotenv()

RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com").strip()
PUMPPORTAL_API = "https://pumpportal.fun/api/trade-local"

SIMULATION_MODE = False  # Modo real activado

def load_wallets():
    if not os.path.exists("wallets.json"):
        raise FileNotFoundError("El archivo wallets.json no existe.")
    with open("wallets.json", "r") as f:
        data = json.load(f)
        keys = data.get("private_keys", [])
        if not keys:
            raise ValueError("No hay claves privadas en wallets.json")
        return [Keypair.from_base58_string(k) for k in keys]

async def execute_pump_trade_single_wallet(keypair: Keypair, token_mint: str, amount_sol: float, action: str, client: AsyncClient):
    wallet_address = str(keypair.pubkey())
    
    if SIMULATION_MODE:
        await asyncio.sleep(0.1)
        return {
            "wallet": wallet_address[:6] + "..." + wallet_address[-4:],
            "status": "SUCCESS",
            "tx": "SIMULATED_TX_PUMP_FUN"
        }

    try:
        # Configuración de parámetros según compra o venta
        amount_param = "100%" if action == "sell" else amount_sol
        denominated_in_sol = "false" if action == "sell" else "true"

        payload = {
            "publicKey": wallet_address,
            "action": action,                           # "buy" o "sell"
            "mint": token_mint.strip(),                 # Contrato del token
            "denominatedInSol": denominated_in_sol,     # "true" para SOL, "false" para tokens
            "amount": amount_param,                     # Monto o 100%
            "slippage": 25,                             # 25% de tolerancia
            "priorityFee": 0.001,                       # Propina de prioridad alta
            "pool": "pump"
        }

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as http_client:
            response = await http_client.post(PUMPPORTAL_API, json=payload)
            
            if response.status_code != 200:
                raise Exception(f"PumpPortal Error [{response.status_code}]: {response.text}")
            
            raw_tx_bytes = response.content

        # 1. Deserializar la transacción limpia que entrega PumpPortal
        vtx = VersionedTransaction.from_bytes(raw_tx_bytes)

        # 2. Firmar el mensaje de forma nativa con solders
        message_bytes = bytes(vtx.message)
        signature = keypair.sign_message(message_bytes)
        signed_tx = VersionedTransaction.populate(vtx.message, [signature])
        signed_tx_bytes = bytes(signed_tx)

        # 3. Enviar al RPC de Solana (skip_preflight=True para evitar bloqueos innecesarios)
        opts = TxOpts(skip_preflight=True, max_retries=5)
        response_rpc = await client.send_raw_transaction(signed_tx_bytes, opts=opts)
        
        # Extraer el hash de la transacción
        tx_hash_str = str(response_rpc.value)

        return {
            "wallet": wallet_address[:6] + "..." + wallet_address[-4:],
            "status": "SUCCESS",
            "tx": tx_hash_str
        }
    except Exception as e:
        return {
            "wallet": wallet_address[:6] + "..." + wallet_address[-4:],
            "status": "FAILED",
            "error": str(e)
        }

async def run_batch_trade(token_mint: str, amount_sol: float, action: str):
    keypairs = load_wallets()
    async_client = AsyncClient(RPC_URL)
    
    tasks = [
        execute_pump_trade_single_wallet(kp, token_mint, amount_sol, action, async_client)
        for kp in keypairs
    ]
    
    results = await asyncio.gather(*tasks)
    await async_client.close()
    return results