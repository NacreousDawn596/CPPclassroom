from flask import Flask, request, jsonify, Response, stream_with_context
import subprocess
import tempfile
import os
import ptyprocess
import select
import time
import json
import threading

app = Flask(__name__)

# Store active processes
# Key: session_id (which we might just use 'default' for single instance per DO)
# But since the DO is unique per session, we can just store one process.
active_process = None
process_lock = threading.Lock()

@app.route('/api/run', methods=['POST'])
def run_code():
    global active_process
    
    data = request.json
    code = data.get('code', '')
    
    if not code:
        return jsonify({'error': 'No code provided'}), 400

    # Create temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False) as cpp_file:
        cpp_file.write(code)
        cpp_path = cpp_file.name

    exe_path = cpp_path.replace('.cpp', '.out')
    
    try:
        # Compile
        compile_process = subprocess.run(
            ['g++', cpp_path, '-o', exe_path, '-std=c++17'],
            capture_output=True,
            text=True,
            timeout=10
        )

        if compile_process.returncode != 0:
            return jsonify({
                'status': 'error',
                'message': 'Compilation failed',
                'output': compile_process.stderr
            }), 400

        # Start process
        with process_lock:
            if active_process and active_process.isalive():
                active_process.terminate(force=True)
            
            active_process = ptyprocess.PtyProcess.spawn([exe_path])

        return jsonify({'status': 'success', 'message': 'Running'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(cpp_path):
            os.remove(cpp_path)

@app.route('/api/input/<session_id>', methods=['POST'])
def handle_input(session_id):
    # In this architecture, the URL routing strips /api usually, 
    # but we'll handle the full path just in case or rely on the Worker to rewrite.
    # The worker rewrites `http://127.0.0.1:8080/api/...` so we keep /api prefix.
    
    global active_process
    data = request.json
    input_text = data.get('input', '')
    
    with process_lock:
        if active_process and active_process.isalive():
            active_process.write(input_text.encode())
            return jsonify({'status': 'sent'})
        else:
            return jsonify({'error': 'Process not running'}), 400

@app.route('/api/output/<session_id>', methods=['GET'])
def stream_output(session_id):
    def generate():
        global active_process
        
        # Wait for process to start if it hasn't yet (simple retry)
        retries = 0
        while not active_process and retries < 10:
            time.sleep(0.1)
            retries += 1
            
        if not active_process:
            yield f"data: {json.dumps({'error': 'No active process'})}\n\n"
            return

        fd = active_process.fd
        
        while True:
            try:
                if not active_process.isalive():
                    yield f"data: {json.dumps({'status': 'finished'})}\n\n"
                    break
                
                r, w, x = select.select([fd], [], [], 0.1)
                
                if fd in r:
                    data = os.read(fd, 1024)
                    if data:
                        yield f"data: {json.dumps({'output': data.decode(errors='replace')})}\n\n"
                
                # Keep connection alive
                # yield f": keepalive\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                break
                
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    # Cloudflare Containers usually expect the app to listen on a specific port (often 8080)
    app.run(host='0.0.0.0', port=8080)
