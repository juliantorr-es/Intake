import SwiftUI

// UI Truthfulness: Only show sections that have real implemented surfaces
// Inbox: Not implemented - removed
// Deliveries: Actually opens Cost Ledger - renamed to "Cost Ledger"
// Deploy: Real but dry-run only - kept as "Deploy Readiness"
// Providers: Shows cost providers - renamed to "Cost Providers"
enum NavSection: String, CaseIterable, Identifiable {
    case dashboard = "Dashboard"
    case quotes = "Quotes"
    case uploads = "Uploads"
    case costLedger = "Cost Ledger"
    case deploy = "Deploy Readiness"
    case costProviders = "Cost Providers"
    case settings = "Settings"
    
    var id: String { self.rawValue }
    
    var icon: String {
        switch self {
        case .dashboard: return "tray.fill"
        case .quotes: return "doc.text.fill"
        case .uploads: return "arrow.up.doc.fill"
        case .costLedger: return "dollarsign.circle.fill"
        case .deploy: return "cloud.fill"
        case .costProviders: return "externaldrive.connected.to.line.below.fill"
        case .settings: return "gearshape.fill"
        }
    }
}

struct ContentView: View {
    @StateObject var healthClient: BackendHealthClient
    @StateObject var launcher: BackendLauncher
    @StateObject var authState = LocalAuthorizationState()
    
    @State private var selectedSection: NavSection? = .dashboard
    @State private var reloadTrigger = 0
    @State private var showInspector = true
    
    let backendURL: URL
    
