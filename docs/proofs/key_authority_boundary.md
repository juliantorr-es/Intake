# Proof: Key Authority Boundary

This document tracks the progression of cryptographic authority from the current bootstrap state to the final production model.

## Current State: Symmetric Bootstrap (Dev)
- **Algorithm**: AES-256-GCM
- **Key Location**: `INTAKE_DEV_ENCRYPTION_KEY` is shared between Hosted and Local.
- **Authority**: Both Hosted and Local processes have technical authority to decrypt.
- **Boundary**: The boundary is currently **procedural and architectural**, not yet cryptographic.
  - Public APIs are redacted.
  - Sync APIs expose only ciphertext.
  - Local Console is the only *intended* surface for decryption.

## Scaffolding: Local Device Identity
To prepare for asymmetric authority, we are introducing the **Local Device** model.
- **Goal**: Establish a unique identity for each local machine running the Intake Console.
  - `public_signing_key`: Ed25519 public key for action verification.
  - `public_encryption_key`: Placeholder for X25519/similar key.
- **Authority**: 
  - **Signing**: Local Console holds the **Private Signing Key**. Only it can generate valid action envelopes.
  - **Verification**: Hosted backend holds the **Public Signing Key**. It can verify intent but cannot forge actions.
- **Verification**: `tests/test_signed_actions.py` proves that tampered actions or wrong keys are rejected.

## Target State: Asymmetric Isolation (Production)
- **Algorithm**: ECIES (Elliptic Curve Integrated Encryption Scheme) or similar.
- **Key Separation**:
  - **Hosted**: Stores the Local Device **Public Key**. Encrypts client data to this key.
  - **Local**: Generates and stores the **Private Key** in secure local storage. Never uploads it.
- **Authority**: Only the Local Console has the cryptographic capability to decrypt client data.
- **Untrusted Hosted**: Even with full database and process access, an attacker on the hosted backend cannot read sensitive client data.
