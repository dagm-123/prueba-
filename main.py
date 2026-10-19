import os
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from bot import run_batch_trade, load_wallets

app = FastAPI(title="Solana Multi-Wallet Sniper")
templates = Jinja2Templates(directory="templates")

class TradeRequest(BaseModel):
    token_mint: str
    amount_sol: float
    action: str  # "buy" o "sell"

@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    try:
        wallets = load_wallets()
        wallet_addresses = [str(w.pubkey()) for w in wallets]
    except Exception as e:
        wallet_addresses = []
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "wallets": wallet_addresses,
        "wallet_count": len(wallet_addresses)
    })

@app.post("/api/trade")
async def execute_trade(data: TradeRequest):
    if not data.token_mint or data.amount_sol <= 0:
        return {"status": "error", "message": "Datos inválidos"}
    
    results = await run_batch_trade(
        token_mint=data.token_mint.strip(),
        amount_sol=data.amount_sol,
        action=data.action.lower()
    )
    return {"status": "completed", "results": results}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)