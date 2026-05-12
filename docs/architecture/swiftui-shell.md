# SwiftUI macOS Shell Architecture

The Intake Console macOS shell is a thin SwiftUI wrapper around the existing Python-based Local Console. It provides a native macOS experience while leveraging the stability and features of the Python backend.

## Core Components

- **IntakeConsoleApp**: The entry point of the macOS application.
- **ContentView**: Manages the high-level UI states (loading, online, error) and hosts the web view.
- **LocalConsoleWebView**: A `WKWebView` wrapper that renders the local console UI.
- **BackendHealthClient**: Continuously monitors the health of the local FastAPI backend.
- **BackendLauncher**: Handles the lifecycle of the Python backend (currently supports development mode).

## Security Boundaries

- **Loopback Only**: The `LocalConsoleWebView` is strictly restricted to `127.0.0.1` and `localhost`. Any attempt to navigate to external URLs is blocked.
- **No Native Bridge**: The shell does not expose a broad native bridge to the web content, minimizing the attack surface.
- **Isolated Processes**: The Python backend and SwiftUI shell run in separate processes.

## Development Mode

In development mode, the shell assumes the Python backend is already running (e.g., via `scripts/dev.sh` or `python -m intake.local_console.app`).

To run the shell against the local backend:
1. Start the backend: `INTAKE_LOCAL_PORT=8000 python -m intake.local_console.app` (or use a dedicated script).
2. Run the shell: `swift run` from `apps/IntakeMac/IntakeConsole`.

The SwiftUI shell currently defaults to `http://127.0.0.1:8000`.

## Next Steps

- Implement "Managed Mode" in `BackendLauncher` to automatically start/stop the Python backend with the app.
- Add native log viewing and settings management.
- Improve the visual integration between SwiftUI and the web UI.
