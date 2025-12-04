const API_URL = 'https://backend-snowy-wildflower-8765.fly.dev';
const STORAGE_KEY = 'cpp_playground_files';

let editor;
let files = [];
let activeFileId = null;
let term;
let fitAddon;
let sessionId = null;
let outputEventSource = null;
let lastError = '';
let userSessionId = localStorage.getItem('userSessionId') || generateId();
let currentQuota = 3;
let suggestedCode = '';

function init() {
    // Initialize xterm.js
    term = new Terminal({
        cursorBlink: true,
        fontSize: 14,
        fontFamily: 'Consolas, Monaco, "Courier New", monospace',
        theme: {
            background: '#1e1e1e',
            foreground: '#cccccc'
        }
    });

    fitAddon = new FitAddon.FitAddon();
    term.loadAddon(fitAddon);
    term.open(document.getElementById('terminal'));
    fitAddon.fit();

    term.onData(data => {
        if (sessionId) {
            sendInput(data);
        }
    });

    window.addEventListener('resize', () => {
        fitAddon.fit();
    });

    // Load files from storage
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
        files = JSON.parse(saved);
    }

    if (files.length === 0) {
        files.push({
            id: generateId(),
            name: 'main.cpp',
            content: `#include <iostream>
using namespace std;

int main() {
    int a, b;
    cout << "Enter two numbers: ";
    cin >> a >> b;
    cout << "Sum: " << (a + b) << endl;
    return 0;
}`
        });
        saveToStorage();
    }

    // Initialize CodeMirror
    editor = CodeMirror.fromTextArea(document.getElementById('editor'), {
        mode: 'text/x-c++src',
        theme: 'monokai',
        lineNumbers: true,
        indentUnit: 4,
        indentWithTabs: false,
        matchBrackets: true,
        autoCloseBrackets: true,
        lineWrapping: false,
        extraKeys: {
            "Ctrl-Enter": runCode,
            "Cmd-Enter": runCode
        }
    });

    editor.on('change', () => {
        if (activeFileId) {
            const file = files.find(f => f.id === activeFileId);
            if (file) {
                file.content = editor.getValue();
                saveToStorage();
            }
        }
    });

    activeFileId = files[0].id;
    renderFiles();
    renderTabs();
    loadActiveFile();

    // Event Listeners
    document.getElementById('newFileBtn').addEventListener('click', openNewFileModal);
    document.getElementById('runBtn').addEventListener('click', runCode);
    document.getElementById('clearOutputBtn').addEventListener('click', clearOutput);
    document.getElementById('cancelBtn').addEventListener('click', closeNewFileModal);
    document.getElementById('createBtn').addEventListener('click', createNewFile);
    document.getElementById('fileNameInput').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') createNewFile();
    });
    document.getElementById('debugBtn').addEventListener('click', debugCode);
    document.getElementById('closeDiffBtn').addEventListener('click', closeDiffModal);
    document.getElementById('rejectBtn').addEventListener('click', closeDiffModal);
    document.getElementById('acceptBtn').addEventListener('click', acceptSuggestion);

    // Save user session ID
    localStorage.setItem('userSessionId', userSessionId);

    // Fetch and update quota display
    fetchQuota();
}

function generateId() {
    return Date.now().toString(36) + Math.random().toString(36).substr(2);
}

function saveToStorage() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(files));
}

function renderFiles() {
    const fileList = document.getElementById('fileList');
    fileList.innerHTML = files.map(file => `
        <div class="file-item ${file.id === activeFileId ? 'active' : ''}" data-id="${file.id}">
            <svg class="file-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>
                <polyline points="13 2 13 9 20 9"/>
            </svg>
            <span class="file-name">${file.name}</span>
            ${files.length > 1 ? `<button class="file-delete" data-id="${file.id}">×</button>` : ''}
        </div>
    `).join('');

    fileList.querySelectorAll('.file-item').forEach(item => {
        item.addEventListener('click', (e) => {
            if (!e.target.classList.contains('file-delete')) {
                switchToFile(item.dataset.id);
            }
        });
    });

    fileList.querySelectorAll('.file-delete').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteFile(btn.dataset.id);
        });
    });
}

