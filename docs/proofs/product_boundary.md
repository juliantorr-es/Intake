# Proof: Product Boundary Enforcement

This document verifies the structural isolation between the Hosted and Local modules.

## Module Isolation
The project structure enforces a clear separation:
- `src/intake/hosted/`: Publicly accessible logic.
- `src/intake/local_console/`: Private operator logic.
- `src/intake/sync/`: Shared protocol models.

## Automated Boundary Tests
Tests in `tests/test_module_boundaries.py` use structural analysis to ensure:
- `hosted` modules do NOT import from `local_console`.
- `local_console` modules do NOT import hosted API routers directly.
- The `Sync Protocol` models are the only bridge for data exchange.

## Redaction Proof
The `HostedQuoteProjection` model in `src/intake/sync/models.py` uses `extra = "forbid"` and explicit field inclusion to ensure that even if a full `Quote` object is passed to it, only non-sensitive metadata is serialized for the sync protocol.
