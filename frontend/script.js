// ── Auth State ──────────────────────────────────────────────────────────────
let currentUser = null;
const TOKEN_KEY = 'ps_token';
let authMode = 'signin'; // 'signin' | 'signup'
let selectedUserType = null; // 'og' | 'dg' — captured during signup

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
const duplexerSettings = document.getElementById('tool-settings-duplexer');
const groupSizeInput = document.getElementById('group-size-input');
const insertSettings = document.getElementById('tool-settings-insert');
const dropTitle = document.getElementById('drop-title');
const dropDesc = document.getElementById('drop-desc');

const cropperSettings = document.getElementById('tool-settings-cropper');
const cropperMode = document.getElementById('cropper-mode');
const cropperModeDesc = document.getElementById('cropper-mode-desc');
const cropperGridOptions = document.getElementById('cropper-grid-options');
const cropperRows = document.getElementById('cropper-rows');
const cropperCols = document.getElementById('cropper-cols');

const vectorizerSettings = document.getElementById('tool-settings-vectorizer');
const vectorizerPreset = document.getElementById('vectorizer-preset');

// Vectorizer result elements
const vecResult = document.getElementById('vec-result');
const vecOriginal = document.getElementById('vec-original');
const vecOutput = document.getElementById('vec-output');
const vecPaths = document.getElementById('vec-paths');
const vecPoints = document.getElementById('vec-points');
const vecColors = document.getElementById('vec-colors');
const vecTime = document.getElementById('vec-time');
const vecEngine = document.getElementById('vec-engine');
const vecWarnings = document.getElementById('vec-warnings');
const vecDownload = document.getElementById('vec-download');
const vecResetBtn = document.getElementById('vec-reset');
const vecAdvancedToggle = document.getElementById('vec-advanced-toggle');
const vecAdvancedPanel = document.getElementById('vec-advanced-panel');
const vecSlidersContainer = document.getElementById('vec-sliders');
const vecOutputFormat = document.getElementById('vec-output-format');
let vecOriginalDataUrl = null;
let vecParamsCache = {};
let vecLastFile = null;
const vecReprocessBtn = document.getElementById('vec-reprocess');
const vecTweakPreset = document.getElementById('vec-tweak-preset');
const vecTweakFormat = document.getElementById('vec-tweak-format');
const vecTweakSliders = document.getElementById('vec-tweak-sliders');

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
const navAuthBtn          = document.getElementById('nav-auth-btn');

// Cropper label presets: value → { rows, cols, desc }
const CROPPER_LABEL_PRESETS = {
    label_10x3:   { rows: 10, cols: 3 },
    label_10x2:   { rows: 10, cols: 2 },
    label_7x2:    { rows: 7,  cols: 2 },
    label_5x2:    { rows: 5,  cols: 2 },
    label_3x2:    { rows: 3,  cols: 2 },
    label_20x4:   { rows: 20, cols: 4 },
    label_2x2:    { rows: 2,  cols: 2 },
    label_15x4:   { rows: 15, cols: 4 },
    label_15x3:   { rows: 15, cols: 3 },
    label_5x2_bc: { rows: 5,  cols: 2 },
    label_3x2_nb: { rows: 3,  cols: 2 },
    label_4x2:    { rows: 4,  cols: 2 },
};

// Cropper preset toggle
cropperMode.addEventListener('change', () => {
    const val = cropperMode.value;
    const preset = CROPPER_LABEL_PRESETS[val];

    if (val === 'reader_spreads') {
        cropperGridOptions.classList.add('hidden');
        cropperModeDesc.innerText = 'First and last pages kept whole; middle pages split into left/right halves.';
    } else if (preset) {
        cropperRows.value = preset.rows;
        cropperCols.value = preset.cols;
        cropperGridOptions.classList.add('hidden');
        cropperModeDesc.innerText = `${preset.rows} rows × ${preset.cols} columns — ${preset.rows * preset.cols} labels per sheet.`;
    } else {
        cropperGridOptions.classList.remove('hidden');
        cropperModeDesc.innerText = 'Specify how many rows and columns to split each page into.';
    }
});

// ── Vectorizer Advanced Settings ─────────────────────────────────────────────
vecAdvancedToggle.addEventListener('click', () => {
    vecAdvancedPanel.classList.toggle('hidden');
    vecAdvancedToggle.textContent = vecAdvancedPanel.classList.contains('hidden')
        ? 'Advanced Settings' : 'Hide Advanced';
});

