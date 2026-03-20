// ── Auth State ──────────────────────────────────────────────────────────────
let currentUser = null;
const TOKEN_KEY = 'ps_token';
let authMode = 'signin'; // 'signin' | 'signup'

// ── DOM References ───────────────────────────────────────────────────────────
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const progressContainer = document.getElementById('progress-container');
const progressFill = document.getElementById('progress-fill');
const resultContainer = document.getElementById('result-container');
const downloadLink = document.getElementById('download-link');
const resetBtn = document.getElementById('reset-btn');
const statusText = document.getElementById('status-text');

const tabBtns = document.querySelectorAll('.tab-btn');
const insertSettings = document.getElementById('tool-settings-insert');
const dropTitle = document.getElementById('drop-title');
const dropDesc = document.getElementById('drop-desc');

const cropperSettings = document.getElementById('tool-settings-cropper');
const cropperRows = document.getElementById('cropper-rows');
const cropperCols = document.getElementById('cropper-cols');

const vectorizerSettings = document.getElementById('tool-settings-vectorizer');
const vectorizerPreset = document.getElementById('vectorizer-preset');

const insertFileZone = document.getElementById('insert-file-zone');
const insertFileInput = document.getElementById('insert-file-input');
const insertFileName = document.getElementById('insert-file-name');
const intervalInput = document.getElementById('interval-input');

const evenoddSettings = document.getElementById('tool-settings-evenodd');
const evenoddStart = document.getElementById('evenodd-start');
const evenoddEnd = document.getElementById('evenodd-end');
const evenoddType = document.getElementById('evenodd-type');
const stringResultContainer = document.getElementById('string-result-container');
const stringResult = document.getElementById('string-result');
const copyBtn = document.getElementById('copy-btn');
const generateBtn = document.getElementById('evenodd-generate-btn');

const swatchsetSettings   = document.getElementById('tool-settings-swatchset');
const ssRefZone           = document.getElementById('ss-ref-zone');
const ssRefInput          = document.getElementById('ss-ref-input');
const ssRefName           = document.getElementById('ss-ref-name');
const swatchsetGenerateBtn = document.getElementById('swatchset-generate-btn');
const ssGoalRadios        = document.querySelectorAll('input[name="ss-goal-type"]');
const ssGoalRgbInputs     = document.getElementById('ss-goal-rgb-inputs');
const ssGoalHexInputs     = document.getElementById('ss-goal-hex-inputs');
const ssGoalPantoneInputs = document.getElementById('ss-goal-pantone-inputs');

const proUpgradePrompt    = document.getElementById('pro-upgrade-prompt');
const userBar             = document.getElementById('user-bar');
const userInfoText        = document.getElementById('user-info-text');
const logoutBtn           = document.getElementById('logout-btn');
const proCta              = document.getElementById('pro-cta');
const signInBar           = document.getElementById('sign-in-bar');
const signInLink          = document.getElementById('sign-in-link');

// Tools that require login (free tier)
const AUTH_REQUIRED_TOOLS = ['duplexer', 'insertbetween', 'cropper'];
// Tools that require Pro
const PRO_TOOLS = ['vectorizer', 'swatchset'];

// Auth modal
const authModal           = document.getElementById('auth-modal');
const authModalTitle      = document.getElementById('auth-modal-title');
const authModalSubtitle   = document.getElementById('auth-modal-subtitle');
const authEmail           = document.getElementById('auth-email');
const authPassword        = document.getElementById('auth-password');
const authSubmitBtn       = document.getElementById('auth-submit-btn');
const authToggleLink      = document.getElementById('auth-toggle-link');
const authError           = document.getElementById('auth-error');

let currentTool = 'duplexer';
let insertFile = null;
let ssRefFile = null;

// ── App Init ─────────────────────────────────────────────────────────────────
async function initApp() {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
        // Not logged in — that's fine, let them browse
        updateUIForAuthState();
        return;
    }
    try {
        const me = await fetch('/auth/me', { headers: { 'Authorization': `Bearer ${token}` } });
        if (!me.ok) {
            localStorage.removeItem(TOKEN_KEY);
            updateUIForAuthState();
            return;
        }
        currentUser = await me.json();
        updateUIForAuthState();
    } catch (err) {
        console.error('Failed to restore session:', err);
        updateUIForAuthState();
    }
}

// ── Auth Helpers ──────────────────────────────────────────────────────────────
function getAuthHeaders() {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) return {};
    return { 'Authorization': `Bearer ${token}` };
}

