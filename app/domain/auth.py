import hashlib
import secrets

def hash_password(password: str) -> str:
    """
    Hash password using PBKDF2 with SHA-256.
    Returns format: pbkdf2_sha256$iterations$salt$hash
    """
    salt = secrets.token_hex(16)
    iterations = 100000
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        iterations
    )
    return f"pbkdf2_sha256${iterations}${salt}${key.hex()}"

def verify_password(password: str, hashed: str) -> bool:
    """
    Verify password against PBKDF2 SHA-256 hash.
    """
    try:
        parts = hashed.split('$')
        if len(parts) != 4 or parts[0] != 'pbkdf2_sha256':
            return False
        iterations = int(parts[1])
        salt = parts[2]
        expected_hex = parts[3]
        
        key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            iterations
        )
        return secrets.compare_digest(key.hex(), expected_hex)
    except Exception:
        return False
