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
        'view-quote-detail': 'Quote Review'
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
            
            // Securely create cell contents
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
    }
}

async function showQuoteDetail(quoteId) {
    try {
        const response = await fetch(`/api/local/quotes/${quoteId}/review`);
        const detail = await response.json();
        
        document.getElementById('detail-quote-id').textContent = `Quote ${detail.quote_id}`;
        document.getElementById('detail-status').textContent = detail.status;
        document.getElementById('detail-lane').textContent = detail.service_lane || 'N/A';
        document.getElementById('detail-area').textContent = detail.general_service_area || 'N/A';
        
        document.getElementById('detail-location').textContent = detail.exact_location || 'Not provided';
        document.getElementById('detail-notes').textContent = detail.access_notes || 'No notes';
        document.getElementById('detail-questionnaire').textContent = JSON.stringify(detail.questionnaire_answers, null, 2);
        
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
        alert('Failed to load quote detail. See console for logs.');
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
