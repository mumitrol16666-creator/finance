import asyncio
import os
os.environ["DB_PATH"] = r"c:\FinanceBot\data\bot.db"
from fastapi.testclient import TestClient
from app.api.api_server import app, generate_token

client = TestClient(app)

def test_req():
    token = generate_token(938030819)
    resp = client.get("/api/planned", headers={"Authorization": f"Bearer {token}"})
    print("PLANNED:", resp.text[:1000])

test_req()
