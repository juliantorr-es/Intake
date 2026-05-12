import webauthn
import inspect

print("webauthn version:", webauthn.__version__ if hasattr(webauthn, "__version__") else "unknown")

# Try to find the return type of verify_registration_response
from webauthn import verify_registration_response, verify_authentication_response

print("\nverify_registration_response return type signature:")
print(inspect.signature(verify_registration_response).return_annotation)

print("\nverify_authentication_response return type signature:")
print(inspect.signature(verify_authentication_response).return_annotation)

# Let's actually call them with dummy data to see what they return? 
# No, easier to just check the module.

from webauthn.helpers.structs import VerifiedRegistrationResponse, VerifiedAuthenticationResponse
import dataclasses

print("\nVerifiedRegistrationResponse fields:")
for f in dataclasses.fields(VerifiedRegistrationResponse):
    print(f"- {f.name}")

print("\nVerifiedAuthenticationResponse fields:")
for f in dataclasses.fields(VerifiedAuthenticationResponse):
    print(f"- {f.name}")
