from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pathlib import Path
import os

# 1. Get the absolute path of the current script
BASE_DIR = Path(__file__).resolve().parent
KEY_DIR = BASE_DIR / 'mypos'

# Create the mypos directory if it doesn't exist
KEY_DIR.mkdir(exist_ok=True)

# 2. Generate a new RSA private key:
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048
)

# 3. Serialize it as a PEM in PKCS#1 format (traditional format):
pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,  # This is PKCS#1
    encryption_algorithm=serialization.NoEncryption()
)

# 4. Write it out:
private_key_path = KEY_DIR / 'private_key.pem'
with open(private_key_path, 'wb') as f:
    f.write(pem)

print("Key written to:", private_key_path)
print("Key format: PKCS#1 (Traditional OpenSSL)")
print("Key contents:")
print(pem.decode('utf-8')[:100] + "...")