
#!/usr/bin/env python3
"""
🌐 Minimal Flask Web UI for StockX Tools
Run any script from the web interface
"""

from flask import Flask, render_template_string, request, jsonify, redirect, url_for
import subprocess
import threading
import os
import sys
import json
import requests
import secrets
import webbrowser
from urllib.parse import urlencode, parse_qs
from datetime import datetime

app = Flask(__name__)

# Store running processes and their outputs
running_processes = {}
process_outputs = {}

# StockX OAuth configuration
STOCKX_API_KEY = 'GH4A9FkG7E3uaWswtc87U7kw8A4quRsU6ciFtrUp'
STOCKX_CLIENT_ID = 'QyK8U0Xir3L3wQjYtBlLuXpMOLANa5EL'
STOCKX_CLIENT_SECRET = 'uqJXWo1oN10iU6qyAiTIap1B0NmuZMsZn6vGp7oO1uK-Ng4-aoSTbRHA5kfNV3Mn'
TOKEN_FILE = 'tokens_full_scope.json'

# Global auth state
auth_state = {
    'authenticated': False,
    'auth_in_progress': False,
    'auth_code': None,
    'auth_error': None
}

def get_replit_url():
    """Get the Replit app URL for OAuth callback"""
    replit_url = os.getenv('REPLIT_URL')
    if replit_url:
        return replit_url.rstrip('/')
    return 'http://localhost:5000'

def is_token_valid():
    """Check if current access token is still valid"""
    try:
        with open(TOKEN_FILE, 'r') as f:
            tokens = json.load(f)
        
        headers = {
            'Authorization': f'Bearer {tokens["access_token"]}',
            'x-api-key': STOCKX_API_KEY
        }
        
        response = requests.get(
            'https://api.stockx.com/v2/catalog/search?query=test&pageSize=1',
            headers=headers,
            timeout=10
        )
        
        return response.status_code == 200
    except Exception:
        return False

def can_refresh_token():
    """Check if we have a valid refresh token"""
    try:
        with open(TOKEN_FILE, 'r') as f:
            tokens = json.load(f)
        return 'refresh_token' in tokens
    except Exception:
        return False

