/**
 * Passkey authentication utilities.
 * Uses the Web Authentication API (WebAuthn).
 */

import { createElement, setTextContent, replaceContent } from './safe-dom.js';

/**
 * Configuration for the relying party.
 * These must match the server configuration.
 * 
 * Local development notes:
 * - RP ID must be a domain string, not an IP address
 * - Use 'localhost' for local dev (not '127.0.0.1')
 * - Origin must match exactly: http://localhost:8000
 * - Production must use HTTPS with a real domain
 */
export const RP_CONFIG = {
    id: window.location.hostname === 'localhost' ? 'localhost' : window.location.hostname,
    name: 'Intake',
    origin: window.location.origin
};

/**
 * Check if passkey authentication is supported.
 * @returns {boolean} Whether passkey auth is supported
 */
export function isPasskeySupported() {
    return !!window.PublicKeyCredential && !!navigator.credentials;
}

/**
 * Request registration options from the server.
 * @returns {Promise<Object>} Registration options
 */
export async function requestRegistrationOptions() {
    const response = await fetch('/api/auth/passkey/register/options', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    });
    
    if (!response.ok) {
        throw new Error(`Failed to get registration options: ${response.status} ${response.statusText}`);
    }
    
    const data = await response.json();
    return data.options;
}

/**
 * Register a new passkey.
 * @param {Object} options - Registration options from the server
 * @returns {Promise<Object>} Registration result
 */
export async function registerPasskey(options) {
    try {
        // Convert base64url challenge to Uint8Array
        const challenge = base64urlToBuffer(options.challenge);
        
        // User ID - may be provided or we generate one
        let userId;
        if (options.user && options.user.id) {
            userId = base64urlToBuffer(options.user.id);
        } else {
            userId = new Uint8Array(16);
            crypto.getRandomValues(userId);
        }
        
        // Build PublicKeyCredentialCreationOptions
        const publicKeyCredentialCreationOptions = {
            challenge: challenge,
            rp: {
                id: RP_CONFIG.id,
                name: RP_CONFIG.name
            },
            user: {
                id: userId,
                name: (options.user && options.user.name) || 'user',
                displayName: (options.user && options.user.displayName) || 'User'
            },
            pubKeyCredParams: options.pubKeyCredParams || [
                { type: 'public-key', alg: -7 },  // ES256
                { type: 'public-key', alg: -257 } // RS256
            ],
            authenticatorSelection: options.authenticatorSelection || {
                authenticatorAttachment: 'platform',
                requireResidentKey: true,
                userVerification: 'preferred'
            },
            supportedAlgorithms: options.supportedAlgorithms,
            extensions: options.extensions,
            timeout: options.timeout || 60000
        };
        
        // Create credential using WebAuthn API
        const credential = await navigator.credentials.create({
            publicKey: publicKeyCredentialCreationOptions
        });
        
        // Convert to JSON for server verification
        const credentialJSON = publicKeyCredentialToJSON(credential);
        
        // Verify with server
        const verifyResponse = await fetch('/api/auth/passkey/register/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ credential: credentialJSON })
        });
        
        if (!verifyResponse.ok) {
            const errorData = await verifyResponse.json().catch(() => ({}));
            throw new Error(`Registration verification failed: ${verifyResponse.status} - ${errorData.detail || errorData.message || ''}`);
        }
        
        return await verifyResponse.json();
    } catch (error) {
        console.error('Registration error:', error);
        throw error;
    }
}

/**
 * Request authentication options from the server.
 * @returns {Promise<Object>} Authentication options
 */
export async function requestAuthenticationOptions() {
    const response = await fetch('/api/auth/passkey/login/options', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    });
    
    if (!response.ok) {
        throw new Error(`Failed to get authentication options: ${response.status} ${response.statusText}`);
    }
    
    const data = await response.json();
    return data.options;
}

/**
 * Authenticate with a passkey.
 * @param {Object} options - Authentication options from the server
 * @returns {Promise<Object>} Authentication result
 */
export async function authenticateWithPasskey(options) {
    try {
        const challenge = base64urlToBuffer(options.challenge);
        
        // Build allowCredentials from options
        let allowCredentials = [];
        if (options.allowCredentials) {
            allowCredentials = options.allowCredentials.map(cred => ({
                id: base64urlToBuffer(cred.id),
                type: cred.type || 'public-key',
                transports: cred.transports
            }));
        }
        
        const publicKeyCredentialRequestOptions = {
            challenge: challenge,
            rpId: RP_CONFIG.id,
            allowCredentials: allowCredentials,
            userVerification: options.userVerification || 'preferred',
            extensions: options.extensions || {},
            timeout: options.timeout || 60000
        };
        
        const credential = await navigator.credentials.get({
            publicKey: publicKeyCredentialRequestOptions
        });
        
        // Convert to JSON for server verification
        const credentialJSON = publicKeyCredentialToJSON(credential);
        
        // Verify with server
        const verifyResponse = await fetch('/api/auth/passkey/login/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ credential: credentialJSON })
        });
        
        if (!verifyResponse.ok) {
            const errorData = await verifyResponse.json().catch(() => ({}));
            throw new Error(`Authentication verification failed: ${verifyResponse.status} - ${errorData.detail || errorData.message || ''}`);
        }
        
        return await verifyResponse.json();
    } catch (error) {
        console.error('Authentication error:', error);
        throw error;
    }
}

/**
 * Logout from the current session.
 * @returns {Promise<Object>} Logout result
 */
export async function logout() {
    const response = await fetch('/api/auth/passkey/logout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    });
    
    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(`Logout failed: ${response.status} - ${errorData.detail || ''}`);
    }
    
    return await response.json();
}

/**
 * Get current session info.
 * @returns {Promise<Object>} Session info
 */
