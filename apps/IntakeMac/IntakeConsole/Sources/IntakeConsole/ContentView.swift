import SwiftUI

struct ContentView: View {
    @StateObject var healthClient: BackendHealthClient
    @StateObject var launcher: BackendLauncher
    @State private var reloadTrigger = 0
    
    let backendURL: URL
    
    var body: some View {
        VStack(spacing: 0) {
            if healthClient.status == .online {
                LocalConsoleWebView(url: backendURL, reloadTrigger: reloadTrigger)
            } else {
                VStack(spacing: 20) {
                    ProgressView()
                        .scaleEffect(1.5)
                    
                    Text("Connecting to Local Console...")
                        .font(.headline)
                    
                    Text("Backend Status: \(healthClient.status.displayName)")
                        .foregroundColor(statusColor)
                    
                    if let error = launcher.launchError {
                        Text(error)
                            .foregroundColor(.red)
                            .font(.caption)
                    }
                    
                    Button("Retry") {
                        healthClient.checkHealth()
                        launcher.ensureBackendRunning()
                    }
                    .buttonStyle(.borderedProminent)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .toolbar {
            ToolbarItem(placement: .navigation) {
                HStack {
                    Image(systemName: "tray.and.arrow.down.fill")
                        .foregroundColor(.accentColor)
                    Text("Intake")
                        .font(.headline)
                }
            }
            
            ToolbarItem(placement: .status) {
                HStack {
                    Circle()
                        .fill(statusColor)
                        .frame(width: 8, height: 8)
                    Text(healthClient.status.displayName)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            
            ToolbarItem(placement: .primaryAction) {
                Button(action: { reloadTrigger += 1 }) {
                    Label("Reload", systemImage: "arrow.clockwise")
                }
                .disabled(healthClient.status != .online)
            }
            
            ToolbarItem(placement: .primaryAction) {
                Button(action: { /* Open Logs */ }) {
                    Label("Logs", systemImage: "doc.text")
                }
            }
            
            ToolbarItem(placement: .primaryAction) {
                Button(action: { /* Settings */ }) {
                    Label("Settings", systemImage: "gearshape")
                }
            }
        }
        .onAppear {
            launcher.ensureBackendRunning()
            healthClient.startMonitoring()
        }
        .onDisappear {
            healthClient.stopMonitoring()
        }
    }
    
    private var statusColor: Color {
        switch healthClient.status {
        case .starting: return .orange
        case .online: return .green
        case .offline: return .gray
        case .failed: return .red
        }
    }
}
