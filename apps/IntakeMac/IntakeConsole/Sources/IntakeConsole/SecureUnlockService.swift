import Foundation
import LocalAuthentication

enum UnlockError: Error {
    case missingNativeCapability
    case invalidResponse
    case serverError(statusCode: Int, message: String)
}

@MainActor
class SecureUnlockService {
    static let shared = SecureUnlockService()
    
    // Native capability token - set by BackendLauncher when starting the backend
    private var nativeCapabilityToken: String? = nil
    
    private init() {}
    
    /// Set the native capability token (called by BackendLauncher in managed mode).
    /// - Parameter token: The 32-byte hex capability token that matches the backend's config.
    func setNativeCapability(_ token: String) {
        self.nativeCapabilityToken = token
    }
    
    /// Get the native capability token for use in unlock requests.
    /// Returns nil if not configured (e.g., in development mode without managed backend).
    func getNativeCapability() -> String? {
        return nativeCapabilityToken
    }
    
    /// Returns the available biometry type on the device.
    func getBiometryType() -> String {
        let context = LAContext()
        var error: NSError?
        
        // We check with deviceOwnerAuthentication to see what's available
        if context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error) {
            switch context.biometryType {
            case .touchID:
                return "touchID"
            case .faceID:
                return "faceID"
            case .opticID:
                return "opticID"
            case .none:
                return "passcode"
            @unknown default:
                return "unknown"
            }
        }
        return "unavailable"
    }
    
    /// Performs an unlock request against the backend with challenge and native proof.
    /// This is called after LAContext succeeds to complete the unlock flow.
    /// - Parameters:
    ///   - challengeToken: The challenge token obtained from /api/local/security/challenge
    ///   - backendURL: The base URL of the backend
    /// - Returns: UnlockStatus from the backend, or nil on network error
    func completeUnlockWithChallenge(
        challengeToken: String,
        backendURL: URL
    ) async throws -> [String: Any]? {
        guard let capability = nativeCapabilityToken else {
            throw UnlockError.missingNativeCapability
        }
        
        let unlockURL = backendURL
            .appendingPathComponent("api")
            .appendingPathComponent("local")
            .appendingPathComponent("security")
            .appendingPathComponent("unlock")
        
        var request = URLRequest(url: unlockURL)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let requestBody: [String: Any] = [
            "challenge_token": challengeToken,
            "native_proof": capability,
            "proof_kind": "native_capability"
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: requestBody)
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw UnlockError.invalidResponse
        }
        
        guard (200...299).contains(httpResponse.statusCode) else {
            let responseString = String(data: data, encoding: .utf8) ?? ""
            throw UnlockError.serverError(statusCode: httpResponse.statusCode, message: responseString)
        }
        
        return try JSONSerialization.jsonObject(with: data) as? [String: Any]
    }

    /// Fetches a challenge token from the backend.
    /// - Parameter backendURL: The base URL of the backend
    /// - Returns: The challenge token string
    func fetchChallengeToken(backendURL: URL) async throws -> String {
        let challengeURL = backendURL
            .appendingPathComponent("api")
            .appendingPathComponent("local")
            .appendingPathComponent("security")
            .appendingPathComponent("challenge")
        
        let (data, response) = try await URLSession.shared.data(from: challengeURL)
        
        guard let httpResponse = response as? HTTPURLResponse, 
              httpResponse.statusCode == 200 else {
            throw UnlockError.serverError(statusCode: 404, message: "Challenge endpoint not available")
        }
        
        guard let dict = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let token = dict["challenge_token"] as? String else {
            throw UnlockError.invalidResponse
        }
        
        return token
    }

    /// Requests a local secure unlock using biometrics (Touch ID/Face ID) or device passcode.
    /// - Parameter reason: The localized reason shown to the user in the auth prompt.
    /// - Returns: An UnlockResult indicating success or failure.
    func requestUnlock(reason: String) async -> UnlockResult {
        let context = LAContext()
        var error: NSError?
        
        // LAPolicy.deviceOwnerAuthentication allows fallback to device passcode.
        // This aligns with "Local Secure Unlock" branding rather than "biometric-only".
        if context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error) {
            do {
                let success = try await context.evaluatePolicy(
                    .deviceOwnerAuthentication,
                    localizedReason: reason
                )
                
                if success {
                    return .success
                } else {
                    return .failed(reason: "Authentication failed")
                }
            } catch let authError as LAError {
                switch authError.code {
                case .userCancel:
                    return .cancelled
                case .authenticationFailed:
                    return .failed(reason: "Authentication failed")
                case .passcodeNotSet:
                    return .failed(reason: "Device passcode not set")
                case .biometryNotAvailable:
                    return .failed(reason: "Biometrics unavailable")
                case .biometryNotEnrolled:
                    return .failed(reason: "Biometrics not enrolled")
                default:
                    return .failed(reason: authError.localizedDescription)
                }
            } catch {
                return .failed(reason: error.localizedDescription)
            }
        } else {
            let reason = error?.localizedDescription ?? "Secure Unlock unavailable on this device"
            return .failed(reason: reason)
        }
    }
}

/// Scaffold for future Keychain-bound local authority.
@MainActor
class KeychainSecretStore {
    static let shared = KeychainSecretStore()
    
    private init() {}
    
    func storeSecret(_ secret: String, for account: String) -> Bool {
        // TODO: Implement actual Keychain storage with SecAccessControl
        // This is a placeholder scaffold for the "Keychain-bound" future.
        print("KeychainSecretStore: Placeholder store for \(account)")
        return true
    }
    
    func fetchSecret(for account: String) -> String? {
        // TODO: Implement actual Keychain retrieval
        return nil
    }
}
