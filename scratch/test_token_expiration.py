import time
import os
import sys

# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.api_server import generate_token, verify_token, SECRET_KEY
import hmac
import hashlib

def test_tokens():
    print(f"Testing with SECRET_KEY: {SECRET_KEY}")

    # 1. Test generate_token
    user_id = 999111
    token = generate_token(user_id)
    print(f"Generated token: {token}")

    # 2. Test verification of new token
    verified_id = verify_token(token)
    assert verified_id == user_id, f"Failed to verify new token! Expected {user_id}, got {verified_id}"
    print("New token format verification: SUCCESS")

    # 3. Test compatibility with old token format
    # Old format: user_id.sig
    old_msg = str(user_id).encode()
    old_sig = hmac.new(SECRET_KEY, old_msg, hashlib.sha256).hexdigest()
    old_token = f"{user_id}.{old_sig}"
    
    verified_old_id = verify_token(old_token)
    assert verified_old_id == user_id, f"Failed to verify old token format! Expected {user_id}, got {verified_old_id}"
    print("Old token format (backwards compatibility) verification: SUCCESS")

    # 4. Test expired token
    # Create a token with exp_timestamp in the past
    past_exp = int(time.time()) - 100
    past_msg = f"{user_id}.{past_exp}".encode()
    past_sig = hmac.new(SECRET_KEY, past_msg, hashlib.sha256).hexdigest()
    expired_token = f"{user_id}.{past_exp}.{past_sig}"

    verified_expired_id = verify_token(expired_token)
    assert verified_expired_id is None, f"Expired token verification did not return None! Got {verified_expired_id}"
    print("Expired token rejection: SUCCESS")

    # 5. Test invalid token
    invalid_token = token + "modified"
    verified_invalid_id = verify_token(invalid_token)
    assert verified_invalid_id is None, f"Invalid signature token verification did not return None! Got {verified_invalid_id}"
    print("Invalid signature rejection: SUCCESS")

if __name__ == "__main__":
    test_tokens()