def refresh_access_token():
    """Refresh the access token using refresh token"""
    try:
        with open(TOKEN_FILE, 'r') as f:
            tokens = json.load(f)
        
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': tokens['refresh_token'],
            'client_id': STOCKX_CLIENT_ID,
            'client_secret': STOCKX_CLIENT_SECRET,
            'audience': 'gateway.stockx.com'
        }
        
        response = requests.post(
            'https://accounts.stockx.com/oauth/token',
            data=data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        
        if response.status_code == 200:
            new_tokens = response.json()
            
            # Preserve refresh token if not provided in response
            if 'refresh_token' not in new_tokens and 'refresh_token' in tokens:
                new_tokens['refresh_token'] = tokens['refresh_token']
            
            with open(TOKEN_FILE, 'w') as f:
                json.dump(new_tokens, f, indent=2)
            
            return True
        else:
            return False
    except Exception:
        return False

def exchange_code_for_tokens(auth_code):
    """Exchange authorization code for access tokens"""
    redirect_uri = f"{get_replit_url()}/auth/callback"
    
    data = {
        'grant_type': 'authorization_code',
        'code': auth_code,
        'redirect_uri': redirect_uri,
        'client_id': STOCKX_CLIENT_ID,
        'client_secret': STOCKX_CLIENT_SECRET,
        'audience': 'gateway.stockx.com'
    }
    
    response = requests.post(
        'https://accounts.stockx.com/oauth/token',
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )
    
    if response.status_code == 200:
        tokens = response.json()
        
        with open(TOKEN_FILE, 'w') as f:
            json.dump(tokens, f, indent=2)
        
        return True
    else:
        return False

def ensure_authentication():
    """Ensure we have valid authentication"""
    global auth_state
    
    # Check if current token is valid
    if is_token_valid():
        auth_state['authenticated'] = True
        return True
    
    # Try to refresh token
    if can_refresh_token():
        if refresh_access_token():
            auth_state['authenticated'] = True
            return True
    
    # Need full authentication
    auth_state['authenticated'] = False
    return False

def run_script_async(script_id, command, working_dir=None):
    """Run script asynchronously and capture output"""
    try:
        # Save current directory
        original_dir = os.getcwd()
        
        # Change to working directory if specified
        if working_dir and os.path.exists(working_dir):
            os.chdir(working_dir)
        
        # Initialize output tracking
        if script_id not in process_outputs:
            process_outputs[script_id] = []
        
        process_outputs[script_id].append(f"🚀 Executing: {command}")
        process_outputs[script_id].append(f"📁 Working directory: {os.getcwd()}")
        process_outputs[script_id].append("=" * 50)
        
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        running_processes[script_id] = process
        
        # Read output line by line
        for line in iter(process.stdout.readline, ''):
            if line:
                process_outputs[script_id].append(line.rstrip())
        
        # Wait for process to complete
        process.wait()
        
        # Add completion message
        if process.returncode == 0:
            process_outputs[script_id].append("=" * 50)
            process_outputs[script_id].append(f"✅ Script completed successfully (exit code: {process.returncode})")
        else:
            process_outputs[script_id].append("=" * 50)
            process_outputs[script_id].append(f"❌ Script failed (exit code: {process.returncode})")
        
        # Remove from running processes
        if script_id in running_processes:
            del running_processes[script_id]
        
        # Restore original directory
        os.chdir(original_dir)
            
    except Exception as e:
        if script_id not in process_outputs:
            process_outputs[script_id] = []
        process_outputs[script_id].append(f"❌ Error running script: {str(e)}")
        if script_id in running_processes:
            del running_processes[script_id]
        # Restore original directory
        try:
            os.chdir(original_dir)
        except:
            pass

# HTML template for the web interface
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>StockX Tools - Web Interface</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body>
    <h1>🤖 StockX Tools - Web Interface</h1>
    <p>Run any script from your StockX project</p>
    <hr>
    
    <h2>🔐 Authentication Status</h2>
    {% if authenticated %}
        <p style="color: green;">✅ <strong>Authenticated</strong> - StockX API is ready to use</p>
    {% elif auth_in_progress %}
        <p style="color: orange;">⏳ <strong>Authentication in progress...</strong></p>
        <p>Please complete the authentication in the browser window that opened.</p>
    {% elif auth_error %}
        <p style="color: red;">❌ <strong>Authentication Error:</strong> {{ auth_error }}</p>
        <p><a href="/auth/start" style="padding: 5px 10px; background: #007cba; color: white; text-decoration: none;">Try Authentication Again</a></p>
    {% else %}
        <p style="color: orange;">⚠️ <strong>Not Authenticated</strong></p>
        <p><a href="/auth/start" style="padding: 5px 10px; background: #007cba; color: white; text-decoration: none;">Start Authentication</a></p>
    {% endif %}
    <hr>
    
    <h2>📊 Available Scripts</h2>
    
    <h3>📝 Examples & Testing</h3>
    <form action="/run" method="post" style="margin: 10px 0;">
        <input type="hidden" name="script" value="examples">
        <input type="submit" value="Run Examples" style="padding: 5px 10px;">
        <p>Test API with example searches</p>
    </form>
    
    <h3>💰 eBay Tools</h3>
    <form action="/run" method="post" style="margin: 10px 0;">
        <input type="hidden" name="script" value="ebay">
        <label for="ebay_file">CSV File (in ebay_tools/ directory):</label><br>
        <input type="text" name="file" id="ebay_file" placeholder="example.csv" style="width: 300px; margin: 5px 0;"><br>
        <input type="submit" value="Run eBay Price Analysis" style="padding: 5px 10px;">
        <p>Compare eBay auction data with StockX prices</p>
    </form>
    
    <h3>📊 Inventory Analysis</h3>
    <form action="/run" method="post" style="margin: 10px 0;">
        <input type="hidden" name="script" value="inventory">
        <label for="inventory_file">CSV File (in pricing_tools/ directory):</label><br>
        <input type="text" name="file" id="inventory_file" placeholder="inventory.csv" style="width: 300px; margin: 5px 0;"><br>
        <input type="submit" value="Run Inventory Analysis" style="padding: 5px 10px;">
        <p>Analyze inventory CSV against StockX market data</p>
    </form>
    
    <hr>
    
    <h2>🔄 Running Processes</h2>
    {% if running_processes %}
        {% for script_id in running_processes %}
            <p>⏳ {{ script_id }} is running...</p>
        {% endfor %}
    {% else %}
        <p>No scripts currently running</p>
    {% endif %}
    
    <h2>📋 Recent Outputs</h2>
    <form action="/clear" method="post" style="margin: 10px 0;">
        <input type="submit" value="Clear All Outputs" style="padding: 5px 10px;">
    </form>
    
    {% for script_id, output in outputs %}
        <h3>{{ script_id }} - {{ output.timestamp }}</h3>
        <pre style="background: #f5f5f5; padding: 10px; border: 1px solid #ddd; white-space: pre-wrap; max-height: 400px; overflow-y: auto;">{{ output.content }}</pre>
        <hr>
    {% endfor %}
    
    {% if not outputs %}
        <p>No script outputs yet</p>
    {% endif %}
    
    <script>
        // Manual refresh only - no auto-refresh
    </script>
</body>
</html>
"""

@app.route('/auth/callback')
def auth_callback():
    """Handle OAuth callback from StockX"""
    global auth_state
    
    # Get authorization code from query parameters
    auth_code = request.args.get('code')
    error = request.args.get('error')
    
    if error:
        auth_state['auth_error'] = error
        auth_state['auth_in_progress'] = False
        return render_template_string("""
        <html>
        <head><title>Authentication Error</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1 style="color: red;">❌ Authentication Error</h1>
            <p>Error: {{ error }}</p>
            <p><a href="/">Return to main page</a></p>
        </body>
        </html>
        """, error=error)
    
    if auth_code:
        # Exchange code for tokens
        if exchange_code_for_tokens(auth_code):
            auth_state['authenticated'] = True
            auth_state['auth_in_progress'] = False
            auth_state['auth_code'] = auth_code
            
            return render_template_string("""
            <html>
            <head><title>Authentication Success</title></head>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1 style="color: green;">✅ Authentication Successful!</h1>
                <p>StockX API is now ready to use.</p>
                <p><a href="/">Return to main page</a></p>
                <script>
                    // Auto-redirect after 3 seconds
                    setTimeout(function() {
                        window.location.href = '/';
                    }, 3000);
                </script>
            </body>
            </html>
            """)
        else:
            auth_state['auth_error'] = 'Token exchange failed'
            auth_state['auth_in_progress'] = False
            
            return render_template_string("""
            <html>
            <head><title>Authentication Error</title></head>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1 style="color: red;">❌ Authentication Error</h1>
                <p>Failed to exchange authorization code for tokens.</p>
                <p><a href="/">Return to main page</a></p>
            </body>
            </html>
            """)
    
    return redirect(url_for('index'))

@app.route('/auth/start')
def start_auth():
    """Start OAuth authentication flow"""
    global auth_state
    
    redirect_uri = f"{get_replit_url()}/auth/callback"
    state = secrets.token_urlsafe(32)
    scope = 'openid offline_access read:catalog read:products read:market'
    
    auth_params = {
        'client_id': STOCKX_CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': redirect_uri,
        'state': state,
        'scope': scope,
        'audience': 'gateway.stockx.com'
    }
    
    auth_url = f"https://accounts.stockx.com/authorize?{urlencode(auth_params)}"
    auth_state['auth_in_progress'] = True
    
    return redirect(auth_url)

@app.route('/')
def index():
    """Main page with script options"""
    global auth_state
    
    # Check authentication status
    auth_status = ensure_authentication()
    
    # Prepare outputs for display
    outputs = []
    for script_id, lines in process_outputs.items():
        if lines:
            outputs.append({
                'script_id': script_id,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'content': '\n'.join(lines[-100:])  # Last 100 lines
            })
    
    # Sort by most recent first
    outputs = [(item['script_id'], item) for item in outputs]
    outputs.reverse()
    
    return render_template_string(
        HTML_TEMPLATE,
        running_processes=running_processes.keys(),
        outputs=outputs,
        authenticated=auth_status,
        auth_in_progress=auth_state.get('auth_in_progress', False),
        auth_error=auth_state.get('auth_error', None)
    )

@app.route('/run', methods=['POST'])
def run_script():
    """Run selected script"""
    script = request.form.get('script')
    file_param = request.form.get('file', '').strip()
    
    if not script:
        return redirect(url_for('index'))
    
    # Generate script ID with timestamp
    script_id = f"{script}_{datetime.now().strftime('%H%M%S')}"
    
    # Define script commands
    if script == 'examples':
        command = 'python3 example.py'
        working_dir = None
        
    elif script == 'ebay':
        if not file_param:
            process_outputs[script_id] = ['❌ Error: Please specify a CSV file']
            return redirect(url_for('index'))
        command = f'python3 ebay_stockxpricing.py "{file_param}"'
        working_dir = 'ebay_tools'
        
    elif script == 'inventory':
        if not file_param:
            process_outputs[script_id] = ['❌ Error: Please specify a CSV file']
            return redirect(url_for('index'))
        command = f'python3 inventory_stockx_analyzer.py "{file_param}"'
        working_dir = 'pricing_tools'
        
    else:
        process_outputs[script_id] = ['❌ Error: Unknown script']
        return redirect(url_for('index'))
    
    # Start script in background thread
    thread = threading.Thread(
        target=run_script_async,
        args=(script_id, command, working_dir)
    )
    thread.daemon = True
    thread.start()
    
    return redirect(url_for('index'))

@app.route('/clear', methods=['POST'])
def clear_outputs():
    """Clear all process outputs"""
    global process_outputs
    process_outputs = {}
    return redirect(url_for('index'))

@app.route('/status')
def status():
    """API endpoint for status (JSON)"""
    return jsonify({
        'running_processes': list(running_processes.keys()),
        'completed_processes': list(process_outputs.keys())
    })

if __name__ == '__main__':
    print("🌐 Starting StockX Tools Web Interface...")
    print("📱 Access at: http://0.0.0.0:5000")
    print("🔄 Refresh manually to see updates")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=5000, debug=False)