export async function getSession() {
    const response = await fetch('/api/auth/passkey/session');
    
    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(`Session check failed: ${response.status} - ${errorData.detail || ''}`);
    }
    
    return await response.json();
}

/**
 * Create a passkey registration UI.
 * @param {Object} config - Configuration options
 * @returns {HTMLElement} The passkey registration element
 */
export function createPasskeyRegistrationUI(config = {}) {
    const container = createElement('div', { class: 'passkey-auth' });
    
    const title = createElement('h2', { class: 'passkey-auth-title' },
        config.title || 'Create Account'
    );
    const description = createElement('p', { class: 'passkey-auth-description' },
        config.description || 'Register with a passkey.'
    );
    const button = createElement('button', { class: 'btn btn-primary passkey-auth-btn' },
        'Create Passkey'
    );
    const status = createElement('div', { class: 'passkey-auth-status' });
    
    replaceContent(container, title, description, button, status);
    
    button.addEventListener('click', async () => {
        button.disabled = true;
        setTextContent(button, 'Creating...');
        
        try {
            const options = await requestRegistrationOptions();
            const result = await registerPasskey(options);
            
            status.className = 'passkey-auth-status passkey-auth-status-success';
            setTextContent(status, 'Passkey created successfully!');
            
            if (config.onSuccess) {
                config.onSuccess(result);
            }
        } catch (error) {
            status.className = 'passkey-auth-status passkey-auth-status-error';
            setTextContent(status, `Error: ${error.message}`);
            button.disabled = false;
            setTextContent(button, 'Create Passkey');
        }
    });
    
    return container;
}

/**
 * Create a passkey login UI.
 * @param {Object} config - Configuration options
 * @returns {HTMLElement} The passkey login element
 */
export function createPasskeyLoginUI(config = {}) {
    const container = createElement('div', { class: 'passkey-auth' });
    
    const title = createElement('h2', { class: 'passkey-auth-title' },
        config.title || 'Sign In'
    );
    const description = createElement('p', { class: 'passkey-auth-description' },
        config.description || 'Sign in with your passkey.'
    );
    const button = createElement('button', { class: 'btn btn-primary passkey-auth-btn' },
        'Sign In with Passkey'
    );
    const status = createElement('div', { class: 'passkey-auth-status' });
    
    replaceContent(container, title, description, button, status);
    
    button.addEventListener('click', async () => {
        button.disabled = true;
        setTextContent(button, 'Signing in...');
        
        try {
            const options = await requestAuthenticationOptions();
            const result = await authenticateWithPasskey(options);
            
            status.className = 'passkey-auth-status passkey-auth-status-success';
            setTextContent(status, 'Signed in successfully!');
            
            if (config.onSuccess) {
                config.onSuccess(result);
            }
        } catch (error) {
            status.className = 'passkey-auth-status passkey-auth-status-error';
            setTextContent(status, `Error: ${error.message}`);
            button.disabled = false;
            setTextContent(button, 'Sign In with Passkey');
        }
    });
    
    return container;
}

// ========== Helper Functions ==========

/**
 * Convert base64url string to Uint8Array.
 * Handles URL-safe base64 without padding.
 * @param {string} str - Base64url string
 * @returns {Uint8Array} Decoded bytes
 */
function base64urlToBuffer(str) {
    if (!str) {
        return new Uint8Array();
    }
    // Replace URL-safe base64 characters
    const base64 = str.replace(/-/g, '+').replace(/_/g, '/');
    // Add padding if needed
    const padLength = (4 - (base64.length % 4)) % 4;
    const padded = base64 + '='.repeat(padLength);
    return Uint8Array.from(atob(padded), c => c.charCodeAt(0));
}

/**
 * Convert Uint8Array to base64url string.
 * @param {Uint8Array} buffer - Bytes to encode
 * @returns {string} Base64url string
 */
function bufferToBase64url(buffer) {
    if (!buffer) {
        return '';
    }
    return btoa(String.fromCharCode(...new Uint8Array(buffer)))
        .replace(/\+/g, '-')
        .replace(/\//g, '_')
        .replace(/=/g, '');
}

/**
 * Convert a PublicKeyCredential to a JSON-serializable object.
 * Handles both registration (attestation) and authentication (assertion) credentials.
 * @param {PublicKeyCredential} credential - The credential from navigator.credentials
 * @returns {Object} JSON-serializable credential for server verification
 */
function publicKeyCredentialToJSON(credential) {
    if (!credential) {
        return null;
    }
    
    const result = {
        id: credential.id,
        rawId: bufferToBase64url(new Uint8Array(credential.rawId)),
        type: credential.type,
        response: {}
    };
    
    if (credential.response) {
        const response = credential.response;
        
        // Registration response (Attestation)
        if (response.attestationObject !== undefined) {
            result.response.attestationObject = bufferToBase64url(new Uint8Array(response.attestationObject));
            result.response.clientDataJSON = bufferToBase64url(new Uint8Array(response.clientDataJSON));
            
            // Handle getAuthenticatorData if available
            if (typeof response.getAuthenticatorData === 'function') {
                const authData = response.getAuthenticatorData();
                result.response.authenticatorData = bufferToBase64url(new Uint8Array(authData));
            }
        }
        
        // Authentication response (Assertion)
        if (response.authenticatorData !== undefined) {
            result.response.authenticatorData = bufferToBase64url(new Uint8Array(response.authenticatorData));
            result.response.clientDataJSON = bufferToBase64url(new Uint8Array(response.clientDataJSON));
            result.response.signature = bufferToBase64url(new Uint8Array(response.signature));
            
            if (response.userHandle !== undefined && response.userHandle !== null) {
                result.response.userHandle = bufferToBase64url(new Uint8Array(response.userHandle));
            }
        }
    }
    
    return result;
}
