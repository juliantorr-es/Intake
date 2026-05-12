document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

async function initApp() {
    // Navigation
    const navItems = document.querySelectorAll('.nav-item');
    const views = document.querySelectorAll('.view');
    
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const targetId = item.id.replace('nav-', 'view-');
            showView(targetId);
            
            navItems.forEach(nav => nav.classList.remove('active'));
            item.classList.add('active');
        });
    });

    document.getElementById('btn-back-to-list').addEventListener('click', () => {
        showView('view-quotes');
    });

    document.getElementById('btn-sync').addEventListener('click', triggerSync);
    
    // Secure Unlock Actions
    document.getElementById('btn-request-unlock').addEventListener('click', requestSecureUnlock);
    document.getElementById('btn-lock-now').addEventListener('click', lockSecureSession);

    // Initial load
    await updateStatus();
    await loadPendingQuotes();
}

function showView(viewId) {
    document.querySelectorAll('.view').forEach(view => {
        view.classList.add('hidden');
    });
    document.getElementById(viewId).classList.remove('hidden');
    
    // Update title
    const titles = {
        'view-dashboard': 'Dashboard',
        'view-quotes': 'Pending Quotes',
        'view-quote-detail': 'Quote Review',
        'view-settings': 'Settings'
    };
    document.getElementById('page-title').textContent = titles[viewId] || 'Console';
}

async function updateStatus() {
    try {
        const response = await fetch('/api/local/status');
        const status = await response.json();
        
        document.getElementById('conf-hosted-url').textContent = status.hosted_url;
        
        const syncAuthEl = document.getElementById('conf-sync-auth');
        syncAuthEl.textContent = status.sync_auth_configured ? 'Configured' : 'Missing';
        syncAuthEl.className = 'badge ' + (status.sync_auth_configured ? 'success' : 'warning');
        
        const encKeyEl = document.getElementById('conf-enc-key');
        encKeyEl.textContent = status.encryption_key_configured ? 'Active' : 'Not Set';
        encKeyEl.className = 'badge ' + (status.encryption_key_configured ? 'success' : 'warning');
        
        const signKeyEl = document.getElementById('conf-signing-key');
        signKeyEl.textContent = status.signing_key_configured ? 'Active' : 'Not Set';
        signKeyEl.className = 'badge ' + (status.signing_key_configured ? 'success' : 'warning');

        // Settings Page
        const unlockReqEl = document.getElementById('settings-unlock-required');
        if (unlockReqEl) {
            unlockReqEl.textContent = status.local_unlock_required ? 'Enabled' : 'Disabled';
            unlockReqEl.className = 'badge ' + (status.local_unlock_required ? 'success' : 'warning');
        }
        
        const unlockTTLEl = document.getElementById('settings-unlock-ttl');
        if (unlockTTLEl) {
            unlockTTLEl.textContent = `${status.local_unlock_ttl} seconds`;
        }
        
    } catch (err) {
        console.error('Failed to update status:', err);
    }
}

async function loadPendingQuotes() {
    try {
        const response = await fetch('/api/local/quotes/pending');
        const quotes = await response.json();
        
        document.getElementById('stat-pending-count').textContent = quotes.length;
        
        const tbody = document.getElementById('quote-list-body');
        tbody.innerHTML = '';
        
        quotes.forEach(quote => {
            const tr = document.createElement('tr');
            
            const cells = [
                quote.quote_id,
                quote.status,
                quote.general_service_area || 'N/A',
                quote.upload_count.toString()
            ];
            
            cells.forEach(text => {
                const td = document.createElement('td');
                td.textContent = text;
                tr.appendChild(td);
            });
            
            const actionTd = document.createElement('td');
            const btn = document.createElement('button');
            btn.className = 'btn';
            btn.textContent = 'Review';
            btn.onclick = () => showQuoteDetail(quote.quote_id);
            actionTd.appendChild(btn);
            tr.appendChild(actionTd);
            
            tbody.appendChild(tr);
        });
    } catch (err) {
        console.error('Failed to load quotes:', err);
        const tbody = document.getElementById('quote-list-body');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--state-error);">Hosted backend unavailable or sync failed.</td></tr>';
        }
    }
}

