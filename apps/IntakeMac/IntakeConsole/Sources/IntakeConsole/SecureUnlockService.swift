import Foundation
import LocalAuthentication

@MainActor
class SecureUnlockService {
    static let shared = SecureUnlockService()
    
    private init() {}
    
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