async function handleAuthSuccess(data) {
    localStorage.setItem(TOKEN_KEY, data.access_token);
    currentUser = { email: data.email, is_pro: data.is_pro, monthly_jobs: data.monthly_jobs };
    hideAuthModal();
    updateUIForAuthState();
    // If they were trying to use a tool, let them continue
    updateUIForTool();
}

function handleSignOut() {
    localStorage.removeItem(TOKEN_KEY);
    currentUser = null;
    userBar.classList.add('hidden');
    signInBar.classList.remove('hidden');
    proCta.style.display = '';
}

function showAuthModal() {
    authModal.classList.remove('hidden');
    authEmail.focus();
}

// Dismiss auth modal by clicking the overlay background
authModal.addEventListener('click', (e) => {
    if (e.target === authModal) {
        hideAuthModal();
    }
});

function hideAuthModal() {
    authModal.classList.add('hidden');
    authError.classList.add('hidden');
    authError.textContent = '';
}

function updateUIForAuthState() {
    if (!currentUser) {
        // Not logged in — show sign-in link, hide user bar
        signInBar.classList.remove('hidden');
        userBar.classList.add('hidden');
        return;
    }

    // Logged in — hide sign-in link, show user bar
    signInBar.classList.add('hidden');
    userBar.classList.remove('hidden');

    if (currentUser.is_pro) {
        userInfoText.textContent = `${currentUser.email} ⚡ Pro`;
        proCta.style.display = 'none';
    } else {
        const remaining = Math.max(0, 20 - (currentUser.monthly_jobs || 0));
        userInfoText.textContent = `${currentUser.email} · ${remaining} jobs left this month`;
    }
}

async function handleAuthError(response) {
    if (response.status === 401) {
        showAuthModal();
        resetUI();
        return true;
    }
    if (response.status === 403) {
        showProUpgradeInCard();
        return true;
    }
    if (response.status === 429) {
        showFreeLimitReached();
        return true;
    }
    return false;
}

function showProUpgradeInCard() {
    hideAllPanels();
    proUpgradePrompt.classList.remove('hidden');
}

function showFreeLimitReached() {
    hideAllPanels();
    proUpgradePrompt.classList.remove('hidden');
    proUpgradePrompt.querySelector('h3').textContent = 'Monthly Limit Reached';
    proUpgradePrompt.querySelector('p').textContent =
        "You've used your 20 free jobs this month. Upgrade to Pro for unlimited access.";
}

// ── Auth Modal Events ─────────────────────────────────────────────────────────
authToggleLink.addEventListener('click', (e) => {
    e.preventDefault();
    authMode = authMode === 'signin' ? 'signup' : 'signin';
    if (authMode === 'signup') {
        authModalTitle.textContent = 'Create Account';
        authModalSubtitle.textContent = 'It\'s free — no credit card needed';
        authSubmitBtn.textContent = 'Create Account';
        authToggleLink.textContent = 'Sign in instead';
        authToggleLink.previousSibling.textContent = 'Already have an account? ';
    } else {
        authModalTitle.textContent = 'Sign In';
        authModalSubtitle.textContent = 'Access your Printssistant tools';
        authSubmitBtn.textContent = 'Sign In';
        authToggleLink.textContent = 'Create one free';
        authToggleLink.previousSibling.textContent = "Don't have an account? ";
    }
    authError.classList.add('hidden');
});

authSubmitBtn.addEventListener('click', async () => {
    const email = authEmail.value.trim();
    const password = authPassword.value;

    if (!email || !password) {
        showAuthError('Please enter your email and password.');
        return;
    }

    authSubmitBtn.disabled = true;
    authSubmitBtn.textContent = authMode === 'signin' ? 'Signing in...' : 'Creating account...';
    authError.classList.add('hidden');

    try {
        const endpoint = authMode === 'signin' ? '/auth/signin' : '/auth/signup';
        const resp = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        });
        const data = await resp.json();

        if (!resp.ok) {
            showAuthError(data.detail || 'Something went wrong. Please try again.');
        } else {
            await handleAuthSuccess(data);
        }
    } catch (err) {
        showAuthError('Something went wrong. Please try again.');
    } finally {
        authSubmitBtn.disabled = false;
        authSubmitBtn.textContent = authMode === 'signin' ? 'Sign In' : 'Create Account';
    }
});

// Allow Enter key to submit
[authEmail, authPassword].forEach(input => {
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') authSubmitBtn.click();
    });
});

function showAuthError(msg) {
    authError.textContent = msg;
    authError.classList.remove('hidden');
}

// ── Sign-In Link ──────────────────────────────────────────────────────────────
signInLink.addEventListener('click', (e) => {
    e.preventDefault();
    showAuthModal();
});