    private var currentURL: URL {
        guard let section = selectedSection else { return backendURL }
        switch section {
        case .dashboard:
            return backendURL
        case .quotes:
            return backendURL.appendingPathComponent("quotes")
        case .uploads:
            return backendURL.appendingPathComponent("uploads")
        case .costLedger:
            return backendURL.appendingPathComponent("costs")
        case .deploy:
            return backendURL.appendingPathComponent("deploy")
        case .costProviders:
            return backendURL.appendingPathComponent("providers")
        case .settings:
            return backendURL.appendingPathComponent("settings")
        }
    }
    
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
                        LocalConsoleWebView(url: currentURL, reloadTrigger: reloadTrigger)
                            .background(IntakeTheme.Colors.paper)
                            .id(currentURL.absoluteString) // Ensure view re-identity on URL change if needed, though updateNSView handles it
                    } else {
                        BackendOfflineView(healthClient: healthClient, launcher: launcher)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                
                // Proof Rail / Inspector
                if showInspector {
                    Divider()
                    ProofRailView(backendBaseURL: backendURL)
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
        .onReceive(NotificationCenter.default.publisher(for: Notification.Name("RequestSecureUnlock"))) { _ in
            performSecureUnlock()
        }
        .onReceive(NotificationCenter.default.publisher(for: Notification.Name("LockSecureSession"))) { _ in
            performSecureLock()
        }
    }
    
    private func performSecureUnlock() {
        Task {
            // Step 1: Perform native OS authentication
            let result = await SecureUnlockService.shared.requestUnlock(reason: "Access decrypted client intake data")
            
            await MainActor.run {
                switch result {
                case .success:
                    // Native auth succeeded - now complete the challenge flow
                    completeUnlockFlow()
                case .failed(let reason):
                    authState.setFailed(reason: reason)
                case .cancelled, .unavailable:
                    break
                }
            }
        }
    }
    
    private func completeUnlockFlow() {
        Task {
            do {
                // Step 2: Fetch challenge from backend
                let challengeToken = try await SecureUnlockService.shared.fetchChallengeToken(
                    backendURL: backendURL
                )
                
                // Step 3: Complete unlock with challenge + native proof
                let response = try await SecureUnlockService.shared.completeUnlockWithChallenge(
                    challengeToken: challengeToken,
                    backendURL: backendURL
                )
                
                await MainActor.run {
                    // Check if unlock was successful in the response
                    if let response = response, 
                       let isUnlocked = response["is_unlocked"] as? Bool, 
                       isUnlocked == true {
                        authState.unlock()
                        reloadTrigger += 1 // Trigger webview reload to see decrypted data
                    } else {
                        authState.setFailed(reason: "Backend unlock failed")
                    }
                }
            } catch UnlockError.missingNativeCapability {
                await MainActor.run {
                    authState.setFailed(reason: "Native capability not configured. Use managed backend mode.")
                }
            } catch UnlockError.serverError(let statusCode, let message) {
                await MainActor.run {
                    authState.setFailed(reason: "Server error: HTTP \(statusCode) - \(message.prefix(100))")
                }
            } catch {
                await MainActor.run {
                    authState.setFailed(reason: "Unlock Failed: \(error.localizedDescription.prefix(100))")
                }
            }
        }
    }
    
    private func performSecureLock() {
        authState.lock()
        notifyBackendOfLock()
    }
    
    private func notifyBackendOfLock() {
        guard let url = URL(string: "\(backendURL.absoluteString)/api/local/security/lock") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        
        URLSession.shared.dataTask(with: request) { _, _, _ in
            DispatchQueue.main.async {
                self.reloadTrigger += 1
            }
        }.resume()
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
    @State private var proofEvents: [ProofEvent] = []
    @State private var isLoading = true
    @State private var errorMessage: String? = nil
    
    // Received from parent to avoid hardcoding
    let backendBaseURL: URL
    
    // Timer to refresh proof rail periodically
    @State private var refreshTimer: Timer?
    
    struct ProofEvent: Identifiable {
        let id: String
        let title: String
        let subtitle: String
        let time: String
        let icon: String
        let color: Color
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("PROOF RAIL")
                .font(.system(size: 11, weight: .bold))
                .foregroundColor(IntakeTheme.Colors.muted)
                .padding(.top, 20)
                .padding(.horizontal)
            
            ScrollView {
                VStack(spacing: 12) {
                    if isLoading {
                        ProgressView()
                            .padding(.vertical, 20)
                    } else if let errorMessage {
                        Text("Not Available")
                            .font(.system(size: 12))
                            .foregroundColor(IntakeTheme.Colors.stateWarn)
                            .padding(.vertical, 8)
                        Text(errorMessage)
                            .font(.system(size: 10))
                            .foregroundColor(IntakeTheme.Colors.muted)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.bottom, 8)
                    } else if proofEvents.isEmpty {
                        Text("No proof events yet")
                            .font(.system(size: 12))
                            .foregroundColor(IntakeTheme.Colors.muted)
                            .frame(maxWidth: .infinity, alignment: .center)
                            .padding(.vertical, 20)
                    } else {
                        ForEach(proofEvents) { event in
                            ProofItemView(
                                title: event.title,
                                subtitle: event.subtitle,
                                time: event.time,
                                icon: event.icon,
                                color: event.color
                            )
                        }
                    }
                }
                .padding()
            }
        }
        .onAppear {
            loadProofEvents()
        }
        .onDisappear {
            refreshTimer?.invalidate()
            refreshTimer = nil
        }
    }
    
    private func loadProofEvents() {
        Task {
            // UI Truthfulness: Only show real proof events from API
            // If API fails or returns empty, show honest empty state
            // Use the provided backendBaseURL instead of hardcoded URL
            let proofRailURL = backendBaseURL
                .appendingPathComponent("api")
                .appendingPathComponent("local")
                .appendingPathComponent("proof-rail")
                .appendingQueryParameters(["limit": "20"])
            
            guard let url = proofRailURL else {
                await MainActor.run {
                    self.isLoading = false
                    self.errorMessage = "Invalid proof rail URL"
                }
                return
            }
            
            do {
                let (data, response) = try await URLSession.shared.data(from: url)
                
                await MainActor.run {
                    if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 {
                        if let jsonArray = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] {
                            var events: [ProofEvent] = []
                            for json in jsonArray {
                                let event = ProofEvent(
                                    id: json["event_id"] as? String ?? UUID().uuidString,
                                    title: json["event_type"] as? String ?? "Unknown",
                                    subtitle: json["details"] as? String ?? json["message"] as? String ?? "",
                                    time: json["created_at"] as? String ?? "",
                                    icon: iconForEvent(json["event_type"] as? String),
                                    color: colorForEvent(json["event_type"] as? String)
                                )
                                events.append(event)
                            }
                            
                            self.proofEvents = events
                            self.isLoading = false
                            self.errorMessage = nil
                        } else {
                            // If we got a 200 but no valid JSON, this might be a real empty state
                            self.proofEvents = []
                            self.isLoading = false
                            self.errorMessage = nil
                        }
                    } else {
                        // API returned non-200 - proof rail might not be configured
                        self.isLoading = false
                        self.errorMessage = "Proof rail not configured (HTTP " + String(describing: (response as? HTTPURLResponse)?.statusCode) + ")"
                    }
                }
            } catch {
                // Network error or API not available - show honest state
                await MainActor.run {
                    self.isLoading = false
                    self.errorMessage = "Proof rail API unavailable: " + error.localizedDescription
                }
            }
        }
    }
    
    private func iconForEvent(_ eventType: String?) -> String {
        switch eventType?.lowercased() {
        case "quote_created", "quote_submitted": return "doc.fill"
        case "upload_received", "upload_completed": return "arrow.up.doc.fill"
        case "decrypt_success", "decryption_complete": return "lock.open.fill"
        case "sync_pull", "sync_complete": return "arrow.triangle.2.circlepath"
        case "email_verified": return "checkmark.seal.fill"
        case "passkey_registration", "passkey_auth": return "key.fill"
        case "session_started", "session_complete": return "clock.fill"
        case "cost_scenario_created", "cost_receipt_generated": return "dollarsign.circle.fill"
        default: return "questionmark.circle.fill"
        }
    }
    
    private func colorForEvent(_ eventType: String?) -> Color {
        switch eventType?.lowercased() {
        case "decrypt_success", "quote_submitted", "upload_completed", "email_verified":
            return IntakeTheme.Colors.stateOk
        case "sync_pull", "sync_complete", "passkey_auth":
            return IntakeTheme.Colors.stateInfo
        case "session_started":
            return IntakeTheme.Colors.stateWarn
        default:
            return .secondary
        }
    }
}

// Helper extension for URL query parameters
extension URL {
    func appendingQueryParameters(_ parameters: [String: String]) -> URL? {
        var components = URLComponents(url: self, resolvingAgainstBaseURL: true)
        components?.queryItems = parameters.map { URLQueryItem(name: $0.key, value: $0.value) }
        return components?.url
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