async function loadVecParams(presetKey, container) {
    container = container || vecSlidersContainer;
    if (vecParamsCache[presetKey]) {
        renderVecSliders(vecParamsCache[presetKey], container);
        return;
    }
    try {
        const res = await fetch(`/vectorizer-params?preset=${presetKey}`);
        if (res.ok) {
            const params = await res.json();
            vecParamsCache[presetKey] = params;
            renderVecSliders(params, container);
        }
    } catch (e) { /* silent — sliders won't show */ }
}

function renderVecSliders(params, container) {
    container = container || vecSlidersContainer;
    container.innerHTML = '';
    for (const [key, meta] of Object.entries(params)) {
        const group = document.createElement('div');
        group.className = 'vec-slider-group';
        group.innerHTML = `
            <div class="vec-slider-header">
                <span class="vec-slider-label">${meta.label}</span>
                <span class="vec-slider-value">default</span>
            </div>
            <div class="vec-slider-desc">${meta.description}</div>
            <input type="range" class="vec-slider-input"
                   min="${meta.min}" max="${meta.max}" step="${meta.step}"
                   data-key="${key}" data-default="true" />
        `;
        container.appendChild(group);

        const slider = group.querySelector('.vec-slider-input');
        const valSpan = group.querySelector('.vec-slider-value');
        slider.addEventListener('input', () => {
            slider.dataset.default = 'false';
            valSpan.textContent = slider.value;
        });
    }
}

function getVecOverridesFrom(container) {
    const overrides = {};
    container.querySelectorAll('.vec-slider-input').forEach(slider => {
        if (slider.dataset.default === 'false') {
            overrides[slider.dataset.key] = parseFloat(slider.value);
        }
    });
    return Object.keys(overrides).length ? JSON.stringify(overrides) : '';
}

let vecUseReprocessOverrides = false;

function getVecOverrides() {
    if (vecUseReprocessOverrides) {
        return getVecOverridesFrom(vecTweakSliders);
    }
    return getVecOverridesFrom(vecSlidersContainer);
}

vectorizerPreset.addEventListener('change', () => loadVecParams(vectorizerPreset.value, vecSlidersContainer));
vecTweakPreset.addEventListener('change', () => loadVecParams(vecTweakPreset.value, vecTweakSliders));

// Re-process: re-submit stored file with tweaked settings
vecReprocessBtn.addEventListener('click', () => {
    if (!vecLastFile) return;
    vectorizerPreset.value = vecTweakPreset.value;
    vecOutputFormat.value = vecTweakFormat.value;
    vecUseReprocessOverrides = true;
    vecResult.classList.add('hidden');
    handleUpload(vecLastFile);
});

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
const forgotPasswordText  = document.getElementById('forgot-password-text');

let currentTool = 'duplexer';
let insertFile = null;
let ssRefFile = null;

// ── App Init ─────────────────────────────────────────────────────────────────
async function initApp() {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
        // Not logged in — that's fine, let them browse
        updateUIForAuthState();
        updateUIForTool();
        maybeOpenSignInFromParam();
        return;
    }
    try {
        const me = await fetch('/auth/me', { headers: { 'Authorization': `Bearer ${token}` } });
        if (!me.ok) {
            localStorage.removeItem(TOKEN_KEY);
            updateUIForAuthState();
            updateUIForTool();
            maybeOpenSignInFromParam();
            return;
        }
        currentUser = await me.json();
        updateUIForAuthState();
    } catch (err) {
        console.error('Failed to restore session:', err);
        updateUIForAuthState();
        maybeOpenSignInFromParam();
    }
    updateUIForTool();
}

