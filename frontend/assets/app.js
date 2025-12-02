const API_URL = 'https://backend-snowy-wildflower-8765.fly.dev';
const STORAGE_KEY = 'cpp_playground_files';

let editor;
let files = [];
let activeFileId = null;
let term;
let fitAddon;
let sessionId = null;
let outputEventSource = null;

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
            term.write(`\r\n\x1b[31mError: ${error.message || 'Failed to start execution'}\x1b[0m\r\n`);
            return;
        }

        const data = await response.json();
        sessionId = data.sessionId;

        // Start listening for output via SSE
        startOutputListener(sessionId);

    } catch (err) {
        term.write(`\r\n\x1b[31mConnection Error: ${err.message}\x1b[0m\r\n`);
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

// Start the app
init();