// ── Logout ────────────────────────────────────────────────────────────────────
logoutBtn.addEventListener('click', () => {
    handleSignOut();
});

// ── Tab Switching ─────────────────────────────────────────────────────────────
tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        tabBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentTool = btn.dataset.tool;

        // Pro tools: require login + pro
        if (PRO_TOOLS.includes(currentTool)) {
            if (!currentUser) {
                showAuthModal();
                return;
            }
            if (!currentUser.is_pro) {
                showProUpgradeInCard();
                return;
            }
        }

        // Auth-required tools: require login
        if (AUTH_REQUIRED_TOOLS.includes(currentTool) && !currentUser) {
            showAuthModal();
            return;
        }

        // Reset upgrade prompt title/text in case it was modified
        proUpgradePrompt.querySelector('h3').textContent = 'Printssistant Pro Feature';
        proUpgradePrompt.querySelector('p').textContent =
            'Unlock the Vectorizer and Swatch Set — plus unlimited use of all tools. One-time payment, lifetime access.';

        updateUIForTool();
        resetUI();
    });
});

function hideAllPanels() {
    insertSettings.classList.add('hidden');
    evenoddSettings.classList.add('hidden');
    cropperSettings.classList.add('hidden');
    vectorizerSettings.classList.add('hidden');
    swatchsetSettings.classList.add('hidden');
    dropZone.classList.add('hidden');
    stringResultContainer.classList.add('hidden');
    progressContainer.classList.add('hidden');
    resultContainer.classList.add('hidden');
    proUpgradePrompt.classList.add('hidden');
}

function updateUIForTool() {
    hideAllPanels();
    proUpgradePrompt.classList.add('hidden');
    fileInput.accept = ".pdf";

    if (currentTool === 'duplexer') {
        dropZone.classList.remove('hidden');
        dropTitle.innerText = "Drag & Drop PDF";
        dropDesc.innerText = "Standard Duplexing (Front/Back)";
    } else if (currentTool === 'insertbetween') {
        insertSettings.classList.remove('hidden');
        dropZone.classList.remove('hidden');
        dropTitle.innerText = "Drag & Drop Main PDF";
        dropDesc.innerText = "Upload the multi-page document here";
    } else if (currentTool === 'cropper') {
        cropperSettings.classList.remove('hidden');
        dropZone.classList.remove('hidden');
        dropTitle.innerText = "Drag & Drop PDF";
        dropDesc.innerText = "Upload the multi-page document to auto-crop";
    } else if (currentTool === 'vectorizer') {
        vectorizerSettings.classList.remove('hidden');
        dropZone.classList.remove('hidden');
        dropTitle.innerText = "Drag & Drop Image";
        dropDesc.innerText = "Upload an image (PNG, JPG) to vectorize";
        fileInput.accept = ".png,.jpg,.jpeg";
    } else if (currentTool === 'evenodd') {
        evenoddSettings.classList.remove('hidden');
    } else if (currentTool === 'swatchset') {
        swatchsetSettings.classList.remove('hidden');
    }
}

// ── Insert File ───────────────────────────────────────────────────────────────
insertFileZone.addEventListener('click', () => insertFileInput.click());
insertFileInput.addEventListener('change', () => {
    if (insertFileInput.files.length > 0) {
        insertFile = insertFileInput.files[0];
        insertFileName.innerText = insertFile.name;
        insertFileZone.classList.add('has-file');
    }
});
insertFileZone.addEventListener('dragover', (e) => { e.preventDefault(); insertFileZone.classList.add('dragging'); });
insertFileZone.addEventListener('dragleave', () => { insertFileZone.classList.remove('dragging'); });
insertFileZone.addEventListener('drop', (e) => {
    e.preventDefault();
    insertFileZone.classList.remove('dragging');
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        insertFile = files[0];
        insertFileName.innerText = insertFile.name;
        insertFileZone.classList.add('has-file');
    }
});

// ── Main Drop Zone ────────────────────────────────────────────────────────────
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragging'); });
dropZone.addEventListener('dragleave', () => { dropZone.classList.remove('dragging'); });
dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragging');
    const files = e.dataTransfer.files;
    if (files.length > 0) handleUpload(files[0]);
});
dropZone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) handleUpload(fileInput.files[0]);
});

