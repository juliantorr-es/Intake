/**
 * Account settings and email verification UI.
 */

export async function getAccountSettings() {
    const response = await fetch('/api/account/settings');
    if (!response.ok) {
        throw new Error('Failed to fetch account settings');
    }
    return await response.json();
}

export async function startEmailVerification(email) {
    const response = await fetch('/api/account/email/start-verification', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email })
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to start verification');
    }
    return await response.json();
}

export async function verifyEmailCode(email, code) {
    const response = await fetch('/api/account/email/verify', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email, code })
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Invalid or expired verification code');
    }
    return await response.json();
}

export function createEmailVerificationUI(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const render = async () => {
        container.innerHTML = '';
        
        try {
            const settings = await getAccountSettings();
            
            const statusDiv = document.createElement('div');
            statusDiv.className = 'mb-md';
            
            if (settings.email.status === 'verified') {
                statusDiv.innerHTML = `
                    <p>Verified Email: <strong id="email-masked"></strong></p>
                    <p class="text-success">Status: Verified at ${new Date(settings.email.verified_at).toLocaleString()}</p>
                `;
                statusDiv.querySelector('#email-masked').textContent = settings.email.masked;
                container.appendChild(statusDiv);
            } else {
                if (settings.email.status === 'pending') {
                    statusDiv.innerHTML = `
                        <p>Pending Verification: <strong id="email-masked"></strong></p>
                        <p class="text-warning">Status: Verification Sent</p>
                    `;
                    statusDiv.querySelector('#email-masked').textContent = settings.email.masked;
                } else {
                    statusDiv.innerHTML = `<p class="text-muted">No email associated with this account.</p>`;
                }
                container.appendChild(statusDiv);

                // Add form
                const form = document.createElement('div');
                form.className = 'form-group mt-md';
                
                const emailInput = document.createElement('input');
                emailInput.type = 'email';
                emailInput.placeholder = 'Enter email address';
                emailInput.className = 'input mb-sm';
                emailInput.style.width = '100%';
                
                const startBtn = document.createElement('button');
                startBtn.className = 'btn btn-primary';
                startBtn.textContent = settings.email.status === 'pending' ? 'Resend Code' : 'Send Verification Code';
                
                form.appendChild(emailInput);
                form.appendChild(startBtn);
                container.appendChild(form);

                if (settings.email.status === 'pending') {
                    const verifyForm = document.createElement('div');
                    verifyForm.className = 'form-group mt-lg';
                    verifyForm.style.paddingTop = '20px';
                    verifyForm.style.borderTop = '1px dashed var(--color-border)';
                    
                    const codeInput = document.createElement('input');
                    codeInput.type = 'text';
                    codeInput.placeholder = '6-digit code';
                    codeInput.className = 'input mb-sm';
                    codeInput.style.width = '100%';
                    
                    const verifyBtn = document.createElement('button');
                    verifyBtn.className = 'btn btn-secondary';
                    verifyBtn.textContent = 'Verify Code';
                    
                    verifyForm.appendChild(codeInput);
                    verifyForm.appendChild(verifyBtn);
                    container.appendChild(verifyForm);

                    verifyBtn.onclick = async () => {
                        try {
                            // We use the masked email's domain or the input email?
                            // Usually we'd need the full email. Let's assume the user enters it or we store it in session/state.
                            // For simplicity, we'll ask for email again if not provided.
                            const email = emailInput.value || settings.email.masked;
                            await verifyEmailCode(email, codeInput.value);
                            alert('Email verified successfully!');
                            render();
                        } catch (err) {
                            alert(err.message);
                        }
                    };
                }

                startBtn.onclick = async () => {
                    if (!emailInput.value) {
                        alert('Please enter an email address');
                        return;
                    }
                    try {
                        await startEmailVerification(emailInput.value);
                        alert('Verification code sent! Check the local dev email sink.');
                        render();
                    } catch (err) {
                        alert(err.message);
                    }
                };
            }
        } catch (err) {
            container.textContent = 'Sign in to manage email settings.';
        }
    };

    render();
}
