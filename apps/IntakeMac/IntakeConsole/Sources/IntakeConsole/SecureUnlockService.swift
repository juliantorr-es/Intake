import Foundation
import LocalAuthentication

enum SecureUnlockResult {
    case success
    case cancelled
    case unavailable
    case failed(String)
}

class SecureUnlockService {
    static let shared = SecureUnlockService()
    
    private init() {}
    
    func requestUnlock(reason: String) async -> SecureUnlockResult {
        let context = LAContext()
        var error: NSError?
        
        // Use deviceOwnerAuthentication for biometric + passcode fallback
        let policy = LAPolicy.deviceOwnerAuthentication
        
        guard context.canEvaluatePolicy(policy, error: &error) else {
            let errorMsg = error?.localizedDescription ?? "Biometrics/Passcode not available"
            print("SecureUnlockService: Policy check failed: \(errorMsg)")
            return .unavailable
        }
        
        do {
            let success = try await context.evaluatePolicy(policy, localizedReason: reason)
            if success {
                return .success
            } else {
                // This usually results in an error being thrown, but handle false just in case
                return .failed("Authentication failed")
            }
        } catch let error as LAError {
            switch error.code {
            case .userCancel, .appCancel, .systemCancel:
                return .cancelled
            case .biometryNotAvailable, .biometryNotEnrolled, .passcodeNotSet:
                return .unavailable
            default:
                return .failed(error.localizedDescription)
            }
        } catch {
            return .failed(error.localizedDescription)
        }
    }
}