function maybeOpenSignInFromParam() {
    const params = new URLSearchParams(window.location.search);
    if (params.get('signin') === 'true') {
        // Remove the param from the URL without a page reload
        history.replaceState(null, '', window.location.pathname);
        if (!currentUser) {
            showAuthModal();
        }
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
    currentUser = {
        email: data.email,
        is_pro: data.is_pro,
        monthly_jobs: data.monthly_jobs,
        user_type: data.user_type,
    };
    hideAuthModal();
    updateUIForAuthState();
    // If they were trying to use a tool, let them continue
    updateUIForTool();
}

function handleSignOut() {
    localStorage.removeItem(TOKEN_KEY);
    currentUser = null;
    updateUIForAuthState();
    proCta.style.display = '';
}

function showAuthModal() {
    authModal.classList.remove('hidden');
    authEmail.focus();
    // Show forgot password link (only visible in signin mode)
    forgotPasswordText.style.display = authMode === 'signin' ? 'block' : 'none';
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
    const navProfileLink = document.getElementById('nav-profile-link');
    if (!currentUser) {
        // Not logged in — hide user bar, show "Sign In" button
        userBar.classList.add('hidden');
        navAuthBtn.textContent = 'Sign In';
        if (navProfileLink) navProfileLink.classList.add('hidden');
        return;
    }

    // Logged in — show user bar, show "Sign Out" button
    userBar.classList.remove('hidden');
    navAuthBtn.textContent = 'Sign Out';
    if (navProfileLink) navProfileLink.classList.remove('hidden');

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
    const userTypeRow = document.getElementById('user-type-row');
    if (authMode === 'signup') {
        authModalTitle.textContent = 'Create Account';
        authModalSubtitle.textContent = 'It\'s free — no credit card needed';
        authSubmitBtn.textContent = 'Create Account';
        authToggleLink.textContent = 'Sign in instead';
        authToggleLink.previousSibling.textContent = 'Already have an account? ';
        forgotPasswordText.style.display = 'none';
        if (userTypeRow) userTypeRow.style.display = 'block';
    } else {
        authModalTitle.textContent = 'Sign In';
        authModalSubtitle.textContent = 'Access your Printssistant tools';
        authSubmitBtn.textContent = 'Sign In';
        authToggleLink.textContent = 'Create one free';
        authToggleLink.previousSibling.textContent = "Don't have an account? ";
        forgotPasswordText.style.display = 'block';
        if (userTypeRow) userTypeRow.style.display = 'none';
        selectedUserType = null;
    }
    authError.classList.add('hidden');
});

