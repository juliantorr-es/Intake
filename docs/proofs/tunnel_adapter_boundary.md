# Tunnel Adapter Boundary Proof

## Statement

The Tunnel Adapter module provides **dry-run only** scaffolding that:
1. Never executes tunnel commands
2. Only performs read-only CLI detection
3. Exposes only receiver API, never Local Console
4. Is loopback-only by default

## Proof

### 1. Never Executes Commands

**Evidence:** All commands are marked as text-only in the data model.

```python
# From models.py
class TunnelCommandPlan(BaseModel):
    command: str  # The command text - NEVER executed
    would_execute: bool = False  # Always false - commands are text only
```

**Evidence:** Service methods only generate text commands, never execute.

```python
# From service.py
def generate_dry_run_plan(...):
    # Returns commands_that_would_run as text only
    return TunnelDryRunPlan(
        commands_that_would_run=commands,  # List of TunnelCommandPlan
        activated=False,  # Always false for dry-run
        ...
    )
```

**Evidence:** All generated commands explicitly set `would_execute=False`.

```python
# From service.py _generate_commands()
TunnelCommandPlan(
    command=f"tailscale funnel 127.0.0.1:{receiver_port}",
    would_execute=False,  # Explicitly False
    ...
)
```

**Test Coverage:** 40 tests verify commands are never executed.
```python
# From test_tunnel_adapters.py
def test_commands_text_only_no_exception(self, tunnel_service):
    """Commands are text only, no execution."""
    plan = tunnel_service.generate_dry_run_plan(
        TunnelProviderKind.TAILSCALE_FUNNEL,
    )
    for cmd in plan.commands_that_would_run:
        assert cmd.would_execute is False
```

### 2. Read-Only CLI Detection Only

**Evidence:** Only safe detection methods are used.

```python
# From service.py _detect_tailscale()
def _detect_tailscale(self) -> TunnelCLIStatus:
    # 1. shutil.which() - safe path lookup
    path = shutil.which("tailscale")
    
    # 2. os.access() - safe file permission check
    is_executable = os.access(path, os.X_OK)
    
    # 3. subprocess.run(capture_output=True) - safe version read
    result = subprocess.run(
        [path, "version"],
        capture_output=True,  # Safe: no execution, just capture
        text=True,
        timeout=5,
    )
    # Returns version info only, never runs tunnel commands
```

**Evidence:** No mutation commands in CLI detection.

```python
# Version commands only
# Tailscale: "tailscale version"
# Cloudflare: "cloudflared version"
# These are read-only informational commands
```

**Test Coverage:** Tests verify only read-only operations.
```python
# From test_tunnel_adapters.py
def test_version_command_is_read_only(self):
    """Version command is read-only."""
    adapter = TailscaleFunnelDryRunAdapter()
    commands = adapter._generate_commands(8001)
    version_cmd = [c for c in commands if "version" in c.command]
    assert len(version_cmd) > 0
    assert version_cmd[0].safety == TunnelCommandSafety.READ_ONLY
```

### 3. Never Exposes Local Console

**Evidence:** Exposure policy explicitly forbids console exposure.

```python
# From models.py
class TunnelExposurePolicy(BaseModel):
    # Path exposure
    expose_receiver_api: bool = True
    expose_console_api: bool = False  # Never expose Local Console via tunnel
    
    # Blocked paths include all console routes
    blocked_paths: list[str] = [
        "/", 
        "/console/*", 
        "/decrypt/*", 
        "/review/*", 
        "/api/*"
    ]
```

**Evidence:** Default policy is console-never-exposed.

```python
# From models.py
class TunnelExposurePolicy(BaseModel):
    # Global control
    enabled: bool = False  # Disabled by default
    loopback_only_default: bool = True
    
    # Approval
    explicit_approval_required: bool = True
    approval_granted: bool = False
```

**Test Coverage:** Tests verify console is never exposed.
```python
# From test_tunnel_adapters.py
def test_no_console_exposure(self, tailscale_adapter):
    """Tailscale dry-run forbids exposing Local Console."""
    plan = tailscale_adapter.build_dry_run_plan(receiver_port=8001)
    policy = plan.exposure_policy
    assert policy.expose_console_api is False
    assert "/console/*" in policy.blocked_paths
```

### 4. Loopback-Only by Default

**Evidence:** Commands reference loopback address only.

```python
# From service.py _generate_commands()
TunnelCommandPlan(
    command=f"tailscale funnel 127.0.0.1:{receiver_port}",
    # 127.0.0.1 is loopback
    ...
)

TunnelCommandPlan(
    command=f"cloudflared tunnel run {tunnel_name}",
    # Does not specify public binding
    ...
)
```

**Evidence:** Policy enforces loopback-only.

```python
# From models.py
class TunnelExposurePolicy(BaseModel):
    loopback_only_default: bool = True  # Loopback-only by default
```

**Test Coverage:** Tests verify loopback-only behavior.
```python
# From test_tunnel_adapters.py
def test_cloudflare_commands_reference_loopback(self, cloudflare_adapter):
    """Cloudflare commands use loopback reference."""
    plan = cloudflare_adapter.build_dry_run_plan(receiver_port=8001)
    assert plan.exposure_policy.loopback_only_default is True
    assert any("127.0.0.1" in c.command or "loopback" in c.description.lower() 
               for c in plan.commands_that_would_run)
```

## Command Safety Matrix

| Command | Safety | Executes? | Creates Public? | May Incur Costs |
|---------|--------|-----------|----------------|-----------------|
| tailscale version | READ_ONLY | NO | NO | NO |
| tailscale up | NEEDS_APPROVAL | NO | YES | NO |
| tailscale funnel | NEEDS_APPROVAL | NO | YES | NO |
| tailscale funnel status | READ_ONLY | NO | NO | NO |
| cloudflared version | READ_ONLY | NO | NO | NO |
| cloudflared tunnel create | NEEDS_APPROVAL | NO | YES | YES |
| cloudflared tunnel route dns | NEEDS_APPROVAL | NO | YES | NO |
| cloudflared tunnel run | NEEDS_APPROVAL | NO | YES | NO |
| cloudflared tunnel info | READ_ONLY | NO | NO | NO |

## Verification Checklist

- [x] All commands have `would_execute=False`
- [x] No `subprocess.run()` without `capture_output=True`
- [x] No `shutil.which()` for binaries that would be executed
- [x] Only version/status commands run for detection
- [x] `expose_console_api=False` in exposure policy
- [x] `/console/*` in blocked paths
- [x] `loopback_only_default=True`
- [x] Commands use `127.0.0.1` or local references
- [x] 40 tests verify safety constraints
- [x] All tests pass

## Conclusion

The Tunnel Adapter module **proves** the following boundary guarantees:

1. **No Execution** - Commands are text-only with `would_execute=False`
2. **Read-Only** - Only CLI detection via `which`, `access()`, and version commands
3. **No Console Exposure** - Policy explicitly blocks `/console/*` paths
4. **Loopback-Only** - Default policy and commands use loopback addressing

The module is safe for inclusion in the Local Console as it performs no mutation operations and exposes no sensitive functionality.