function renderTabs() {
    const tabsBar = document.getElementById('tabsBar');
    tabsBar.innerHTML = files.map(file => `
        <div class="tab ${file.id === activeFileId ? 'active' : ''}" data-id="${file.id}">
            <span class="tab-name">${file.name}</span>
            ${files.length > 1 ? `<button class="tab-close" data-id="${file.id}">×</button>` : ''}
        </div>
    `).join('');

    tabsBar.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', (e) => {
            if (!e.target.classList.contains('tab-close')) {
                switchToFile(tab.dataset.id);
            }
        });
    });

    tabsBar.querySelectorAll('.tab-close').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteFile(btn.dataset.id);
        });
    });
}

function switchToFile(fileId) {
    activeFileId = fileId;
    renderFiles();
    renderTabs();
    loadActiveFile();
}

function loadActiveFile() {
    const file = files.find(f => f.id === activeFileId);
    if (file) {
        editor.setValue(file.content);
    }
}

function deleteFile(fileId) {
    if (files.length === 1) {
        alert('Cannot delete the last file!');
        return;
    }

    const index = files.findIndex(f => f.id === fileId);
    files.splice(index, 1);

    if (activeFileId === fileId) {
        activeFileId = files[0].id;
        loadActiveFile();
    }

    saveToStorage();
    renderFiles();
    renderTabs();
}

function openNewFileModal() {
    document.getElementById('newFileModal').classList.add('active');
    document.getElementById('fileNameInput').value = '';
    document.getElementById('fileNameInput').focus();
}

function closeNewFileModal() {
    document.getElementById('newFileModal').classList.remove('active');
}

function createNewFile() {
    const input = document.getElementById('fileNameInput');
    const fileName = input.value.trim();

    if (!fileName) {
        alert('Please enter a file name!');
        return;
    }

    if (files.some(f => f.name === fileName)) {
        alert('A file with this name already exists!');
        return;
    }

    const newFile = {
        id: generateId(),
        name: fileName,
        content: `#include <iostream>
using namespace std;

int main() {
    // Write your code here
    return 0;
}`
    };

    files.push(newFile);
    activeFileId = newFile.id;
    saveToStorage();
    renderFiles();
    renderTabs();
    loadActiveFile();
    closeNewFileModal();
}

async function runCode() {
    const code = editor.getValue();

    if (!code.trim()) {
        term.write('\r\n\x1b[31mError: Please write some code first!\x1b[0m\r\n');
        return;
    }

    term.reset();
    term.write('Compiling and executing...\r\n');

    // Close existing session if any
    if (outputEventSource) {
        outputEventSource.close();
        outputEventSource = null;
    }

    try {
        const response = await fetch(`${API_URL}/run`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ code: code })
        });

        if (!response.ok) {
            const error = await response.json();
            // Display stderr if available, otherwise show the generic message
            const errorOutput = error.stderr || error.output || error.message || 'Failed to start execution';
            term.write(`\r\n\x1b[31mError: ${error.message}\x1b[0m\r\n`);
            if (error.stderr || error.output) {
                term.write(`\x1b[31m${errorOutput}\x1b[0m\r\n`);
                lastError = errorOutput; // Store for AI debugging
            }
            return;
        }

        const data = await response.json();
        sessionId = data.sessionId;

        // Start listening for output via SSE
        startOutputListener(sessionId);

    } catch (err) {
        term.write(`\r\n\x1b[31mConnection Error: ${err.message}\x1b[0m\r\n`);
        lastError = err.message;
    }
}

function startOutputListener(sid) {
    outputEventSource = new EventSource(`${API_URL}/output/${sid}`);

    outputEventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.output) {
                term.write(data.output);
            }
            if (data.status === 'finished') {
                outputEventSource.close();
                outputEventSource = null;
                sessionId = null;
            }
        } catch (e) {
            console.error('Error parsing SSE data:', e);
        }
    };

    outputEventSource.onerror = (err) => {
        console.error('SSE Error:', err);
        outputEventSource.close();
        outputEventSource = null;
        sessionId = null;
    };
}

