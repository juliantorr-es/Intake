# Proof: SwiftUI Shell Boundary

This document verifies the security boundaries and functional scope of the SwiftUI macOS shell.

## Security Boundary Verification

### 1. Loopback-Only Navigation
The `LocalConsoleWebView` implementation includes a `WKNavigationDelegate` that enforces a strict host check:

```swift
func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
    guard let url = navigationAction.request.url else {
        decisionHandler(.cancel)
        return
    }
    
    let host = url.host ?? ""
    if host == "127.0.0.1" || host == "localhost" {
        decisionHandler(.allow)
    } else {
        decisionHandler(.cancel)
    }
}
```

**Verification State**:
- [x] Internal links within `127.0.0.1` are allowed.
- [x] External links (e.g., `google.com`) are blocked.
- [x] Redirects to external sites are blocked.

### 2. No Native Bridge
The shell does not inject any `WKUserScript` or register any `WKScriptMessageHandler` that would expose native capabilities to the web content.

**Verification State**:
- [x] No `addScriptMessageHandler` calls found in `LocalConsoleWebView`.

### 3. Loopback-Only Backend
The backend is configured to bind to `127.0.0.1` by default, ensuring it is not accessible from the network.

**Verification State**:
- [x] `uvicorn.run(app, host="127.0.0.1", ...)` confirmed in `src/intake/local_console/app.py`.

## Functional Scope Verification

### 1. Backend Health Monitoring
The `BackendHealthClient` uses a periodic timer to poll `/api/local/health`.

**Verification State**:
- [x] `online` status shown when backend is running.
- [x] `offline` status shown when backend is stopped.

### 2. Toolbar Actions
The toolbar provides a native feel with essential actions.

**Verification State**:
- [x] Reload button triggers `webView.reload()`.
- [x] Branding and status indicators are present.

## Known Gaps
- Managed backend launch is not yet implemented (shell assumes backend is pre-started).
- Log viewing is currently a placeholder.
- Settings are currently a placeholder.
