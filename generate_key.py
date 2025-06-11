from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pathlib import Path

# 1. Adjust this to your Django project root if needed:
BASE_DIR = Path(__file__).resolve().parent.parent  # or Path('D:/Sakarela_DJANGO')
KEY_DIR = BASE_DIR / 'mypos'
KEY_DIR.mkdir(exist_ok=True)

# 2. Generate a new RSA private key:
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048
)

# 3. Serialize it as a PEM (PKCS#8, unencrypted):
pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)

# 4. Write it out:
private_key_path = KEY_DIR / 'private_key.pem'
with open(private_key_path, 'wb') as f:
    f.write(pem)

print("Key written to:", private_key_path)