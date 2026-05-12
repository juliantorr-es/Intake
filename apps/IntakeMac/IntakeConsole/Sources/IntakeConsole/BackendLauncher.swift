import Foundation
import Combine
import CryptoKit

@MainActor
class BackendLauncher: ObservableObject {
    @Published var isLaunching = false
    @Published var launchError: String?
    @Published var isRunning = false
    
    enum LaunchMode {
        case development // Backend started manually via scripts/dev.sh or python -m ...
        case managed     // App launches the backend itself
    }
    
    private let mode: LaunchMode
    nonisolated(unsafe) private var process: Process?
    private var cancellables = Set<AnyCancellable>()
    
    init(mode: LaunchMode = .development) {
        self.mode = mode
    }
    
    func ensureBackendRunning() {
        switch mode {
        case .development:
            // In dev mode, we just wait for the health check to pass
            print("BackendLauncher: Running in development mode. Assuming backend is started externally.")
        case .managed:
            launchManagedBackend()
        }
    }
    
    private func launchManagedBackend() {
        guard !isLaunching && !isRunning else { return }
        
        isLaunching = true
        launchError = nil
        
        // Find the project root by walking up from current directory
        let fileManager = FileManager.default
        var searchPath = URL(fileURLWithPath: fileManager.currentDirectoryPath)
        var projectRoot = searchPath.path
        
        // Walk up until we find 'src/intake'
        while searchPath.path != "/" {
            let srcIntakePath = searchPath.appendingPathComponent("src/intake").path
            var isDir: ObjCBool = false
            if fileManager.fileExists(atPath: srcIntakePath, isDirectory: &isDir), isDir.boolValue {
                projectRoot = searchPath.path
                break
            }
            searchPath = searchPath.deletingLastPathComponent()
        }
        
        let pythonPath = "\(projectRoot)/src"
        
        print("BackendLauncher: Current Directory: \(fileManager.currentDirectoryPath)")
        print("BackendLauncher: Project Root: \(projectRoot)")
        print("BackendLauncher: PYTHONPATH: \(pythonPath)")
        
        let process = Process()
        // Try to use homebrew python 3.13 as fallback, but prefer 'python3' if it exists in path
        // For managed mode in dev, we often need a specific path if PATH isn't inherited cleanly
        process.executableURL = URL(fileURLWithPath: "/opt/homebrew/opt/python@3.13/bin/python3.13")
        process.arguments = ["-m", "intake.local_console.app"]
        
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = pythonPath
        env["INTAKE_HEADLESS"] = "1"
        env["INTAKE_LOCAL_PORT"] = "8000"
        
        // Generate a native capability token for secure unlock proof
        // This binds the Swift native shell to the backend process
        let capabilityToken = generateNativeCapabilityToken()
        env["INTAKE_NATIVE_UNLOCK_CAPABILITY"] = capabilityToken
        
        // Store the capability for use by SecureUnlockService
        SecureUnlockService.shared.setNativeCapability(capabilityToken)
        
        process.environment = env
        
        process.currentDirectoryURL = URL(fileURLWithPath: projectRoot)
        
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        
        do {
            try process.run()
            self.process = process
            print("BackendLauncher: Started managed backend process (PID: \(process.processIdentifier))")
            
            // Watch for termination
            process.terminationHandler = { [weak self] proc in
                Task { @MainActor in
                    self?.isRunning = false
                    self?.isLaunching = false
                    if proc.terminationStatus != 0 {
                        self?.launchError = "Backend exited with status \(proc.terminationStatus)"
                    }
                }
            }
            
            // We consider it "running" once the process starts, 
            // though health client will confirm connectivity.
            self.isRunning = true
            self.isLaunching = false
            
            // Read output to diagnose issues
            let outHandle = pipe.fileHandleForReading
            outHandle.readabilityHandler = { handle in
                let data = handle.availableData
                guard !data.isEmpty else { return }
                if let line = String(data: data, encoding: .utf8) {
                    // Task used to ensure thread safety for print if needed, 
                    // though print is thread-safe. Primarily to keep patterns consistent.
                    print("Backend >>> \(line)", terminator: "")
                }
            }
            
        } catch {
            isLaunching = false
            launchError = "Failed to launch backend: \(error.localizedDescription)"
            print("BackendLauncher Error: \(launchError!)")
        }
    }
    
    func stopBackend() {
        if let process = process, process.isRunning {
            process.terminate()
            print("BackendLauncher: Terminated backend process.")
        }
        process = nil
        isRunning = false
    }
    
    deinit {
        let p = process
        Task { @MainActor in
            if let process = p, process.isRunning {
                process.terminate()
                print("BackendLauncher: Terminated backend process (from deinit).")
            }
        }
    }
}

// MARK: - Native Capability Token Generation

private func generateNativeCapabilityToken() -> String {
    /// Generate a cryptographically strong random token for native capability proof.
    /// This token is unique per-process and binds the Swift shell to the backend.
    /// Uses CryptoKit for secure random generation.
    var bytes = [UInt8](repeating: 0, count: 32)
    _ = SecRandomCopyBytes(kSecRandomDefault, 32, &bytes)
    return bytes.map { String(format: "%02x", $0) }.joined()
}
