from webauthn import base64url_to_bytes
import base64

data = b"hello world"
b64url = base64.urlsafe_b64encode(data).decode().rstrip('=')
print(f"unpadded b64url: '{b64url}'")

try:
    decoded = base64url_to_bytes(b64url)
    print(f"base64url_to_bytes decoded: {decoded}")
except Exception as e:
    print(f"base64url_to_bytes failed: {e}")