// ── Upload Handler ────────────────────────────────────────────────────────────
async function handleUpload(file) {
    if (currentTool !== 'vectorizer' && !file.name.toLowerCase().endsWith('.pdf')) {
        alert('Please select a PDF file.');
        return;
    }
    if (currentTool === 'vectorizer' && !file.name.toLowerCase().match(/\.(jpg|jpeg|png)$/)) {
        alert('Please select a PNG or JPG file for vectorization.');
        return;
    }
    if (currentTool === 'insertbetween' && !insertFile) {
        alert('Please upload an Insert PDF first!');
        return;
    }

    dropZone.classList.add('hidden');
    insertSettings.classList.add('hidden');
    cropperSettings.classList.add('hidden');
    vectorizerSettings.classList.add('hidden');
    progressContainer.classList.remove('hidden');
    statusText.innerText = `Processing ${file.name}...`;

    let progress = 0;
    const intervalAnim = setInterval(() => {
        if (progress < 90) { progress += 5; progressFill.style.width = `${progress}%`; }
    }, 100);

    const formData = new FormData();
    let endpoint = '/upload';

    if (currentTool === 'duplexer') {
        formData.append('file', file);
        endpoint = '/upload';
    } else if (currentTool === 'insertbetween') {
        formData.append('base_file', file);
        formData.append('insert_file', insertFile);
        formData.append('interval', intervalInput.value);
        endpoint = '/insert';
    } else if (currentTool === 'cropper') {
        formData.append('file', file);
        formData.append('rows', cropperRows.value);
        formData.append('cols', cropperCols.value);
        endpoint = '/crop';
    } else if (currentTool === 'vectorizer') {
        formData.append('file', file);
        formData.append('preset', vectorizerPreset.value);
        endpoint = '/vectorize';
    }

    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: formData
        });

        clearInterval(intervalAnim);

        const handled = await handleAuthError(response);
        if (handled) return;

        const data = await response.json();
        progressFill.style.width = '100%';

        if (data.status === 'success') {
            setTimeout(() => {
                progressContainer.classList.add('hidden');
                resultContainer.classList.remove('hidden');
                downloadLink.href = `/download/${data.filename}`;
            }, 500);
        } else {
            alert('Error: ' + data.message);
            resetUI();
        }
    } catch (err) {
        clearInterval(intervalAnim);
        alert('Failed to connect to server.');
        resetUI();
    }
}

resetBtn.addEventListener('click', resetUI);

// ── Swatchset Goal Type Toggle ────────────────────────────────────────────────
ssGoalRadios.forEach(radio => {
    radio.addEventListener('change', () => {
        const val = document.querySelector('input[name="ss-goal-type"]:checked').value;
        ssGoalRgbInputs.classList.toggle('hidden', val !== 'rgb');
        ssGoalHexInputs.classList.toggle('hidden', val !== 'hex');
        ssGoalPantoneInputs.classList.toggle('hidden', val !== 'pantone');
    });
});

// ── Swatchset Reference Image ─────────────────────────────────────────────────
ssRefZone.addEventListener('click', () => ssRefInput.click());
ssRefInput.addEventListener('change', () => {
    if (ssRefInput.files.length > 0) {
        ssRefFile = ssRefInput.files[0];
        ssRefName.innerText = ssRefFile.name;
        ssRefZone.classList.add('has-file');
    }
});
ssRefZone.addEventListener('dragover', (e) => { e.preventDefault(); ssRefZone.classList.add('dragging'); });
ssRefZone.addEventListener('dragleave', () => ssRefZone.classList.remove('dragging'));
ssRefZone.addEventListener('drop', (e) => {
    e.preventDefault();
    ssRefZone.classList.remove('dragging');
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        ssRefFile = files[0];
        ssRefName.innerText = ssRefFile.name;
        ssRefZone.classList.add('has-file');
    }
});

// ── Swatchset Format Label ────────────────────────────────────────────────────
document.querySelectorAll('input[name="ss-format"]').forEach(radio => {
    radio.addEventListener('change', () => {
        const fmt = document.querySelector('input[name="ss-format"]:checked').value;
        swatchsetGenerateBtn.textContent = `Generate Swatch Set ${fmt.toUpperCase()}`;
    });
});