// ── User type button wiring (signup modal) ─────────────────────────────────
['og', 'dg'].forEach(type => {
    const btn = document.getElementById(`type-${type}-btn`);
    if (!btn) return;
    btn.addEventListener('click', () => {
        selectedUserType = type;
        document.querySelectorAll('.user-type-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
    });
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
        const body = { email, password };
        if (authMode === 'signup' && selectedUserType) body.user_type = selectedUserType;
        const resp = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
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

// ── Nav Auth Button (Sign In / Sign Out) ──────────────────────────────────────
navAuthBtn.addEventListener('click', (e) => {
    e.preventDefault();
    if (currentUser) {
        // User is logged in — sign them out
        handleSignOut();
    } else {
        // User is not logged in — show sign in modal
        showAuthModal();
    }
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
    duplexerSettings.classList.add('hidden');
    insertSettings.classList.add('hidden');
    evenoddSettings.classList.add('hidden');
    cropperSettings.classList.add('hidden');
    vectorizerSettings.classList.add('hidden');
    swatchsetSettings.classList.add('hidden');
    dropZone.classList.add('hidden');
    stringResultContainer.classList.add('hidden');
    progressContainer.classList.add('hidden');
    resultContainer.classList.add('hidden');
    vecResult.classList.add('hidden');
    proUpgradePrompt.classList.add('hidden');
}

function updateUIForTool() {
    hideAllPanels();
    proUpgradePrompt.classList.add('hidden');
    fileInput.accept = ".pdf";

    if (currentTool === 'duplexer') {
        duplexerSettings.classList.remove('hidden');
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
        loadVecParams(vectorizerPreset.value);
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

    // Capture original image for vectorizer preview and keep file for re-processing
    if (currentTool === 'vectorizer') {
        vecLastFile = file;
        if (!vecOriginalDataUrl) {
            vecOriginalDataUrl = await new Promise(resolve => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result);
                reader.readAsDataURL(file);
            });
        }
    }

    dropZone.classList.add('hidden');
    duplexerSettings.classList.add('hidden');
    insertSettings.classList.add('hidden');
    cropperSettings.classList.add('hidden');
    vectorizerSettings.classList.add('hidden');
    progressContainer.classList.remove('hidden');
    statusText.innerText = `Uploading ${file.name}...`;
    progressFill.style.width = '0%';

    const formData = new FormData();
    let endpoint = '/upload';

    if (currentTool === 'duplexer') {
        formData.append('file', file);
        formData.append('group_size', groupSizeInput.value);
        endpoint = '/upload';
    } else if (currentTool === 'insertbetween') {
        formData.append('base_file', file);
        formData.append('insert_file', insertFile);
        formData.append('interval', intervalInput.value);
        endpoint = '/insert';
    } else if (currentTool === 'cropper') {
        formData.append('file', file);
        const isLabel = CROPPER_LABEL_PRESETS[cropperMode.value];
        formData.append('mode', isLabel ? 'grid' : cropperMode.value);
        formData.append('rows', cropperRows.value);
        formData.append('cols', cropperCols.value);
        endpoint = '/crop';
    } else if (currentTool === 'vectorizer') {
        formData.append('file', file);
        formData.append('preset', vectorizerPreset.value);
        formData.append('output_format', vecOutputFormat.value);
        const ov = getVecOverrides();
        if (ov) formData.append('overrides', ov);
        endpoint = '/vectorize';
    }

    // Use XMLHttpRequest for real upload progress tracking
    const xhr = new XMLHttpRequest();

    const uploadPromise = new Promise((resolve, reject) => {
        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
                const pct = Math.round((e.loaded / e.total) * 90); // 0-90% for upload
                progressFill.style.width = `${pct}%`;
                statusText.innerText = `Uploading ${file.name}... ${pct}%`;
            }
        };

        xhr.upload.onload = () => {
            progressFill.style.width = '90%';
            statusText.innerText = 'Processing...';
        };

        xhr.onload = () => {
            resolve({ status: xhr.status, response: xhr.responseText });
        };

        xhr.onerror = () => reject(new Error('Network error'));
        xhr.ontimeout = () => reject(new Error('Request timed out'));

        xhr.open('POST', endpoint);
        // Set auth headers (skip Content-Type — FormData sets it with boundary)
        const token = localStorage.getItem(TOKEN_KEY);
        if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
        xhr.send(formData);
    });

    try {
        const { status, response: responseText } = await uploadPromise;

        // Handle auth errors
        if (status === 401) { showAuthModal(); resetUI(); return; }
        if (status === 403) { showProUpgradeInCard(); return; }
        if (status === 429) { showFreeLimitReached(); return; }

        const data = JSON.parse(responseText);
        progressFill.style.width = '100%';

        if (data.status === 'success') {
            setTimeout(() => {
                progressContainer.classList.add('hidden');
                if (currentTool === 'vectorizer' && data.preview_bw) {
                    // Show vectorizer-specific result with preview + stats
                    vecOriginal.src = vecOriginalDataUrl || '';
                    vecOutput.src = `data:image/png;base64,${data.preview_bw}`;
                    vecDownload.href = `/download/${data.filename}`;
                    vecDownload.textContent = `Download ${data.filename.endsWith('.pdf') ? 'PDF' : 'SVG'}`;

                    const s = data.stats || {};
                    vecPaths.textContent = (s.path_count ?? '-').toLocaleString();
                    vecPoints.textContent = (s.point_count ?? '-').toLocaleString();
                    vecColors.textContent = s.color_count ?? '-';
                    vecTime.textContent = s.processing_time != null ? `${s.processing_time}s` : '-';
                    vecEngine.textContent = s.engine ?? '-';

                    // Warnings
                    const warns = s.warnings || [];
                    if (warns.length) {
                        vecWarnings.innerHTML = warns.map(w => `<div>${w}</div>`).join('');
                        vecWarnings.classList.remove('hidden');
                    } else {
                        vecWarnings.classList.add('hidden');
                    }

                    // Populate tweak panel with current settings
                    vecTweakPreset.value = vectorizerPreset.value;
                    vecTweakFormat.value = vecOutputFormat.value;
                    vecUseReprocessOverrides = false;
                    loadVecParams(vecTweakPreset.value, vecTweakSliders);

                    vecResult.classList.remove('hidden');
                } else {
                    resultContainer.classList.remove('hidden');
                    downloadLink.href = `/download/${data.filename}`;
                }
            }, 500);
        } else {
            alert('Error: ' + data.message);
            resetUI();
        }
    } catch (err) {
        alert('Failed to connect to server.');
        resetUI();
    }
}

resetBtn.addEventListener('click', resetUI);
vecResetBtn.addEventListener('click', resetUI);

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
    vecResult.classList.add('hidden');
    progressContainer.classList.add('hidden');
    stringResultContainer.classList.add('hidden');
    proUpgradePrompt.classList.add('hidden');
    progressFill.style.width = '0%';
    fileInput.value = '';
    vecOriginalDataUrl = null;
    vecLastFile = null;
    vecUseReprocessOverrides = false;

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
