from webauthn.registration.verify_registration_response import VerifiedRegistration
from webauthn.authentication.verify_authentication_response import VerifiedAuthentication
import dataclasses

print("VerifiedRegistration fields:")
for f in dataclasses.fields(VerifiedRegistration):
    print(f"- {f.name}")

print("\nVerifiedAuthentication fields:")
for f in dataclasses.fields(VerifiedAuthentication):
    print(f"- {f.name}")
