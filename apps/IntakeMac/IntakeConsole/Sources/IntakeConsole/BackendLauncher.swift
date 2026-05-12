import Foundation

class BackendLauncher: ObservableObject {
    @Published var isLaunching = false
    @Published var launchError: String?
    
    enum LaunchMode {
        case development // Backend started manually via scripts/dev.sh or python -m ...
        case managed     // App launches the backend itself
    }
    
    private let mode: LaunchMode
    
    init(mode: LaunchMode = .development) {
        self.mode = mode
    }
    
    func ensureBackendRunning() {
        switch mode {
        case .development:
            // In dev mode, we just wait for the health check to pass
            print("BackendLauncher: Running in development mode. Assuming backend is started externally.")
        case .managed:
            // TODO: Implement managed launch (python -m intake.local_console.app)
            print("BackendLauncher: Managed mode not yet implemented.")
            launchError = "Managed launch not yet implemented."
        }
    }
}
