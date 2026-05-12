import Foundation
import Security

/// Scaffold for future local unlock secret or signing key storage.
/// In production, this would use SecAccessControl with .biometryCurrentSet or .userPresence.
class KeychainSecretStore {
    static let shared = KeychainSecretStore()
    
    private let service = "com.intake.local-console"
    private let account = "unlock-authorization-token"
    
    private init() {}
    
    func storeSecret(_ secret: String) throws {
        // Implementation for future slice
        print("KeychainSecretStore: Store secret scaffold (not implemented)")
    }
    
    func getSecret() -> String? {
        // Implementation for future slice
        return nil
    }
    
    func deleteSecret() {
        // Implementation for future slice
    }
}