async function sendInput(data) {
    if (!sessionId) return;

    try {
        await fetch(`${API_URL}/input/${sessionId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ input: data })
        });
    } catch (err) {
        console.error('Error sending input:', err);
    }
}

function clearOutput() {
    term.reset();
}

// AI Debug Functions
function updateQuotaDisplay() {
    const quotaBadge = document.getElementById('quotaBadge');
    const debugBtn = document.getElementById('debugBtn');

    // Safety check - elements might not exist if HTML isn't updated
    if (!quotaBadge || !debugBtn) {
        console.warn('Debug UI elements not found - make sure frontend is deployed with latest HTML');
        return;
    }

    quotaBadge.textContent = `${currentQuota}/3`;

    if (currentQuota <= 0) {
        debugBtn.disabled = true;
        debugBtn.title = 'Daily quota exhausted. Come back tomorrow!';
    } else {
        debugBtn.disabled = false;
        debugBtn.title = 'Debug with AI (Gemini)';
    }
}

async function fetchQuota() {
    try {
        const response = await fetch(`${API_URL}/quota/${userSessionId}`);
        if (response.ok) {
            const data = await response.json();
            currentQuota = data.quota;
            updateQuotaDisplay();
        } else {
            // If quota fetch fails, keep default
            updateQuotaDisplay();
        }
    } catch (err) {
        console.error('Error fetching quota:', err);
        // Keep default quota on error
        updateQuotaDisplay();
    }
}

async function debugCode() {
    const code = editor.getValue();

    if (!code.trim()) {
        alert('Please write some code first!');
        return;
    }

    if (currentQuota <= 0) {
        alert('You have used all 3 debugs for today. Come back tomorrow!');
        return;
    }

    // Show loading state
    const debugBtn = document.getElementById('debugBtn');
    const originalText = debugBtn.innerHTML;
    debugBtn.disabled = true;
    debugBtn.innerHTML = '<span class="spinner"></span> Analyzing...';

    try {
        const response = await fetch(`${API_URL}/debug`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                code: code,
                error: lastError,
                sessionId: userSessionId
            })
        });

        const data = await response.json();

        if (!response.ok) {
            if (response.status === 429) {
                alert(data.message || 'Daily quota exhausted!');
                currentQuota = 0;
                updateQuotaDisplay();
            } else {
                alert(`Debug failed: ${data.error || 'Unknown error'}`);
            }
            return;
        }

        // Update quota
        currentQuota = data.quota;
        updateQuotaDisplay();

        // Store suggested code
        suggestedCode = data.correctedCode;

        // Display diff
        displayDiff(code, data.correctedCode, data.explanation, data.diff);

    } catch (err) {
        alert(`Connection error: ${err.message}`);
    } finally {
        debugBtn.disabled = false;
        debugBtn.innerHTML = originalText;
    }
}

function displayDiff(original, suggested, explanation, diffData) {
    // Set explanation
    document.getElementById('diffExplanation').textContent = explanation || 'AI has analyzed your code and suggests the following changes:';

    // Display original code
    const originalCodeEl = document.getElementById('originalCode');
    originalCodeEl.innerHTML = '';
    original.split('\n').forEach(line => {
        const span = document.createElement('span');
        span.className = 'diff-line-context';
        span.textContent = line + '\n';
        originalCodeEl.appendChild(span);
    });

    // Display suggested code with highlighting
    const suggestedCodeEl = document.getElementById('suggestedCode');
    suggestedCodeEl.innerHTML = '';

    // Create a simple diff highlighting
    const originalLines = original.split('\n');
    const suggestedLines = suggested.split('\n');

    suggestedLines.forEach((line, index) => {
        const span = document.createElement('span');

        if (index >= originalLines.length || originalLines[index] !== line) {
            // Line is different (added or modified)
            if (index < originalLines.length) {
                // Modified line - show as change
                span.className = 'diff-line-add';
            } else {
                // New line
                span.className = 'diff-line-add';
            }
        } else {
            // Line unchanged
            span.className = 'diff-line-context';
        }

        span.textContent = line + '\n';
        suggestedCodeEl.appendChild(span);
    });

    // Show removed lines in original
    if (originalLines.length > suggestedLines.length) {
        for (let i = suggestedLines.length; i < originalLines.length; i++) {
            const span = document.createElement('span');
            span.className = 'diff-line-remove';
            span.textContent = originalLines[i] + '\n';
            originalCodeEl.appendChild(span);
        }
    }

    // Show modal
    document.getElementById('diffModal').classList.add('active');
}

function closeDiffModal() {
    document.getElementById('diffModal').classList.remove('active');
}

function acceptSuggestion() {
    if (suggestedCode) {
        editor.setValue(suggestedCode);
        const file = files.find(f => f.id === activeFileId);
        if (file) {
            file.content = suggestedCode;
            saveToStorage();
        }
    }
    closeDiffModal();
    term.write('\r\n\x1b[32mAI suggestions applied successfully!\x1b[0m\r\n');
}

// Start the app
init();
