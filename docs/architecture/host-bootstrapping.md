# Host Bootstrapping

Host bootstrapping is the process of provisioning, configuring, deploying, verifying, and registering a Hosted Intake backend on common webhosts using the Local Console.

## Product Doctrine

- **Guided Deployment:** Host bootstrapping is guided deployment, not magic cloud control.
- **Provider Adapters:** Railway is the first-class target. The system uses a provider adapter architecture to support other hosts (e.g., Render, Fly.io) in the future.
- **Data Locality:** Provider tokens and secrets stay local. Local private keys (e.g., local private decrypt keys, local private signing keys) are **never** deployed to the hosted backend.
- **Safe Artifacts:** Generated artifacts are safe to inspect and are output to a safe build directory (e.g., `.build/intake/deploy/railway/...`).
- **Deployment Receipts:** Deployment receipts act as evidence, not secrets.

## Key Authority separation

If the current dev encryption key is still required by hosted runtime, it is strictly documented as a bootstrap-only and risky operation. We do not claim production local-only decrypt authority until public-key/envelope encryption removes the hosted decrypt capability.