// ── Swatchset Generate ────────────────────────────────────────────────────────
swatchsetGenerateBtn.addEventListener('click', async () => {
    const goalType = document.querySelector('input[name="ss-goal-type"]:checked').value;

    if (goalType === 'hex') {
        const hexVal = document.getElementById('ss-goal-hex-val').value.trim();
        if (!hexVal || !/^#?[0-9a-fA-F]{6}$/.test(hexVal)) {
            alert('Please enter a valid 6-digit hex color (e.g. #FF5733).');
            return;
        }
    }
    if (goalType === 'pantone') {
        const ptVal = document.getElementById('ss-goal-pantone-val').value.trim();
        if (!ptVal) {
            alert('Please enter a Pantone color code (e.g. 485 C).');
            return;
        }
    }

    const outputFormat = document.querySelector('input[name="ss-format"]:checked').value;
    const formData = new FormData();
    formData.append('base_c', document.getElementById('ss-base-c').value);
    formData.append('base_m', document.getElementById('ss-base-m').value);
    formData.append('base_y', document.getElementById('ss-base-y').value);
    formData.append('base_k', document.getElementById('ss-base-k').value);
    formData.append('goal_type', goalType);
    formData.append('output_format', outputFormat);

    if (goalType === 'rgb') {
        formData.append('goal_r', document.getElementById('ss-goal-r').value);
        formData.append('goal_g', document.getElementById('ss-goal-g').value);
        formData.append('goal_b', document.getElementById('ss-goal-b').value);
    } else if (goalType === 'hex') {
        formData.append('goal_hex', document.getElementById('ss-goal-hex-val').value.trim());
    } else if (goalType === 'pantone') {
        formData.append('goal_pantone', document.getElementById('ss-goal-pantone-val').value.trim());
    }

    if (ssRefFile) formData.append('reference_image', ssRefFile);

    swatchsetSettings.classList.add('hidden');
    progressContainer.classList.remove('hidden');
    statusText.innerText = `Generating Swatch Set ${outputFormat.toUpperCase()}...`;

    let progress = 0;
    const intervalAnim = setInterval(() => {
        if (progress < 90) { progress += 10; progressFill.style.width = `${progress}%`; }
    }, 80);

    try {
        const response = await fetch('/swatchset', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: formData
        });

        clearInterval(intervalAnim);

        const handled = await handleAuthError(response);
        if (handled) return;

        const data = await response.json();
        progressFill.style.width = '100%';

        if (data.status === 'success') {
            setTimeout(() => {
                progressContainer.classList.add('hidden');
                resultContainer.classList.remove('hidden');
                downloadLink.href = `/download/${data.filename}`;
                downloadLink.download = data.filename;
                resetBtn.textContent = 'Create New Swatch Set';
            }, 500);
        } else {
            alert('Error: ' + (data.message || 'Unknown error'));
            resetUI();
        }
    } catch (err) {
        clearInterval(intervalAnim);
        alert('Failed to connect to server.');
        resetUI();
    }
});

// ── Even/Odd Generate ─────────────────────────────────────────────────────────
generateBtn.addEventListener('click', async () => {
    const formData = new FormData();
    formData.append('start', evenoddStart.value);
    formData.append('end', evenoddEnd.value);
    formData.append('type', evenoddType.value);

    evenoddSettings.classList.add('hidden');
    progressContainer.classList.remove('hidden');
    statusText.innerText = 'Generating Numbers...';

    try {
        const response = await fetch('/evenodd', { method: 'POST', body: formData });
        const data = await response.json();
        progressContainer.classList.add('hidden');

        if (data.status === 'success') {
            stringResultContainer.classList.remove('hidden');
            stringResult.value = data.result;
        } else {
            alert('Error generating numbers.');
            resetUI();
        }
    } catch (err) {
        alert('Failed to connect to server.');
        resetUI();
    }
});

// ── Copy Button ───────────────────────────────────────────────────────────────
copyBtn.addEventListener('click', () => {
    stringResult.select();
    document.execCommand("copy");
    copyBtn.innerText = "Copied!";
    setTimeout(() => { copyBtn.innerText = "Copy to Clipboard"; }, 2000);
});

// ── Reset UI ──────────────────────────────────────────────────────────────────
function resetUI() {
    resultContainer.classList.add('hidden');
    progressContainer.classList.add('hidden');
    stringResultContainer.classList.add('hidden');
    proUpgradePrompt.classList.add('hidden');
    progressFill.style.width = '0%';
    fileInput.value = '';

    if (currentTool !== 'evenodd' && currentTool !== 'swatchset') {
        dropZone.classList.remove('hidden');
    }
    if (currentTool === 'evenodd') evenoddSettings.classList.remove('hidden');
    if (currentTool === 'swatchset') {
        swatchsetSettings.classList.remove('hidden');
        ssRefFile = null;
        ssRefName.innerText = '';
        ssRefZone.classList.remove('has-file');
        resetBtn.textContent = 'Process Another';
    }
    if (currentTool === 'insertbetween') insertSettings.classList.remove('hidden');
    if (currentTool === 'cropper') cropperSettings.classList.remove('hidden');
    if (currentTool === 'vectorizer') vectorizerSettings.classList.remove('hidden');
}

// ── Start ─────────────────────────────────────────────────────────────────────
initApp();
