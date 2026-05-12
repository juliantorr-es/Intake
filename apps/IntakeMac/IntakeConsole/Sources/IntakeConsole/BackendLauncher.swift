import Foundation
import Combine

class BackendLauncher: ObservableObject {
    @Published var isLaunching = false
    @Published var launchError: String?
    @Published var isRunning = false
    
    enum LaunchMode {
        case development // Backend started manually via scripts/dev.sh or python -m ...
        case managed     // App launches the backend itself
    }
    
    private let mode: LaunchMode
    private var process: Process?
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
        
        // Find the project root
        // In dev, it might be nearby. In prod, it would be in Resources.
        // For this slice, we assume we are running from the repo.
        let fileManager = FileManager.default
        let currentDir = fileManager.currentDirectoryPath
        let projectRoot = currentDir // Assuming we are run from the repo root
        
        let pythonPath = "\(projectRoot)/src"
        
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = ["python3", "-m", "intake.local_console.app"]
        
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = pythonPath
        env["INTAKE_HEADLESS"] = "1"
        env["INTAKE_LOCAL_PORT"] = "8000" // Force port for simplicity in this slice
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
                DispatchQueue.main.async {
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
        stopBackend()
    }
}
