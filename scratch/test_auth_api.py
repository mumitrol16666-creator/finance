import asyncio
import os
import sys
from fastapi.testclient import TestClient

os.environ["DB_PATH"] = r"c:\FinanceBot\data\bot.db"

# Add parent directory to path so we can import app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api.api_server import app

client = TestClient(app)

def test_check_username():
    print("Testing GET /api/auth/check-username...")
    # user_823811332 exists in database
    resp = client.get("/api/auth/check-username?username=user_823811332")
    print("Existing username availability status:", resp.status_code, resp.json())
    assert resp.status_code == 200
    assert resp.json()["available"] is False

    resp = client.get("/api/auth/check-username?username=completely_new_username_12345")
    print("New username availability status:", resp.status_code, resp.json())
    assert resp.status_code == 200
    assert resp.json()["available"] is True

def test_login_legacy_placeholder():
    print("\nTesting login for a legacy user (must be blocked)...")
    # user_823811332 has LEGACY_PLACEHOLDER password hash
    payload = {
        "username": "user_823811332",
        "password": "anypassword"
    }
    resp = client.post("/api/auth/login", json=payload)
    print("Login response status:", resp.status_code)
    print("Login response json:", resp.json())
    assert resp.status_code == 400
    assert "Для входа в приложение установите пароль внутри Telegram-бота" in resp.json()["detail"]

def test_register_and_login_new_user():
    print("\nTesting new user registration and subsequent login...")
    username = "test_api_user_new"
    
    # 1. Register
    payload_reg = {
        "display_name": "API Tester",
        "username": username,
        "password": "securepassword123",
        "confirm_password": "securepassword123"
    }
    resp_reg = client.post("/api/auth/register", json=payload_reg)
    print("Register response status:", resp_reg.status_code)
    print("Register response json:", resp_reg.json())
    assert resp_reg.status_code == 200
    assert "token" in resp_reg.json()

    # 2. Login
    payload_login = {
        "username": username,
        "password": "securepassword123"
    }
    resp_login = client.post("/api/auth/login", json=payload_login)
    print("Login response status:", resp_login.status_code)
    print("Login response json:", resp_login.json())
    assert resp_login.status_code == 200
    assert "token" in resp_login.json()

    # 3. Login with wrong password
    payload_login_wrong = {
        "username": username,
        "password": "wrongpassword"
    }
    resp_login_wrong = client.post("/api/auth/login", json=payload_login_wrong)
    print("Login wrong pass response status:", resp_login_wrong.status_code)
    print("Login wrong pass response json:", resp_login_wrong.json())
    assert resp_login_wrong.status_code == 401

if __name__ == '__main__':
    test_check_username()
    test_login_legacy_placeholder()
    test_register_and_login_new_user()
    print("\nAll auth API tests passed successfully!")
