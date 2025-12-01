import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import subprocess
import tempfile
import os
import pty
import select
import struct
import fcntl
import termios
import signal
import threading
import time
import ptyprocess

app = Flask(__name__, template_folder="./frontend")
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

@app.route('/', methods=['GET'])
def home():
    return render_template("index.html")

@app.route('/health', methods=['GET'])
def health():
    return {'status': 'healthy'}

active_processes = {}

@socketio.on('connect')
def handle_connect():
    print(f"Client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    print(f"Client disconnected: {request.sid}")
    sid = request.sid
    if sid in active_processes:
        proc = active_processes[sid]['proc']
        proc.terminate(force=True)
        del active_processes[sid]

@socketio.on('run_code')
def handle_run_code(data):
    print(f"Received run_code request from {request.sid}")
    code = data.get('code', '')
    sid = request.sid
    
    if not code:
        emit('output', 'Error: No code provided\r\n')
        return

    # Create temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False) as cpp_file:
        cpp_file.write(code)
        cpp_path = cpp_file.name

    exe_path = cpp_path.replace('.cpp', '.out')
    print(f"Compiling {cpp_path} to {exe_path}")

    try:
        # Compile
        compile_process = subprocess.run(
            ['g++', cpp_path, '-o', exe_path, '-std=c++17'],
            capture_output=True,
            text=True,
            timeout=10
        )

        if compile_process.returncode != 0:
            print("Compilation failed")
            emit('output', '\x1b[31mCompilation Error:\x1b[0m\r\n')
            emit('output', compile_process.stderr.replace('\n', '\r\n'))
            return

        print("Compilation successful. Starting process...")
        
        # Clean up previous process for this session if any
        if sid in active_processes:
            old_proc = active_processes[sid]['proc']
            old_proc.terminate(force=True)
            
        proc = ptyprocess.PtyProcess.spawn([exe_path])
        
        active_processes[sid] = {'proc': proc}
        
        def read_loop():
            print(f"Started read_loop for {sid}")
            fd = proc.fd
            while True:
                try:
                    if not proc.isalive():
                        break
                    
                    # Use select to wait for data (timeout allows yielding)
                    r, w, x = select.select([fd], [], [], 0.1)
                    
                    if fd in r:
                        data = os.read(fd, 1024)
                        if data:
                            print(f"Read data: {data}")
                            socketio.emit('output', data.decode(errors='replace'), room=sid)
                    
                    socketio.sleep(0) # Explicit yield just in case
                except OSError as e:
                    # Input/output error usually means the process died
                    print(f"OSError in read_loop: {e}")
                    break
                except Exception as e:
                    print(f"Error in read_loop: {e}")
                    break
            
            print(f"Process finished for {sid}")
            socketio.emit('output', '\r\n\x1b[32mProgram exited.\x1b[0m\r\n', room=sid)
            if os.path.exists(exe_path):
                os.remove(exe_path)
            if os.path.exists(cpp_path):
                os.remove(cpp_path)

        socketio.start_background_task(read_loop)

    except Exception as e:
        print(f"Exception in run_code: {e}")
        emit('output', f'\r\nError: {str(e)}\r\n')
        if os.path.exists(cpp_path):
            os.remove(cpp_path)

@socketio.on('input')
def handle_input(data):
    sid = request.sid
    print(f"Received input from {sid}: {repr(data)}")
    if sid in active_processes:
        proc = active_processes[sid]['proc']
        if proc.isalive():
            print(f"Writing to process for {sid}")
            proc.write(data.encode())
            # proc.flush() # ptyprocess write is unbuffered
        else:
            print(f"Process not alive for {sid}")
    else:
        print(f"No active process for {sid}")

if __name__ == '__main__':
    print("Starting server on port 5550...")
    socketio.run(app, debug=True, host='0.0.0.0', port=5550)