import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, Response, jsonify, redirect, url_for
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
import uuid
import json

from flask_cors import CORS
import google.generativeai as genai
from datetime import datetime, timezone
import difflib

app = Flask(__name__, template_folder="./frontend")
app.config['SECRET_KEY'] = 'secret!'
CORS(app, resources={r"/*": {"origins": ["https://cppclassroom.k-aferiad.workers.dev", "https://backend-snowy-wildflower-8765.fly.dev", "https://cpp.gadzit.lol" ]}})
# Keep SocketIO for legacy/fallback if needed, but we are moving to HTTP/SSE
socketio = SocketIO(app, cors_allowed_origins=["https://cppclassroom.k-aferiad.workers.dev", "https://backend-snowy-wildflower-8765.fly.dev", "https://cpp.gadzit.lol"], async_mode='eventlet')

# Configure Gemini API
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Quota file path
QUOTA_FILE = '/tmp/debug_quota.json'
MAX_DAILY_DEBUGS = 3

def load_quota():
    """Load quota data from file"""
    if os.path.exists(QUOTA_FILE):
        try:
            with open(QUOTA_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_quota(quota_data):
    """Save quota data to file"""
    with open(QUOTA_FILE, 'w') as f:
        json.dump(quota_data, f)

def get_user_quota(session_id):
    """Get remaining quota for user"""
    quota_data = load_quota()
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    if session_id not in quota_data:
        quota_data[session_id] = {'date': today, 'count': 0}
        save_quota(quota_data)  # Save immediately for new users
    
    user_data = quota_data[session_id]
    
    # Reset if new day
    if user_data.get('date') != today:
        user_data = {'date': today, 'count': 0}
        quota_data[session_id] = user_data
        save_quota(quota_data)
    
    return MAX_DAILY_DEBUGS - user_data.get('count', 0)

def increment_quota(session_id):
    """Increment usage count for user"""
    quota_data = load_quota()
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    if session_id not in quota_data:
        quota_data[session_id] = {'date': today, 'count': 0}
    
    user_data = quota_data[session_id]
    if user_data.get('date') != today:
        user_data = {'date': today, 'count': 0}
    
    user_data['count'] = user_data.get('count', 0) + 1
    quota_data[session_id] = user_data
    save_quota(quota_data)

def generate_diff(original, fixed):
    """Generate line-by-line diff information"""
    original_lines = original.splitlines(keepends=True)
    fixed_lines = fixed.splitlines(keepends=True)
    
    diff = list(difflib.unified_diff(original_lines, fixed_lines, lineterm=''))
    
    # Parse diff to extract changes
    changes = []
    for line in diff:
        if line.startswith('+++') or line.startswith('---') or line.startswith('@@'):
            continue
        if line.startswith('+'):
            changes.append({'type': 'add', 'content': line[1:]})
        elif line.startswith('-'):
            changes.append({'type': 'remove', 'content': line[1:]})
        else:
            changes.append({'type': 'context', 'content': line})
    
    return changes

import os
import subprocess

@socketio.on('connect')
def handle_connect():
    print("✅ Client Connected!")

@socketio.on('run_code')
def handle_run_code(data):
    print(f"📝 Received code length: {len(data.get('code', ''))}") # Shows in fly logs

    try:
        code = data.get('code')
        if not code:
            emit('output', "Error: No code received")
            return

        # 1. Write to /tmp (Safe directory in Docker)
        source_file = "/tmp/program.cpp"
        executable = "/tmp/program"
        
        with open(source_file, "w") as f:
            f.write(code)

        # 2. Compile
        # We capture both stdout and stderr to see compilation errors
        compile_process = subprocess.run(
            ["g++", source_file, "-o", executable],
            capture_output=True,
            text=True
        )

        if compile_process.returncode != 0:
            # Send compilation error back to client
            emit('output', f"⚠️ Compilation Error:\n{compile_process.stderr}")
            return

        # 3. Run
        # Set a timeout so infinite loops don't kill your server
        run_process = subprocess.run(
            [executable],
            capture_output=True,
            text=True,
            timeout=5  # 5 second timeout
        )

        # 4. Send Output
        output = run_process.stdout + run_process.stderr
        emit('output', output)
        print("✅ Output sent to client")

    except subprocess.TimeoutExpired:
        emit('output', "⏱️ Error: Execution Timed Out (Limit: 5s)")
    except Exception as e:
        print(f"🔥 Server Error: {e}") # Shows in fly logs
        emit('output', f"🔥 Server Error: {str(e)}")

@app.route('/run_code', methods=['POST'])
def run_code():
    data = request.json
    code = data.get('code', '')
    
    if not code:
        return jsonify({'error': 'No code provided'}), 400

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
            return jsonify({
                'message': 'Compilation failed',
                'stderr': compile_process.stderr
            }), 400

        # Start process
        proc = ptyprocess.PtyProcess.spawn([exe_path])
        session_id = str(uuid.uuid4())
        
        active_processes[session_id] = {
            'proc': proc,
            'cpp_path': cpp_path,
            'exe_path': exe_path,
            'created_at': time.time()
        }
        
        return jsonify({'sessionId': session_id})

    except Exception as e:
        if os.path.exists(cpp_path):
            os.remove(cpp_path)
        return jsonify({'error': str(e)}), 500

@app.route('/', methods=['GET'])
def home():
    return redirect(url_for('https://cpp.gadzit.lol/'))

@app.route('/health', methods=['GET'])
def health():
    return {'status': 'healthy'}

@app.route('/quota/<session_id>', methods=['GET'])
def check_quota(session_id):
    """Check remaining quota for a user"""
    try:
        remaining = get_user_quota(session_id)
        return jsonify({
            'quota': remaining,
            'max': MAX_DAILY_DEBUGS
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/debug', methods=['POST'])
def debug_code():
    """Debug C++ code using Gemini AI"""
    if not GEMINI_API_KEY:
        return jsonify({'error': 'Gemini API not configured'}), 500
    
    data = request.json
    code = data.get('code', '')
    error_msg = data.get('error', '')
    session_id = data.get('sessionId', 'default')
    
    if not code:
        return jsonify({'error': 'No code provided'}), 400
    
    # Check quota
    remaining = get_user_quota(session_id)
    if remaining <= 0:
        return jsonify({
            'error': 'Daily quota exhausted',
            'quota': 0,
            'message': 'You have used all 3 debugs for today. Come back tomorrow!'
        }), 429
    
    try:
        # Prepare prompt for Gemini
        prompt = f"""You are a C++ debugging assistant. Analyze the following code and error, then provide a corrected version.

Original Code:
```cpp
{code}
```

Error Message:
{error_msg if error_msg else 'No specific error provided. Please analyze for potential issues and improvements.'}

Provide:
1. A brief explanation of the issue (max 2 sentences)
2. The complete corrected code

Format your response as:
EXPLANATION: <your explanation>
CORRECTED CODE:
```cpp
<corrected code>
```
"""
        
        # Call Gemini API with retry logic for rate limits
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        max_retries = 3
        retry_delay = 1  # Start with 1 second
        
        for attempt in range(max_retries):
            try:
                response = model.generate_content(prompt)
                break  # Success, exit retry loop
            except Exception as api_error:
                error_str = str(api_error)
                if '429' in error_str and attempt < max_retries - 1:
                    # Rate limit hit, wait and retry
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                elif '429' in error_str:
                    # Still hitting rate limit after retries
                    return jsonify({
                        'error': 'Gemini API rate limit exceeded. Please wait a moment and try again.',
                        'quota': remaining,
                        'message': 'The AI service is temporarily busy. Please try again in a few seconds.'
                    }), 503
                else:
                    # Other API error
                    raise api_error
        
        # Parse response
        response_text = response.text
        
        # Extract explanation and corrected code
        explanation = ''
        corrected_code = code  # fallback to original
        
        if 'EXPLANATION:' in response_text:
            parts = response_text.split('CORRECTED CODE:')
            explanation = parts[0].replace('EXPLANATION:', '').strip()
            if len(parts) > 1:
                # Extract code from markdown code block
                code_part = parts[1]
                if '```cpp' in code_part:
                    code_part = code_part.split('```cpp')[1]
                    if '```' in code_part:
                        corrected_code = code_part.split('```')[0].strip()
                elif '```' in code_part:
                    code_part = code_part.split('```')[1]
                    if '```' in code_part:
                        corrected_code = code_part.split('```')[0].strip()
        
        # Generate diff
        diff = generate_diff(code, corrected_code)
        
        # Increment quota
        increment_quota(session_id)
        remaining = get_user_quota(session_id)
        
        return jsonify({
            'status': 'success',
            'explanation': explanation,
            'correctedCode': corrected_code,
            'diff': diff,
            'quota': remaining
        })
        
    except Exception as e:
        return jsonify({
            'error': f'Debug failed: {str(e)}',
            'quota': remaining
        }), 500

# Store active processes: { sessionId: { 'proc': ptyprocess, 'output_queue': [], 'finished': False } }
active_processes = {}

@app.route('/run', methods=['POST'])
def run_code_http():
    data = request.json
    code = data.get('code', '')
    
    if not code:
        return jsonify({'error': 'No code provided'}), 400

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
            return jsonify({
                'message': 'Compilation failed',
                'stderr': compile_process.stderr
            }), 400

        # Start process
        proc = ptyprocess.PtyProcess.spawn([exe_path])
        session_id = str(uuid.uuid4())
        
        active_processes[session_id] = {
            'proc': proc,
            'cpp_path': cpp_path,
            'exe_path': exe_path,
            'created_at': time.time()
        }
        
        return jsonify({'sessionId': session_id})

    except Exception as e:
        if os.path.exists(cpp_path):
            os.remove(cpp_path)
        return jsonify({'error': str(e)}), 500

@app.route('/output/<session_id>', methods=['GET'])
def get_output(session_id):
    if session_id not in active_processes:
        return jsonify({'error': 'Session not found'}), 404

    def generate():
        session = active_processes[session_id]
        proc = session['proc']
        fd = proc.fd
        
        msg = 'Connected to terminal session...\r\n'
        yield f"data: {json.dumps({'output': msg})}\n\n"

        try:
            # Read any buffered output immediately (for fast programs)
            import fcntl
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            
            # Give the process a moment to produce output
            eventlet.sleep(0.05)
            
            # Try to read any immediate output
            try:
                while True:
                    data = os.read(fd, 1024)
                    if data:
                        output = data.decode(errors='replace')
                        yield f"data: {json.dumps({'output': output})}\n\n"
                    else:
                        break
            except (OSError, BlockingIOError):
                pass  # No more immediate data
            
            # Now enter the normal polling loop
            while True:
                if not proc.isalive():
                    # Process finished, try to read any remaining buffered output
                    try:
                        data = os.read(fd, 1024)
                        if data:
                            output = data.decode(errors='replace')
                            yield f"data: {json.dumps({'output': output})}\n\n"
                    except (OSError, BlockingIOError):
                        pass
                    break
                
                r, w, x = select.select([fd], [], [], 0.1)
                
                if fd in r:
                    try:
                        data = os.read(fd, 1024)
                        if data:
                            output = data.decode(errors='replace')
                            yield f"data: {json.dumps({'output': output})}\n\n"
                    except OSError:
                        break
                
                eventlet.sleep(0.01)
            
            exit_msg = '\r\n\x1b[32mProgram exited.\x1b[0m\r\n'
            yield f"data: {json.dumps({'output': exit_msg, 'status': 'finished'})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            # Cleanup
            cleanup_session(session_id)

    return Response(generate(), mimetype='text/event-stream')

@app.route('/input/<session_id>', methods=['POST'])
def send_input(session_id):
    if session_id not in active_processes:
        return jsonify({'error': 'Session not found'}), 404
        
    data = request.json
    input_text = data.get('input', '')
    
    session = active_processes[session_id]
    proc = session['proc']
    
    if proc.isalive():
        proc.write(input_text.encode())
        return jsonify({'status': 'ok'})
    else:
        return jsonify({'error': 'Process finished'}), 400

def cleanup_session(session_id):
    if session_id in active_processes:
        session = active_processes[session_id]
        proc = session['proc']
        proc.terminate(force=True)
        
        if os.path.exists(session['exe_path']):
            os.remove(session['exe_path'])
        if os.path.exists(session['cpp_path']):
            os.remove(session['cpp_path'])
            
        del active_processes[session_id]

if __name__ == '__main__':
    print("Starting server on port 5550...")
    socketio.run(app, debug=True, host='0.0.0.0', port=5550)