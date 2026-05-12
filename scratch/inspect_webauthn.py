import webauthn.helpers.structs as structs
from webauthn.helpers.structs import VerifiedRegistrationResponse, VerifiedAuthenticationResponse
import dataclasses

print("VerifiedRegistrationResponse fields:")
for field in dataclasses.fields(VerifiedRegistrationResponse):
    print(f"- {field.name}: {field.type}")

print("\nVerifiedAuthenticationResponse fields:")
for field in dataclasses.fields(VerifiedAuthenticationResponse):
    print(f"- {field.name}: {field.type}")