async function showQuoteDetail(quoteId) {
    try {
        const response = await fetch(`/api/local/quotes/${quoteId}/review`);
        const detail = await response.json();
        
        document.getElementById('detail-quote-id').textContent = `Quote ${detail.quote_id}`;
        document.getElementById('detail-status').textContent = detail.status.toUpperCase();
        document.getElementById('detail-lane').textContent = detail.service_lane || 'GENERAL';
        document.getElementById('detail-area').textContent = detail.general_service_area || 'N/A';
        document.getElementById('detail-email-verified').classList.toggle('hidden', !detail.email_verified);
        
        // Handle Lock State
        const unlockOverlay = document.getElementById('unlock-required-overlay');
        const unlockStatus = document.getElementById('unlock-status-container');
        
        if (detail.is_locked) {
            unlockOverlay.classList.remove('hidden');
            unlockStatus.classList.add('hidden');
            document.getElementById('detail-location').textContent = '••••••••';
            document.getElementById('detail-notes').textContent = '••••••••';
            document.getElementById('detail-questionnaire').textContent = '{ "locked": true }';
        } else {
            unlockOverlay.classList.add('hidden');
            unlockStatus.classList.remove('hidden');
            document.getElementById('detail-location').textContent = detail.exact_location || 'Not provided';
            document.getElementById('detail-notes').textContent = detail.access_notes || 'No notes';
            document.getElementById('detail-questionnaire').textContent = JSON.stringify(detail.questionnaire_answers, null, 2);
            
            // Start timer
            startUnlockTimer();
        }
        
        // Render evidence
        document.getElementById('detail-upload-count').textContent = detail.upload_count;
        const evidenceContainer = document.getElementById('detail-upload-evidence');
        evidenceContainer.innerHTML = '';
        
        if (detail.upload_evidence && detail.upload_evidence.length > 0) {
            detail.upload_evidence.forEach(ev => {
                const row = document.createElement('div');
                row.className = 'info-item';
                row.style.marginTop = '12px';
                row.style.borderTop = '1px solid var(--color-border)';
                row.style.paddingTop = '8px';
                
                const left = document.createElement('div');
                left.style.display = 'flex';
                left.style.flexDirection = 'column';
                
                const filename = document.createElement('span');
                filename.style.fontWeight = '600';
                filename.style.fontSize = '13px';
                filename.textContent = ev.original_filename || `file-${ev.file_id.substring(0, 8)}`;
                
                const meta = document.createElement('span');
                meta.style.fontSize = '11px';
                meta.style.color = 'var(--color-muted)';
                meta.style.fontFamily = 'var(--font-mono)';
                meta.textContent = `${ev.content_type} • ${(ev.size_bytes / 1024).toFixed(1)} KB • sha256:${ev.sha256.substring(0, 8)}`;
                
                left.appendChild(filename);
                left.appendChild(meta);
                
                const provider = document.createElement('span');
                provider.className = 'badge';
                provider.style.fontSize = '10px';
                provider.textContent = ev.storage_provider;
                
                row.appendChild(left);
                row.appendChild(provider);
                
                evidenceContainer.appendChild(row);
            });
        }
        
        // Handle "Start Review" button visibility
        const btnStart = document.getElementById('btn-start-review');
        if (detail.status === 'submitted' || detail.status === 'needs_review') {
            btnStart.classList.remove('hidden');
            btnStart.onclick = () => startReview(detail.quote_id);
        } else {
            btnStart.classList.add('hidden');
        }

        showView('view-quote-detail');
    } catch (err) {
        console.error('Failed to load quote detail:', err);
        showView('view-quote-detail');
    }
}

async function startReview(quoteId) {
    const btn = document.getElementById('btn-start-review');
    btn.disabled = true;
    btn.textContent = 'Processing...';
    
    try {
        const response = await fetch(`/api/local/quotes/${quoteId}/start-review`, { method: 'POST' });
        if (response.ok) {
            alert('Review started successfully!');
            await showQuoteDetail(quoteId); // Refresh
        } else {
            const err = await response.json();
            alert(`Error: ${err.detail}`);
            btn.disabled = false;
            btn.textContent = 'Start Review';
        }
    } catch (err) {
        console.error('Failed to start review:', err);
        alert('Failed to start review. See console for logs.');
        btn.disabled = false;
        btn.textContent = 'Start Review';
    }
}

async function triggerSync() {
    const btn = document.getElementById('btn-sync');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = 'Syncing...';
    
    try {
        await fetch('/api/local/sync/pull', { method: 'POST' });
        await loadPendingQuotes();
    } catch (err) {
        console.error('Sync failed:', err);
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

async function requestSecureUnlock() {
    console.log('JS: Requesting Secure Unlock...');
    if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.requestSecureUnlock) {
        window.webkit.messageHandlers.requestSecureUnlock.postMessage(null);
    } else {
        // Fallback for browser testing
        const response = await fetch('/api/local/security/unlock', { method: 'POST' });
        if (response.ok) {
            location.reload();
        }
    }
}

async function lockSecureSession() {
    console.log('JS: Locking Session...');
    if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.lockSecureSession) {
        window.webkit.messageHandlers.lockSecureSession.postMessage(null);
    } else {
        await fetch('/api/local/security/lock', { method: 'POST' });
        location.reload();
    }
}

let unlockTimer = null;
async function startUnlockTimer() {
    if (unlockTimer) clearInterval(unlockTimer);
    
    const updateTimer = async () => {
        try {
            const response = await fetch('/api/local/security/status');
            const status = await response.json();
            
            if (!status.is_unlocked) {
                location.reload(); // Re-lock view
                clearInterval(unlockTimer);
                return;
            }
            
            const minutes = Math.floor(status.remaining_seconds / 60);
            const seconds = Math.floor(status.remaining_seconds % 60);
            const timeStr = `${minutes}:${seconds.toString().padStart(2, '0')}`;
            const timeEl = document.getElementById('unlock-time');
            if (timeEl) timeEl.textContent = timeStr;
            
        } catch (err) {
            console.error('Failed to update unlock timer:', err);
            clearInterval(unlockTimer);
        }
    };
    
    await updateTimer();
    unlockTimer = setInterval(updateTimer, 1000);
}
