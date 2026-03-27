// ── Suggest Idea Modal (shared across all pages) ──────────────────────────────
function showSuggestIdeaModal() {
  const existing = document.getElementById('suggest-idea-modal');
  if (existing) existing.remove();

  const modal = document.createElement('div');
  modal.id = 'suggest-idea-modal';
  modal.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.6);display:flex;align-items:center;justify-content:center;z-index:9999;backdrop-filter:blur(4px);';
  modal.innerHTML = `
    <div style="background:var(--glass-bg,#1a1a2e);border:1px solid var(--glass-border,rgba(255,255,255,0.1));border-radius:12px;padding:2rem;max-width:480px;width:90%;color:#f8fafc;position:relative;">
      <button id="suggest-close" style="position:absolute;top:0.75rem;right:0.75rem;background:none;border:none;color:rgba(248,250,252,0.6);font-size:1.3rem;cursor:pointer;">&times;</button>
      <h3 style="margin:0 0 0.5rem;font-size:1.3rem;font-weight:700;">Suggest an Idea</h3>
      <p style="color:rgba(248,250,252,0.6);font-size:0.9rem;margin-bottom:1.25rem;">Have a feature idea or improvement? We'd love to hear it!</p>
      <textarea id="suggest-text" rows="4" placeholder="Describe your idea..." style="width:100%;padding:0.65rem;border-radius:8px;border:1px solid rgba(255,255,255,0.1);background:rgba(0,0,0,0.3);color:#f8fafc;font-size:0.9rem;resize:vertical;box-sizing:border-box;"></textarea>
      <button id="suggest-submit" style="margin-top:1rem;width:100%;padding:0.65rem;border:none;border-radius:8px;background:var(--primary-light,#c13584);color:white;font-weight:600;font-size:0.95rem;cursor:pointer;">Submit Idea</button>
      <p id="suggest-status" style="text-align:center;margin-top:0.75rem;font-size:0.85rem;color:rgba(248,250,252,0.5);display:none;"></p>
    </div>
  `;
  document.body.appendChild(modal);

  modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
  document.getElementById('suggest-close').addEventListener('click', () => modal.remove());

  document.getElementById('suggest-submit').addEventListener('click', async () => {
    const text = document.getElementById('suggest-text').value.trim();
    const statusEl = document.getElementById('suggest-status');
    if (!text) {
      statusEl.textContent = 'Please enter your idea first.';
      statusEl.style.display = 'block';
      statusEl.style.color = '#f87171';
      return;
    }
    statusEl.textContent = 'Submitting...';
    statusEl.style.display = 'block';
    statusEl.style.color = 'rgba(248,250,252,0.5)';

    const token = localStorage.getItem('ps_token');
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    try {
      const resp = await fetch('/api/suggest-idea', {
        method: 'POST',
        headers,
        body: JSON.stringify({ idea: text }),
      });
      if (resp.ok) {
        statusEl.textContent = 'Thanks! Your idea has been submitted.';
        statusEl.style.color = '#4ade80';
        document.getElementById('suggest-text').value = '';
        setTimeout(() => modal.remove(), 2000);
      } else {
        statusEl.textContent = 'Could not submit. Please try again.';
        statusEl.style.color = '#f87171';
      }
    } catch {
      statusEl.textContent = 'Network error. Please try again.';
      statusEl.style.color = '#f87171';
    }
  });
}

// Wire up nav link on every page that includes this script
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('a.nav-link').forEach(link => {
    if (link.getAttribute('href') === '/suggest-idea') {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        showSuggestIdeaModal();
      });
    }
  });
});
