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

// Insert Specific UI
const insertFileZone = document.getElementById('insert-file-zone');
const insertFileInput = document.getElementById('insert-file-input');
const insertFileName = document.getElementById('insert-file-name');
const intervalInput = document.getElementById('interval-input');

let currentTool = 'duplexer';
let insertFile = null;

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
    if (currentTool === 'duplexer') {
        insertSettings.classList.add('hidden');
        dropTitle.innerText = "Drag & Drop PDF";
        dropDesc.innerText = "Standard Duplexing (Front/Back)";
    } else if (currentTool === 'insertbetween') {
        insertSettings.classList.remove('hidden');
        dropTitle.innerText = "Drag & Drop Main PDF";
        dropDesc.innerText = "Upload the multi-page document here";
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
    if (!file.name.endsWith('.pdf')) {
        alert('Please select a PDF file.');
        return;
    }

    if (currentTool === 'insertbetween' && !insertFile) {
        alert('Please upload an Insert PDF first!');
        return;
    }

    // UI Updates
    dropZone.classList.add('hidden');
    insertSettings.classList.add('hidden');
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

function resetUI() {
    resultContainer.classList.add('hidden');
    progressContainer.classList.add('hidden');
    dropZone.classList.remove('hidden');
    fileInput.value = '';
    progressFill.style.width = '0%';
    
    if (currentTool === 'insertbetween') {
        insertSettings.classList.remove('hidden');
    }
}
