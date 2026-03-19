const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const progressContainer = document.getElementById('progress-container');
const progressFill = document.getElementById('progress-fill');
const resultContainer = document.getElementById('result-container');
const downloadLink = document.getElementById('download-link');
const resetBtn = document.getElementById('reset-btn');
const statusText = document.getElementById('status-text');

// Tabs
const tabBtns = document.querySelectorAll('.tab-btn');
const insertSettings = document.getElementById('tool-settings-insert');
const dropTitle = document.getElementById('drop-title');
const dropDesc = document.getElementById('drop-desc');

// Cropper UI
const cropperSettings = document.getElementById('tool-settings-cropper');
const cropperRows = document.getElementById('cropper-rows');
const cropperCols = document.getElementById('cropper-cols');

// Vectorizer UI
const vectorizerSettings = document.getElementById('tool-settings-vectorizer');
const vectorizerPreset = document.getElementById('vectorizer-preset');

// Insert Specific UI
const insertFileZone = document.getElementById('insert-file-zone');
const insertFileInput = document.getElementById('insert-file-input');
const insertFileName = document.getElementById('insert-file-name');
const intervalInput = document.getElementById('interval-input');

// EvenOdd UI
const evenoddSettings = document.getElementById('tool-settings-evenodd');
const evenoddStart = document.getElementById('evenodd-start');
const evenoddEnd = document.getElementById('evenodd-end');
const evenoddType = document.getElementById('evenodd-type');
const stringResultContainer = document.getElementById('string-result-container');
const stringResult = document.getElementById('string-result');
const copyBtn = document.getElementById('copy-btn');
const generateBtn = document.getElementById('evenodd-generate-btn');

// Swatchset UI
const swatchsetSettings   = document.getElementById('tool-settings-swatchset');
const ssRefZone           = document.getElementById('ss-ref-zone');
const ssRefInput          = document.getElementById('ss-ref-input');
const ssRefName           = document.getElementById('ss-ref-name');
const swatchsetGenerateBtn = document.getElementById('swatchset-generate-btn');
const ssGoalRadios        = document.querySelectorAll('input[name="ss-goal-type"]');
const ssGoalRgbInputs     = document.getElementById('ss-goal-rgb-inputs');
const ssGoalHexInputs     = document.getElementById('ss-goal-hex-inputs');
const ssGoalPantoneInputs = document.getElementById('ss-goal-pantone-inputs');

let currentTool = 'duplexer';
let insertFile = null;
let ssRefFile = null;

// Tab Switching
tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        tabBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentTool = btn.dataset.tool;
        updateUIForTool();
        resetUI();
    });
});

function updateUIForTool() {
    insertSettings.classList.add('hidden');
    evenoddSettings.classList.add('hidden');
    cropperSettings.classList.add('hidden');
    vectorizerSettings.classList.add('hidden');
    swatchsetSettings.classList.add('hidden');
    dropZone.classList.remove('hidden');
    stringResultContainer.classList.add('hidden');
    
    // Reset accept attribute
    fileInput.accept = ".pdf";
    
    if (currentTool === 'duplexer') {
        dropTitle.innerText = "Drag & Drop PDF";
        dropDesc.innerText = "Standard Duplexing (Front/Back)";
    } else if (currentTool === 'insertbetween') {
        insertSettings.classList.remove('hidden');
        dropTitle.innerText = "Drag & Drop Main PDF";
        dropDesc.innerText = "Upload the multi-page document here";
    } else if (currentTool === 'cropper') {
        cropperSettings.classList.remove('hidden');
        dropTitle.innerText = "Drag & Drop PDF";
        dropDesc.innerText = "Upload the multi-page document to auto-crop";
    } else if (currentTool === 'vectorizer') {
        vectorizerSettings.classList.remove('hidden');
        dropTitle.innerText = "Drag & Drop Image";
        dropDesc.innerText = "Upload an image (PNG, JPG) to vectorize";
        fileInput.accept = ".png,.jpg,.jpeg";
    } else if (currentTool === 'evenodd') {
        evenoddSettings.classList.remove('hidden');
        dropZone.classList.add('hidden');
    } else if (currentTool === 'swatchset') {
        swatchsetSettings.classList.remove('hidden');
        dropZone.classList.add('hidden');
    }
}

// Handle Insert File
insertFileZone.addEventListener('click', () => insertFileInput.click());
insertFileInput.addEventListener('change', () => {
    if (insertFileInput.files.length > 0) {
        insertFile = insertFileInput.files[0];
        insertFileName.innerText = insertFile.name;
        insertFileZone.classList.add('has-file');
    }
});

insertFileZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    insertFileZone.classList.add('dragging');
});

insertFileZone.addEventListener('dragleave', () => {
    insertFileZone.classList.remove('dragging');
});

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

// Handle Drag & Drop (Main File)
dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragging');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragging');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragging');
    const files = e.dataTransfer.files;
    if (files.length > 0) handleUpload(files[0]);
});

