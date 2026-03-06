const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const progressContainer = document.getElementById('progress-container');
const progressFill = document.getElementById('progress-fill');
const resultContainer = document.getElementById('result-container');
const downloadLink = document.getElementById('download-link');
const resetBtn = document.getElementById('reset-btn');
const statusText = document.getElementById('status-text');

// Handle Drag & Drop
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

// Handle Click to Upload
dropZone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) handleUpload(fileInput.files[0]);
});

async function handleUpload(file) {
    if (!file.name.endsWith('.pdf')) {
        alert('Please select a PDF file.');
        return;
    }

    // UI Updates
    dropZone.classList.add('hidden');
    progressContainer.classList.remove('hidden');
    statusText.innerText = `Processing ${file.name}...`;
    
    // Animate progress (simulated for small files, but logic is real)
    let progress = 0;
    const interval = setInterval(() => {
        if (progress < 90) {
            progress += 5;
            progressFill.style.width = `${progress}%`;
        }
    }, 100);

    // Prepare Form Data
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        clearInterval(interval);
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
        clearInterval(interval);
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
}
