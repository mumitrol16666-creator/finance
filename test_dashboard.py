import asyncio
import aiosqlite
import os

os.environ["DB_PATH"] = r"c:\FinanceBot\data\bot.db"

from fastapi.testclient import TestClient
from app.api.api_server import app, generate_token

client = TestClient(app)

def test_dash():
    token = generate_token(938030819)
    print("TOKEN:", token)
    
    resp = client.get("/api/dashboard", headers={"Authorization": f"Bearer {token}"})
    print("STATUS:", resp.status_code)
    if resp.status_code != 200:
        print("ERROR:", resp.text)
    else:
        print("SUCCESS! Output length:", len(resp.text))
        
test_dash()
