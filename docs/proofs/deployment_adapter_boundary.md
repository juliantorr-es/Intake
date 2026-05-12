# Deployment Adapter Boundary

## Architecture
The deployment adapter boundary defines the separation between the local Intake console and cloud provider deployment environments. This ensures that we have a structured, provider-agnostic way to deploy the Hosted Intake service.

## Proofs
- **Provider Interface:** `BaseDeploymentAdapter` provides an abstract interface requiring `plan_deployment` and `verify_readiness`.
- **Artifact Generation:** Providers generate specific artifacts (e.g., `railway.json` for Railway) into a safe `.build/intake/deploy/` directory.
- **Security Boundaries:**
  - Local private keys are strictly forbidden from being generated into `.env.hosted.example` or any deployment plan artifacts.
  - Secret values are redacted (`REDACTED`) in example files.
  - The start command is adaptable and utilizes provider port injection (e.g., `${PORT:-8000}`).
- **First-class Target:** Railway is explicitly implemented as the initial deployment scaffolding provider.
