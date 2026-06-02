import hmac
import hashlib
import urllib.request
import urllib.error
import json

SECRET_KEY = b"finance_bot_secret_key_123!"

def generate_token(user_id: int) -> str:
    msg = str(user_id).encode()
    sig = hmac.new(SECRET_KEY, msg, hashlib.sha256).hexdigest()
    return f"{user_id}.{sig}"

def test_endpoint(token, path, method="GET", body=None):
    url = f"http://127.0.0.1:8000{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
        except Exception:
            err_body = e.reason
        return e.code, err_body
    except Exception as e:
        return 999, str(e)

def run():
    newbie_id = 1917163976
    premium_id = 6856090314
    
    newbie_token = generate_token(newbie_id)
    premium_token = generate_token(premium_id)
    
    endpoints = [
        ("/api/debts", "GET", None),
        ("/api/recurring", "GET", None),
        ("/api/planned", "GET", None),
        ("/api/chat", "POST", {"text": "привет"}),
    ]
    
    print("=== Testing FREE NEWBIE User (should return 403 Forbidden) ===")
    for path, method, body in endpoints:
        status, response = test_endpoint(newbie_token, path, method, body)
        print(f"{method} {path} -> Status: {status} | Response: {response}")
        
    print("\n=== Testing PREMIUM User (should return 200 OK or non-403) ===")
    for path, method, body in endpoints:
        status, response = test_endpoint(premium_token, path, method, body)
        print(f"{method} {path} -> Status: {status} | Response: {response}")

if __name__ == "__main__":
    run()
