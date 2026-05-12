import SwiftUI

enum NavSection: String, CaseIterable, Identifiable {
    case inbox = "Inbox"
    case quotes = "Quotes"
    case uploads = "Uploads"
    case deliveries = "Deliveries"
    case deploy = "Deploy"
    case providers = "Providers"
    case settings = "Settings"
    
    var id: String { self.rawValue }
    
    var icon: String {
        switch self {
        case .inbox: return "tray.fill"
        case .quotes: return "doc.text.fill"
        case .uploads: return "arrow.up.doc.fill"
        case .deliveries: return "shippingbox.fill"
        case .deploy: return "cloud.fill"
        case .providers: return "externaldrive.connected.to.line.below.fill"
        case .settings: return "gearshape.fill"
        }
    }
}

struct ContentView: View {
    @StateObject var healthClient: BackendHealthClient
    @StateObject var launcher: BackendLauncher
    @State private var selectedSection: NavSection? = .quotes
    @State private var reloadTrigger = 0
    @State private var showInspector = true
    
    let backendURL: URL
    
    var body: some View {
        NavigationSplitView {
            // Sidebar
            List(NavSection.allCases, selection: $selectedSection) { section in
                NavigationLink(value: section) {
                    Label(section.rawValue, systemImage: section.icon)
                }
            }
            .navigationTitle("Intake")
            .listStyle(.sidebar)
            .background(VisualEffectView(material: .sidebar, blendingMode: .behindWindow))
        } detail: {
            // Main Panel
            HStack(spacing: 0) {
                VStack(spacing: 0) {
                    if healthClient.status == .online {
                        LocalConsoleWebView(url: backendURL, reloadTrigger: reloadTrigger)
                            .background(IntakeTheme.Colors.paper)
                    } else {
                        BackendOfflineView(healthClient: healthClient, launcher: launcher)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                
                // Proof Rail / Inspector
                if showInspector {
                    Divider()
                    ProofRailView()
                        .frame(width: 280)
                        .background(VisualEffectView(material: .sidebar, blendingMode: .behindWindow))
                }
            }
        }
        .toolbar {
            ToolbarItem(placement: .navigation) {
                HStack {
                    Image(systemName: "tray.and.arrow.down.fill")
                        .foregroundColor(IntakeTheme.Colors.stateInfo)
                    Text("Intake")
                        .font(.headline)
                }
            }
            
            ToolbarItem(placement: .status) {
                StatusChip(status: healthClient.status)
            }
            
            ToolbarItem(placement: .primaryAction) {
                Button(action: { reloadTrigger += 1 }) {
                    Label("Reload", systemImage: "arrow.clockwise")
                }
                .disabled(healthClient.status != .online)
            }
            
            ToolbarItem(placement: .primaryAction) {
                Button(action: { showInspector.toggle() }) {
                    Label("Inspector", systemImage: "sidebar.right")
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
}

struct StatusChip: View {
    let status: BackendStatus
    
    var body: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(statusColor)
                .frame(width: 8, height: 8)
            Text(status.displayName)
                .font(.system(size: 11, weight: .medium, design: .rounded))
                .foregroundColor(.secondary)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(Capsule().fill(Color.primary.opacity(0.05)))
    }
    
    private var statusColor: Color {
        switch status {
        case .starting: return IntakeTheme.Colors.stateWarn
        case .online: return IntakeTheme.Colors.stateOk
        case .offline: return IntakeTheme.Colors.muted
        case .failed: return IntakeTheme.Colors.stateError
        }
    }
}

struct BackendOfflineView: View {
    @ObservedObject var healthClient: BackendHealthClient
    @ObservedObject var launcher: BackendLauncher
    
    var body: some View {
        VStack(spacing: 20) {
            ProgressView()
                .scaleEffect(1.5)
            
            Text("Connecting to Local Console...")
                .font(.headline)
            
            Text("Backend Status: \(healthClient.status.displayName)")
                .foregroundColor(.secondary)
            
            if let error = launcher.launchError {
                Text(error)
                    .foregroundColor(IntakeTheme.Colors.stateError)
                    .font(.caption)
            }
            
            Button("Retry") {
                healthClient.checkHealth()
                launcher.ensureBackendRunning()
            }
            .buttonStyle(.borderedProminent)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(IntakeTheme.Colors.bg)
    }
}

struct ProofRailView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("PROOF RAIL")
                .font(.system(size: 11, weight: .bold))
                .foregroundColor(IntakeTheme.Colors.muted)
                .padding(.top, 20)
                .padding(.horizontal)
            
            ScrollView {
                VStack(spacing: 12) {
                    ProofItemView(title: "Local Decrypt", subtitle: "Quote payload verified", time: "NOW", icon: "lock.open.fill", color: IntakeTheme.Colors.stateOk)
                    ProofItemView(title: "Local Sync", subtitle: "Pulled 3 projections", time: "2m", icon: "arrow.triangle.2.circlepath", color: IntakeTheme.Colors.stateInfo)
                    ProofItemView(title: "Payload Stored", subtitle: "Encrypted envelope @ Hosted", time: "1h", icon: "tray.and.arrow.down.fill")
                    ProofItemView(title: "Upload Received", subtitle: "2 files @ Local Receiver", time: "1h", icon: "doc.badge.checkmark", color: IntakeTheme.Colors.stateOk)
                    ProofItemView(title: "Quote Submitted", subtitle: "Client session completed", time: "1h", icon: "paperplane.fill")
                    ProofItemView(title: "Email Verified", subtitle: "Client identity confirmed", time: "1h", icon: "checkmark.seal.fill", color: IntakeTheme.Colors.stateOk)
                    ProofItemView(title: "Passkey Auth", subtitle: "Device registration", time: "2h", icon: "key.fill")
                    
                    Divider().padding(.vertical, 8)
                    
                    Text("SIGNED ACTIONS")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundColor(IntakeTheme.Colors.muted)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    
                    ProofItemView(title: "Review Started", subtitle: "Action placeholder", time: "---", icon: "signature")
                }
                .padding()
            }
        }
    }
}

struct ProofItemView: View {
    let title: String
    let subtitle: String
    let time: String
    let icon: String
    var color: Color = .secondary
    
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .foregroundColor(color)
                .frame(width: 24, height: 24)
                .background(Circle().fill(color.opacity(0.1)))
            
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 13, weight: .medium))
                Text(subtitle)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
            
            Spacer()
            
            Text(time)
                .font(.system(size: 10, design: .monospaced))
                .foregroundColor(IntakeTheme.Colors.muted)
        }
        .padding(8)
        .background(RoundedRectangle(cornerRadius: 8).fill(Color.primary.opacity(0.03)))
    }
}

struct VisualEffectView: NSViewRepresentable {
    let material: NSVisualEffectView.Material
    let blendingMode: NSVisualEffectView.BlendingMode
    
    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = material
        view.blendingMode = blendingMode
        view.state = .active
        return view
    }
    
    func updateNSView(_ nsView: NSVisualEffectView, context: Context) {
        nsView.material = material
        nsView.blendingMode = blendingMode
    }
}
