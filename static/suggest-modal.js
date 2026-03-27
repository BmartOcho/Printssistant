// ── Suggest Idea Modal (shared across all pages) ──────────────────────────────
function showSuggestIdeaModal() {
  const existing = document.getElementById('suggest-idea-modal');
  if (existing) existing.remove();

  const modal = document.createElement('div');
  modal.id = 'suggest-idea-modal';
  modal.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.6);display:flex;align-items:center;justify-content:center;z-index:9999;backdrop-filter:blur(4px);overflow-y:auto;';
  modal.innerHTML = `
    <div style="background:var(--glass-bg,#1a1a2e);border:1px solid var(--glass-border,rgba(255,255,255,0.1));border-radius:12px;padding:2rem;max-width:480px;width:90%;color:#f8fafc;position:relative;margin:2rem auto;">
      <button id="suggest-close" style="position:absolute;top:0.75rem;right:0.75rem;background:none;border:none;color:rgba(248,250,252,0.6);font-size:1.3rem;cursor:pointer;">&times;</button>
      <h3 style="margin:0 0 0.25rem;font-size:1.3rem;font-weight:700;">Suggest a Tool or Feature</h3>
      <p style="color:rgba(248,250,252,0.6);font-size:0.875rem;margin-bottom:1.5rem;">What would make your prepress workflow better?</p>

      <div style="margin-bottom:1rem;">
        <label style="display:block;font-size:0.875rem;font-weight:500;margin-bottom:0.35rem;">Your Name <span style="opacity:0.5;">(Optional)</span></label>
        <input id="suggest-name" type="text" placeholder="Your name" style="width:100%;padding:0.65rem;border-radius:6px;border:1px solid rgba(255,255,255,0.1);background:rgba(255,255,255,0.05);color:#f8fafc;font-size:0.9rem;box-sizing:border-box;" />
      </div>

      <div style="margin-bottom:1rem;">
        <label style="display:block;font-size:0.875rem;font-weight:500;margin-bottom:0.35rem;">Your Email <span style="color:#f87171;">*</span></label>
        <input id="suggest-email" type="email" placeholder="your@email.com" style="width:100%;padding:0.65rem;border-radius:6px;border:1px solid rgba(255,255,255,0.1);background:rgba(255,255,255,0.05);color:#f8fafc;font-size:0.9rem;box-sizing:border-box;" />
        <small style="display:block;margin-top:0.3rem;opacity:0.5;font-size:0.8rem;">So we can reach out if we build it.</small>
      </div>

      <div style="margin-bottom:1rem;">
        <label style="display:block;font-size:0.875rem;font-weight:500;margin-bottom:0.35rem;">Idea Title <span style="color:#f87171;">*</span></label>
        <input id="suggest-title" type="text" placeholder="e.g., Batch color space conversion" style="width:100%;padding:0.65rem;border-radius:6px;border:1px solid rgba(255,255,255,0.1);background:rgba(255,255,255,0.05);color:#f8fafc;font-size:0.9rem;box-sizing:border-box;" />
      </div>

      <div style="margin-bottom:1rem;">
        <label style="display:block;font-size:0.875rem;font-weight:500;margin-bottom:0.35rem;">Describe the Problem <span style="color:#f87171;">*</span></label>
        <textarea id="suggest-description" rows="4" placeholder="What's the pain point? How would this tool solve it?" style="width:100%;padding:0.65rem;border-radius:6px;border:1px solid rgba(255,255,255,0.1);background:rgba(255,255,255,0.05);color:#f8fafc;font-size:0.9rem;resize:vertical;box-sizing:border-box;font-family:inherit;"></textarea>
      </div>

      <div style="margin-bottom:1.25rem;">
        <label style="display:block;font-size:0.875rem;font-weight:500;margin-bottom:0.35rem;">How Often Do You Face This? <span style="color:#f87171;">*</span></label>
        <select id="suggest-impact" style="width:100%;padding:0.65rem;border-radius:6px;border:1px solid rgba(255,255,255,0.1);background:rgba(255,255,255,0.05);color:#f8fafc;font-size:0.9rem;box-sizing:border-box;">
          <option value="">-- Select --</option>
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
          <option value="sometimes">Sometimes</option>
        </select>
      </div>

      <button id="suggest-submit" style="width:100%;padding:0.75rem;border:none;border-radius:6px;background:linear-gradient(135deg,var(--primary,#833ab4),var(--primary-light,#c13584));color:white;font-weight:600;font-size:0.95rem;cursor:pointer;">Send Idea</button>
      <p id="suggest-status" style="text-align:center;margin-top:0.75rem;font-size:0.85rem;color:rgba(248,250,252,0.5);display:none;"></p>
    </div>
  `;
  document.body.appendChild(modal);

  modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
  document.getElementById('suggest-close').addEventListener('click', () => modal.remove());

  document.getElementById('suggest-submit').addEventListener('click', async () => {
    const name        = document.getElementById('suggest-name').value.trim();
    const email       = document.getElementById('suggest-email').value.trim();
    const title       = document.getElementById('suggest-title').value.trim();
    const description = document.getElementById('suggest-description').value.trim();
    const impact      = document.getElementById('suggest-impact').value;
    const statusEl    = document.getElementById('suggest-status');

    if (!email || !title || !description || !impact) {
      statusEl.textContent = 'Please fill in all required fields.';
      statusEl.style.display = 'block';
      statusEl.style.color = '#f87171';
      return;
    }

    const submitBtn = document.getElementById('suggest-submit');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Sending...';
    statusEl.style.display = 'none';

    try {
      const resp = await fetch('/api/suggestions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name || 'Anonymous',
          email,
          title,
          description,
          impact,
          submittedAt: new Date().toISOString(),
        }),
      });

      if (resp.ok) {
        statusEl.textContent = 'Thanks! Your idea has been submitted.';
        statusEl.style.display = 'block';
        statusEl.style.color = '#4ade80';
        setTimeout(() => modal.remove(), 2500);
      } else {
        const data = await resp.json().catch(() => ({}));
        statusEl.textContent = data.detail || 'Could not submit. Please try again.';
        statusEl.style.display = 'block';
        statusEl.style.color = '#f87171';
        submitBtn.disabled = false;
        submitBtn.textContent = 'Send Idea';
      }
    } catch {
      statusEl.textContent = 'Network error. Please try again.';
      statusEl.style.display = 'block';
      statusEl.style.color = '#f87171';
      submitBtn.disabled = false;
      submitBtn.textContent = 'Send Idea';
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
