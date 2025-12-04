from flask import Flask, request, jsonify, Response, stream_with_context
import subprocess
import tempfile
import os
import ptyprocess
import select
import time
import json
import threading
import google.generativeai as genai
from datetime import datetime, timezone
import difflib

app = Flask(__name__)

# Store active processes
# Key: session_id (which we might just use 'default' for single instance per DO)
# But since the DO is unique per session, we can just store one process.
active_process = None
process_lock = threading.Lock()

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
                'output': compile_process.stderr,
                'stderr': compile_process.stderr
            }), 400

        # Start process
        with process_lock:
            if active_process and active_process.isalive():
                active_process.terminate(force=True)
            
            active_process = ptyprocess.PtyProcess.spawn([exe_path])

        return jsonify({'status': 'success', 'message': 'Running'})

    except Exception as e:
        return jsonify({
            'error': str(e),
            'stderr': str(e)
        }), 500
    finally:
        if os.path.exists(cpp_path):
            os.remove(cpp_path)

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
        model = genai.GenerativeModel('gemini-pro')
        
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