// Handle Click to Upload (Main File)
dropZone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) handleUpload(fileInput.files[0]);
});

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

    // UI Updates
    dropZone.classList.add('hidden');
    insertSettings.classList.add('hidden');
    cropperSettings.classList.add('hidden');
    vectorizerSettings.classList.add('hidden');
    progressContainer.classList.remove('hidden');
    statusText.innerText = `Processing ${file.name}...`;
    
    // Animate progress (simulated for small files)
    let progress = 0;
    const intervalAnim = setInterval(() => {
        if (progress < 90) {
            progress += 5;
            progressFill.style.width = `${progress}%`;
        }
    }, 100);

    // Prepare Form Data based on tool
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
            body: formData
        });

        const data = await response.json();

        clearInterval(intervalAnim);
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

// ── Swatchset: Goal type radio toggle ────────────────────────────────────
ssGoalRadios.forEach(radio => {
    radio.addEventListener('change', () => {
        const val = document.querySelector('input[name="ss-goal-type"]:checked').value;
        ssGoalRgbInputs.classList.toggle('hidden', val !== 'rgb');
        ssGoalHexInputs.classList.toggle('hidden', val !== 'hex');
        ssGoalPantoneInputs.classList.toggle('hidden', val !== 'pantone');
    });
});

// ── Swatchset: Reference image upload ────────────────────────────────────
ssRefZone.addEventListener('click', () => ssRefInput.click());
ssRefInput.addEventListener('change', () => {
    if (ssRefInput.files.length > 0) {
        ssRefFile = ssRefInput.files[0];
        ssRefName.innerText = ssRefFile.name;
        ssRefZone.classList.add('has-file');
    }
});
ssRefZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    ssRefZone.classList.add('dragging');
});
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

// ── Swatchset: Update button label when format changes ────────────────────
document.querySelectorAll('input[name="ss-format"]').forEach(radio => {
    radio.addEventListener('change', () => {
        const fmt = document.querySelector('input[name="ss-format"]:checked').value;
        swatchsetGenerateBtn.textContent = `Generate Swatch Set ${fmt.toUpperCase()}`;
    });
});

// ── Swatchset: Generate button ────────────────────────────────────────────
swatchsetGenerateBtn.addEventListener('click', async () => {
    const goalType = document.querySelector('input[name="ss-goal-type"]:checked').value;

    // Client-side validation
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

    // Build FormData
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

    if (ssRefFile) {
        formData.append('reference_image', ssRefFile);
    }

    // Show progress
    swatchsetSettings.classList.add('hidden');
    progressContainer.classList.remove('hidden');
    statusText.innerText = `Generating Swatch Set ${outputFormat.toUpperCase()}...`;

    let progress = 0;
    const intervalAnim = setInterval(() => {
        if (progress < 90) {
            progress += 10;
            progressFill.style.width = `${progress}%`;
        }
    }, 80);

    try {
        const response = await fetch('/swatchset', { method: 'POST', body: formData });
        const data = await response.json();

        clearInterval(intervalAnim);
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

// Handle EvenOdd Generate Button
generateBtn.addEventListener('click', async () => {
    const formData = new FormData();
    formData.append('start', evenoddStart.value);
    formData.append('end', evenoddEnd.value);
    formData.append('type', evenoddType.value);

    evenoddSettings.classList.add('hidden');
    progressContainer.classList.remove('hidden');
    statusText.innerText = `Generating Numbers...`;

    try {
        const response = await fetch('/evenodd', {
            method: 'POST',
            body: formData
        });

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

// Handle Copy Array
copyBtn.addEventListener('click', () => {
    stringResult.select();
    document.execCommand("copy");
    copyBtn.innerText = "Copied!";
    setTimeout(() => {
        copyBtn.innerText = "Copy to Clipboard";
    }, 2000);
});

function resetUI() {
    resultContainer.classList.add('hidden');
    progressContainer.classList.add('hidden');
    stringResultContainer.classList.add('hidden');
    
    if (currentTool !== 'evenodd' && currentTool !== 'swatchset') {
        dropZone.classList.remove('hidden');
    } else if (currentTool === 'evenodd') {
        evenoddSettings.classList.remove('hidden');
    } else if (currentTool === 'swatchset') {
        swatchsetSettings.classList.remove('hidden');
        ssRefFile = null;
        ssRefName.innerText = '';
        ssRefZone.classList.remove('has-file');
        resetBtn.textContent = 'Process Another';
    }

    fileInput.value = '';
    progressFill.style.width = '0%';
    
    if (currentTool === 'insertbetween') {
        insertSettings.classList.remove('hidden');
    } else if (currentTool === 'cropper') {
        cropperSettings.classList.remove('hidden');
    } else if (currentTool === 'vectorizer') {
        vectorizerSettings.classList.remove('hidden');
    }
}
