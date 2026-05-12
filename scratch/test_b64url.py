from webauthn.helpers import bytes_to_base64url, base64url_to_bytes
import base64

data = b"hello world"
b64url = bytes_to_base64url(data)
print(f"data: {data}")
print(f"bytes_to_base64url: '{b64url}'")

# Standard base64url with padding
std_b64url = base64.urlsafe_b64encode(data).decode()
print(f"standard urlsafe_b64encode: '{std_b64url}'")

# Check if they match
if b64url == std_b64url.rstrip('='):
    print("bytes_to_base64url matches standard without padding.")
else:
    print("bytes_to_base64url does NOT match standard without padding.")
