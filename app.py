
#!/usr/bin/env python3
"""
🌐 Minimal Flask Web UI for StockX Tools
Run any script from the web interface
"""

from flask import Flask, render_template_string, request, jsonify, redirect, url_for, flash, send_from_directory
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
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
import signal
import psutil
import time

app = Flask(__name__)
app.secret_key = 'stockx_tools_secret_key_2025'

# Initialize SocketIO with production-ready configuration
try:
    # Try with eventlet for production deployment
    socketio = SocketIO(
        app, 
        cors_allowed_origins="*",
        async_mode='eventlet',
        logger=True,
        engineio_logger=True
    )
except Exception as e:
    print(f"⚠️ Could not initialize with eventlet, falling back to threading: {e}")
    # Fallback to threading mode
    socketio = SocketIO(
        app, 
        cors_allowed_origins="*",
        async_mode='threading',
        logger=False,
        engineio_logger=False
    )

# File upload configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Store running processes and their outputs
running_processes = {}  # process_id -> process object
process_outputs = {}    # process_id -> output lines
process_pids = {}       # process_id -> PID for cleanup

# Token refresh thread
token_refresh_thread = None
token_refresh_active = False

# Create upload directory if it doesn't exist
import os
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# StockX OAuth configuration
STOCKX_API_KEY = 'GH4A9FkG7E3uaWswtc87U7kw8A4quRsU6ciFtrUp'
STOCKX_CLIENT_ID = 'QyK8U0Xir3L3wQjYtBlLuXpMOLANa5EL'
STOCKX_CLIENT_SECRET = 'uqJXWo1oN10iU6qyAiTIap1B0NmuZMsZn6vGp7oO1uK-Ng4-aoSTbRHA5kfNV3Mn'
TOKEN_FILE = os.path.join(os.getcwd(), 'tokens_full_scope.json')

# Global auth state
auth_state = {
    'authenticated': False,
    'auth_in_progress': False,
    'auth_code': None,
    'auth_error': None,
    'token_info': None
}

def get_replit_url():
    """Get the Replit app URL for OAuth callback"""
    # Try to get from environment variables
    replit_domain = os.getenv('REPLIT_DEV_DOMAIN')
    if replit_domain:
        return f'https://{replit_domain}'
    
    # Try other Replit environment variables
    replit_slug = os.getenv('REPL_SLUG')
    replit_owner = os.getenv('REPL_OWNER')
    if replit_slug and replit_owner:
        return f'https://{replit_slug}.{replit_owner}.repl.co'
    
    # Check if we're in a deployed Replit environment
    if os.getenv('REPLIT_DEPLOYMENT'):
        return f'https://{os.getenv("REPL_ID", "unknown")}.replit.app'
    
    # Fallback for local development  
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
            
            print(f"✅ Token refreshed successfully at {datetime.now()}")
            return True
        else:
            print(f"❌ Token refresh failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error refreshing token: {str(e)}")
        return False

def auto_refresh_token():
    """Automatically refresh tokens every 11 hours"""
    global token_refresh_active
    token_refresh_active = True
    
    # Initial delay of 30 seconds to let the app start
    time.sleep(30)
    
    while token_refresh_active:
        # Sleep for 11 hours (39600 seconds) - refresh before 12 hour expiry
        time.sleep(39600)
        
        if token_refresh_active:
            success = refresh_access_token()
            if not success:
                print("❌ Failed to refresh token automatically")
                # Try again in 1 hour if failed
                time.sleep(3600)

def start_token_refresh_thread():
    """Start the automatic token refresh thread"""
    global token_refresh_thread
    if token_refresh_thread is None or not token_refresh_thread.is_alive():
        token_refresh_thread = threading.Thread(target=auto_refresh_token, daemon=True)
        token_refresh_thread.start()
        print("🔄 Started automatic token refresh thread")

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

def allowed_file(filename):
    """Check if file has allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def check_real_authentication():
    """Check REAL authentication status with actual API call"""
    global auth_state
    
    try:
        # First check if token file exists
        if not os.path.exists(TOKEN_FILE):
            auth_state['authenticated'] = False
            auth_state['auth_error'] = 'No token file found - authentication required'
            auth_state['token_info'] = None
            return False
        
        # Load and validate token
        with open(TOKEN_FILE, 'r') as f:
            tokens = json.load(f)
        
        if 'access_token' not in tokens:
            auth_state['authenticated'] = False
            auth_state['auth_error'] = 'Invalid token file - no access token'
            auth_state['token_info'] = None
            return False
        
        # Store token info for display
        auth_state['token_info'] = {
            'access_token': tokens['access_token'][:50] + '...',  # Truncate for display
            'has_refresh_token': 'refresh_token' in tokens,
            'token_type': tokens.get('token_type', 'Bearer'),
            'expires_in': tokens.get('expires_in', 'Unknown')
        }
        
        # Make REAL API call to verify authentication
        headers = {
            'Authorization': f'Bearer {tokens["access_token"]}',
            'x-api-key': STOCKX_API_KEY
        }
        
        response = requests.get(
            'https://api.stockx.com/v2/catalog/search?query=nike&pageSize=1',
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if 'products' in data:
                auth_state['authenticated'] = True
                auth_state['auth_error'] = None
                return True
            else:
                auth_state['authenticated'] = False
                auth_state['auth_error'] = 'API returned empty data - token may be invalid'
                return False
        else:
            auth_state['authenticated'] = False
            auth_state['auth_error'] = f'API authentication failed - HTTP {response.status_code}'
            return False
            
    except requests.exceptions.RequestException as e:
        auth_state['authenticated'] = False
        auth_state['auth_error'] = f'Network error during authentication check: {str(e)}'
        return False
    except Exception as e:
        auth_state['authenticated'] = False
        auth_state['auth_error'] = f'Authentication check failed: {str(e)}'
        print(f"⚠️ Authentication check failed: {e}")
        return False

def run_script_async(script_id, command, working_dir=None):
    """Run script asynchronously and capture output with WebSocket streaming"""
    try:
        # Save current directory
        original_dir = os.getcwd()
        
        # Change to working directory if specified
        if working_dir and os.path.exists(working_dir):
            os.chdir(working_dir)
        
        # Initialize output tracking
        if script_id not in process_outputs:
            process_outputs[script_id] = []
        
        initial_msg = f"🚀 Executing: {command}"
        working_dir_msg = f"📁 Working directory: {os.getcwd()}"
        separator = "=" * 50
        
        process_outputs[script_id].append(initial_msg)
        process_outputs[script_id].append(working_dir_msg)
        process_outputs[script_id].append(separator)
        
        # Emit initial messages via WebSocket
        socketio.emit('process_output', {
            'script_id': script_id,
            'line': initial_msg,
            'status': 'running'
        })
        socketio.emit('process_output', {
            'script_id': script_id,
            'line': working_dir_msg,
            'status': 'running'
        })
        socketio.emit('process_output', {
            'script_id': script_id,
            'line': separator,
            'status': 'running'
        })
        
        # Use unbuffered output and set PYTHONUNBUFFERED for real-time progress
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=0,  # Unbuffered
            env=env
        )
        
        running_processes[script_id] = process
        process_pids[script_id] = process.pid
        
        # Update running processes status via WebSocket
        socketio.emit('process_status', {
            'running_processes': list(running_processes.keys()),
            'process_count': len(running_processes)
        })
        
        # Read output line by line and stream via WebSocket
        for line in iter(process.stdout.readline, ''):
            if line:
                output_line = line.rstrip()
                process_outputs[script_id].append(output_line)
                
                # Emit line via WebSocket
                socketio.emit('process_output', {
                    'script_id': script_id,
                    'line': output_line,
                    'status': 'running'
                })
        
        # Wait for process to complete
        process.wait()
        
        # Add completion message
        if process.returncode == 0:
            completion_msg = f"✅ Script completed successfully (exit code: {process.returncode})"
            status = 'completed'
        elif process.returncode == -15:
            # SIGTERM - process was stopped by user, this is normal
            completion_msg = f"🛑 Script stopped by user (exit code: {process.returncode})"
            status = 'stopped'
        else:
            completion_msg = f"❌ Script failed (exit code: {process.returncode})"
            status = 'failed'
        
        process_outputs[script_id].append("=" * 50)
        process_outputs[script_id].append(completion_msg)
        
        # Emit completion via WebSocket
        socketio.emit('process_output', {
            'script_id': script_id,
            'line': "=" * 50,
            'status': status
        })
        socketio.emit('process_output', {
            'script_id': script_id,
            'line': completion_msg,
            'status': status
        })
        
        # Remove from running processes
        if script_id in running_processes:
            del running_processes[script_id]
        if script_id in process_pids:
            del process_pids[script_id]
        
        # Update running processes status via WebSocket
        socketio.emit('process_status', {
            'running_processes': list(running_processes.keys()),
            'process_count': len(running_processes)
        })
        
        # Restore original directory
        os.chdir(original_dir)
            
    except Exception as e:
        if script_id not in process_outputs:
            process_outputs[script_id] = []
        
        error_msg = f"❌ Error running script: {str(e)}"
        process_outputs[script_id].append(error_msg)
        
        # Emit error via WebSocket
        socketio.emit('process_output', {
            'script_id': script_id,
            'line': error_msg,
            'status': 'error'
        })
        
        # Cleanup
        if script_id in running_processes:
            del running_processes[script_id]
        if script_id in process_pids:
            del process_pids[script_id]
        
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
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .auth-section { background: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 5px; }
        .search-section { background: #e7f3ff; padding: 15px; margin: 10px 0; border-radius: 5px; }
        .upload-section { background: #f0f8f0; padding: 15px; margin: 10px 0; border-radius: 5px; }
        .results-section { background: #fff3cd; padding: 15px; margin: 10px 0; border-radius: 5px; }
        .token-info { background: #f8f9fa; padding: 10px; margin: 10px 0; border: 1px solid #dee2e6; border-radius: 4px; font-family: monospace; }
        pre { background: #f5f5f5; padding: 10px; border: 1px solid #ddd; white-space: pre-wrap; max-height: 400px; overflow-y: auto; border-radius: 4px; }
        .success { color: green; font-weight: bold; }
        .error { color: red; font-weight: bold; }
        .warning { color: orange; font-weight: bold; }
        input[type="text"] { width: 300px; padding: 5px; margin: 5px; }
        button, input[type="submit"] { padding: 8px 15px; margin: 5px; cursor: pointer; }
        .auth-button { background: #dc3545; color: white; border: none; text-decoration: none; padding: 8px 15px; border-radius: 4px; }
        .search-button { background: #28a745; color: white; border: none; }
        .upload-button { background: #007bff; color: white; border: none; }
        .auto-refresh { color: #6c757d; font-size: 12px; }
        .running-indicator { color: #ffc107; font-weight: bold; }
        .progress-indicator { animation: pulse 2s infinite; }
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }
    </style>
    <script src="https://cdn.socket.io/4.0.0/socket.io.min.js"></script>
    <script src="{{ url_for('static', filename='app.js') }}"></script>
</head>
<body>
    <h1>🤖 StockX Tools - Web Interface</h1>
    <p>Complete StockX API integration with authentication, search, and bulk analysis</p>
    
    {% with messages = get_flashed_messages() %}
        {% if messages %}
            {% for message in messages %}
                <div style="padding: 10px; margin: 10px 0; background: #d4edda; border: 1px solid #c3e6cb; color: #155724; border-radius: 4px;">
                    {{ message }}
                </div>
            {% endfor %}
        {% endif %}
    {% endwith %}
    
    <div class="auth-section">
        <h2>🔐 Authentication Status</h2>
        {% if authenticated %}
            <p class="success">✅ AUTHENTICATED - StockX API is ready to use</p>
            {% if token_info %}
                <div class="token-info">
                    <strong>Token Information:</strong><br>
                    Access Token: {{ token_info.access_token }}<br>
                    Token Type: {{ token_info.token_type }}<br>
                    Has Refresh Token: {{ token_info.has_refresh_token }}<br>
                    Expires In: {{ token_info.expires_in }} seconds
                </div>
            {% endif %}
        {% elif auth_in_progress %}
            <p class="warning">⏳ Authentication in progress...</p>
            <p>Complete the authentication in the browser window that opened.</p>
        {% elif auth_error %}
            <p class="error">❌ NOT AUTHENTICATED</p>
            <p style="color: red;">Error: {{ auth_error }}</p>
            <p><a href="/auth/start" class="auth-button">AUTHENTICATE NOW</a></p>
        {% else %}
            <p class="error">❌ NOT AUTHENTICATED</p>
            <p><a href="/auth/start" class="auth-button">AUTHENTICATE NOW</a></p>
        {% endif %}
        
        <form action="/verify" method="post" style="margin: 10px 0;">
            <input type="submit" value="Verify Authentication Status" style="padding: 5px 10px; background: #17a2b8; color: white; border: none;">
        </form>
    </div>
    
    <div class="search-section">
        <h2>🔍 Product Search</h2>
        <p>Search for any shoe and get complete StockX information</p>
        <form action="/search" method="post" style="margin: 10px 0;">
            <label for="search_query">Enter shoe name (e.g., "Jordan 1 Chicago", "Nike Dunk Panda"):</label><br>
            <input type="text" name="query" id="search_query" placeholder="Jordan 1 Chicago" required><br>
            <input type="submit" value="Search StockX" class="search-button">
        </form>
    </div>
    
    <div class="upload-section">
        <h2>📊 Bulk Analysis Tools</h2>
        
        <h3>💰 eBay Price Comparison</h3>
        <form action="/upload" method="post" enctype="multipart/form-data" style="margin: 10px 0;">
            <input type="hidden" name="script_type" value="ebay">
            <label for="ebay_upload">Upload eBay CSV file:</label><br>
            <input type="file" name="file" id="ebay_upload" accept=".csv" style="margin: 5px 0;"><br>
            <input type="submit" value="Upload & Run eBay Analysis" class="upload-button">
        </form>
        <p><em>Compare eBay auction data with StockX prices</em></p>
        
        <h3>📈 Inventory Analysis</h3>
        <form action="/upload" method="post" enctype="multipart/form-data" style="margin: 10px 0;">
            <input type="hidden" name="script_type" value="inventory">
            <label for="inventory_upload">Upload inventory CSV file:</label><br>
            <input type="file" name="file" id="inventory_upload" accept=".csv" style="margin: 5px 0;"><br>
            <input type="submit" value="Upload & Run Inventory Analysis" class="upload-button">
        </form>
        <p><em>Analyze inventory CSV against StockX market data</em></p>
    </div>
    
    <div class="results-section">
        <h2>📁 Results & Downloads</h2>
        <p><strong>Your processed files are saved in these locations:</strong></p>
        <ul>
            <li><strong>uploads/</strong> - Your uploaded files</li>
            <li><strong>ebay_tools/</strong> - eBay analysis results</li>
            <li><strong>pricing_tools/</strong> - Inventory analysis results</li>
        </ul>
        <p><a href="/downloads" style="padding: 5px 10px; background: #17a2b8; color: white; text-decoration: none; border-radius: 4px;">View & Download All Results</a></p>
        <p><em>⏱️ Processing can take several minutes. Your files remain available even if you close the browser.</em></p>
    </div>
    
    <hr>
    
    <div class="running-processes">
        <h2>🔄 Running Processes</h2>
        {% if running_processes %}
            {% for script_id in running_processes %}
                <div style="margin: 10px 0; padding: 10px; border: 1px solid #ddd; background: #f9f9f9;">
                    <span class="running-indicator">⏳ {{ script_id }} is running...</span>
                    <button onclick="stopProcess('{{ script_id }}')" 
                            style="background: #dc3545; color: white; border: none; padding: 4px 8px; margin-left: 10px; cursor: pointer;">
                        Stop Process
                    </button>
                </div>
            {% endfor %}
        {% else %}
            <p>No scripts currently running</p>
        {% endif %}
        <p><small>Real-time streaming updates via WebSocket</small></p>
    </div>
    
    <div id="recent-activity">
        <h2>📋 Recent Activity</h2>
        <form action="/clear" method="post" style="margin: 10px 0;">
            <input type="submit" value="Clear All Logs" style="padding: 5px 10px;">
        </form>
        
        {% for script_id, output in outputs %}
            <div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h3>{{ script_id }} - {{ output.timestamp }}</h3>
                    {% if script_id in running_processes %}
                        <button onclick="stopProcess('{{ script_id }}')" 
                                style="background: #dc3545; color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer;">
                            Stop
                        </button>
                    {% endif %}
                </div>
                <div id="output-{{ script_id }}">
                    <pre style="max-height: 300px; overflow-y: auto; background: #f5f5f5; padding: 10px; border: 1px solid #ddd; border-radius: 4px;">{{ output.content }}</pre>
                </div>
                <hr>
            </div>
        {% endfor %}
        
        {% if not outputs %}
            <p>No recent activity</p>
        {% endif %}
    </div>
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

@app.route('/verify', methods=['POST'])
def verify_auth():
    """Verify authentication and show token info"""
    check_real_authentication()
    return redirect(url_for('index'))

@app.route('/search', methods=['POST'])
def search_products():
    """Search for products and display detailed info"""
    if not check_real_authentication():
        flash('❌ SEARCH BLOCKED: Authentication required. Please authenticate first.')
        return redirect(url_for('index'))
    
    query = request.form.get('query', '').strip()
    
    if not query:
        flash('Please enter a search query')
        return redirect(url_for('index'))
    
    try:
        # Load token for API call
        with open(TOKEN_FILE, 'r') as f:
            tokens = json.load(f)
        
        headers = {
            'Authorization': f'Bearer {tokens["access_token"]}',
            'x-api-key': STOCKX_API_KEY
        }
        
        # Search for products
        response = requests.get(
            f'https://api.stockx.com/v2/catalog/search?query={query}&pageSize=5',
            headers=headers,
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            products = data.get('products', [])
            
            if products:
                flash(f'🔍 SEARCH RESULTS for "{query}" - Found {data.get("count", 0)} total products')
                
                for i, product in enumerate(products, 1):
                    # Get basic product info
                    title = product.get('title', 'Unknown Product')
                    brand = product.get('brand', 'Unknown')
                    style_id = product.get('styleId', 'N/A')
                    product_type = product.get('productType', 'N/A')
                    
                    # Get product attributes
                    attrs = product.get('productAttributes', {})
                    gender = attrs.get('gender', 'N/A')
                    release_date = attrs.get('releaseDate', 'N/A')
                    retail_price = attrs.get('retailPrice', 'N/A')
                    colorway = attrs.get('colorway', 'N/A')
                    
                    # Get size chart info
                    size_chart = product.get('sizeChart', {})
                    default_conversion = size_chart.get('defaultConversion', {})
                    size_type = default_conversion.get('type', 'N/A') if default_conversion else 'N/A'
                    
                    # Get market eligibility
                    flex_eligible = product.get('isFlexEligible', False)
                    direct_eligible = product.get('isDirectEligible', False)
                    
                    # Format product info
                    product_info = f"""
{i}. {title}
   Brand: {brand} | Style: {style_id} | Type: {product_type}
   Gender: {gender} | Release: {release_date} | Retail: ${retail_price}
   Colorway: {colorway}
   Size Type: {size_type}
   Flex Eligible: {flex_eligible} | Direct Eligible: {direct_eligible}
   Product ID: {product.get('productId', 'N/A')}
   URL Key: {product.get('urlKey', 'N/A')}
"""
                    flash(product_info)
                    
                    # Try to get market data for first product
                    if i == 1:
                        try:
                            market_response = requests.get(
                                f'https://api.stockx.com/v2/catalog/products/{product.get("productId")}/market-data',
                                headers=headers,
                                timeout=10
                            )
                            
                            if market_response.status_code == 200:
                                market_data = market_response.json()
                                if market_data:
                                    # Get first variant's market data
                                    first_variant = market_data[0] if isinstance(market_data, list) and market_data else market_data
                                    
                                    lowest_ask = first_variant.get('lowestAskAmount', 'N/A')
                                    highest_bid = first_variant.get('highestBidAmount', 'N/A')
                                    currency = first_variant.get('currencyCode', 'USD')
                                    
                                    flash(f'💰 MARKET DATA for {title}:')
                                    flash(f'   Lowest Ask: {lowest_ask} {currency}')
                                    flash(f'   Highest Bid: {highest_bid} {currency}')
                        except Exception as e:
                            flash(f'⚠️ Could not fetch market data: {str(e)}')
                    
            else:
                flash(f'❌ No products found for "{query}"')
        else:
            flash(f'❌ Search failed - Status: {response.status_code}')
            
    except Exception as e:
        flash(f'❌ Search error: {str(e)}')
    
    return redirect(url_for('index'))

@app.route('/')
def index():
    """Main page with script options"""
    global auth_state
    
    # ALWAYS check REAL authentication status with actual API call
    auth_status = check_real_authentication()
    
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
        auth_error=auth_state.get('auth_error', None),
        token_info=auth_state.get('token_info', None)
    )

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload - REQUIRES REAL AUTHENTICATION"""
    if 'file' not in request.files:
        flash('No file selected')
        return redirect(url_for('index'))
    
    file = request.files['file']
    script_type = request.form.get('script_type')
    
    if file.filename == '':
        flash('No file selected')
        return redirect(url_for('index'))
    
    # VERIFY REAL AUTHENTICATION BEFORE PROCESSING UPLOAD
    if not check_real_authentication():
        flash('❌ UPLOAD BLOCKED: Authentication required. Please authenticate first.')
        return redirect(url_for('index'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Add timestamp to prevent conflicts
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        flash(f'File uploaded successfully: {filename}')
        
        # Auto-run the script with uploaded file
        script_id = f"{script_type}_{datetime.now().strftime('%H%M%S')}"
        
        if script_type == 'ebay':
            command = f'python3 ebay_stockxpricing.py "../uploads/{filename}"'
            working_dir = 'ebay_tools'
        elif script_type == 'inventory':
            command = f'python3 inventory_stockx_analyzer.py "../uploads/{filename}"'
            working_dir = 'pricing_tools'
        else:
            flash('Invalid script type')
            return redirect(url_for('index'))
        
        # Start script in background thread
        thread = threading.Thread(
            target=run_script_async,
            args=(script_id, command, working_dir)
        )
        thread.daemon = True
        thread.start()
        
        return redirect(url_for('index'))
    else:
        flash('Invalid file type. Please upload a CSV file.')
        return redirect(url_for('index'))

@app.route('/downloads')
def list_downloads():
    """List available output files for download"""
    download_dirs = ['ebay_tools', 'pricing_tools', 'uploads']
    files = []
    
    for directory in download_dirs:
        if os.path.exists(directory):
            for filename in os.listdir(directory):
                if filename.endswith('.csv'):
                    filepath = os.path.join(directory, filename)
                    file_info = {
                        'name': filename,
                        'path': directory,
                        'size': os.path.getsize(filepath),
                        'modified': datetime.fromtimestamp(os.path.getmtime(filepath)).strftime('%Y-%m-%d %H:%M:%S')
                    }
                    files.append(file_info)
    
    # Sort by modification time (newest first)
    files.sort(key=lambda x: x['modified'], reverse=True)
    
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Download Files - StockX Tools</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            table { border-collapse: collapse; width: 100%; }
            th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
            th { background-color: #f2f2f2; }
            .download-btn { background: #007bff; color: white; text-decoration: none; padding: 5px 10px; border-radius: 4px; }
        </style>
    </head>
    <body>
        <h1>📁 Download Files</h1>
        <p><a href="/">← Back to main page</a></p>
        <hr>
        
        <h2>📍 File Locations</h2>
        <ul>
            <li><strong>uploads/</strong> - Your uploaded CSV files</li>
            <li><strong>ebay_tools/</strong> - eBay price comparison results</li>
            <li><strong>pricing_tools/</strong> - Inventory analysis results</li>
        </ul>
        
        {% if files %}
            <h2>Available CSV Files</h2>
            <table>
                <tr>
                    <th>File Name</th>
                    <th>Directory</th>
                    <th>Size</th>
                    <th>Modified</th>
                    <th>Download</th>
                </tr>
                {% for file in files %}
                <tr>
                    <td>{{ file.name }}</td>
                    <td>{{ file.path }}</td>
                    <td>{{ "%.1f"|format(file.size/1024) }} KB</td>
                    <td>{{ file.modified }}</td>
                    <td>
                        <a href="/download/{{ file.path }}/{{ file.name }}" class="download-btn">
                            Download
                        </a>
                    </td>
                </tr>
                {% endfor %}
            </table>
        {% else %}
            <p>No CSV files found. Upload and process files to see results here.</p>
        {% endif %}
    </body>
    </html>
    """, files=files)

@app.route('/download/<path:directory>/<filename>')
def download_file(directory, filename):
    """Download a specific file"""
    try:
        return send_from_directory(directory, filename, as_attachment=True)
    except FileNotFoundError:
        flash('File not found')
        return redirect(url_for('list_downloads'))

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

@app.route('/stop_process/<script_id>', methods=['POST'])
def stop_process(script_id):
    """Stop a running process"""
    try:
        if script_id in running_processes:
            process = running_processes[script_id]
            process.terminate()
            
            # Try to kill child processes too
            try:
                if script_id in process_pids:
                    parent = psutil.Process(process_pids[script_id])
                    children = parent.children(recursive=True)
                    for child in children:
                        child.terminate()
                    # Wait a bit then kill if still running
                    time.sleep(1)
                    for child in children:
                        if child.is_running():
                            child.kill()
                    parent.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            
            # Clean up
            del running_processes[script_id]
            if script_id in process_pids:
                del process_pids[script_id]
            
            # Add stop message to output
            if script_id in process_outputs:
                process_outputs[script_id].append("🛑 Process stopped by user")
            
            # Emit stop message via WebSocket
            socketio.emit('process_output', {
                'script_id': script_id,
                'line': "🛑 Process stopped by user",
                'status': 'stopped'
            })
            
            # Update running processes status
            socketio.emit('process_status', {
                'running_processes': list(running_processes.keys()),
                'process_count': len(running_processes)
            })
            
            return jsonify({'success': True, 'message': 'Process stopped'})
        else:
            return jsonify({'success': False, 'message': 'Process not found'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/process_list')
def process_list():
    """Get list of running processes"""
    return jsonify({
        'running_processes': list(running_processes.keys()),
        'process_count': len(running_processes)
    })

@app.route('/debug')
def debug_websocket():
    """Debug WebSocket page"""
    try:
        with open('debug_websocket.html', 'r') as f:
            return f.read()
    except FileNotFoundError:
        return "Debug file not found", 404

@app.route('/test_websocket')
def test_websocket():
    """Test WebSocket by sending a few messages"""
    try:
        import time
        import threading
        
        def send_test_messages():
            time.sleep(1)
            for i in range(3):
                socketio.emit('process_output', {
                    'script_id': 'websocket_test',
                    'line': f'🧪 Test message {i+1}/3 - {time.strftime("%H:%M:%S")}',
                    'status': 'running'
                })
                time.sleep(1)
            socketio.emit('process_output', {
                'script_id': 'websocket_test', 
                'line': '✅ WebSocket test completed!',
                'status': 'completed'
            })
        
        # Start in background thread
        threading.Thread(target=send_test_messages, daemon=True).start()
        
        return jsonify({'success': True, 'message': 'WebSocket test started'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# WebSocket handlers
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print(f'Client connected: {request.sid}')
    
    # Send current running processes to new client
    emit('process_status', {
        'running_processes': list(running_processes.keys()),
        'process_count': len(running_processes)
    })

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print(f'Client disconnected: {request.sid}')

@socketio.on('request_output')
def handle_request_output(data):
    """Send existing output for a process"""
    script_id = data.get('script_id')
    if script_id in process_outputs:
        for line in process_outputs[script_id]:
            emit('process_output', {
                'script_id': script_id,
                'line': line,
                'status': 'running' if script_id in running_processes else 'completed'
            })

if __name__ == '__main__':
    try:
        print("🌐 Starting StockX Tools Web Interface...")
        print("📱 Access at: http://0.0.0.0:5000")
        print("🔄 Real-time updates via WebSocket")
        print("=" * 50)
        
        # Start automatic token refresh thread
        try:
            start_token_refresh_thread()
        except Exception as e:
            print(f"⚠️ Warning: Could not start token refresh thread: {e}")
        
        # Use SocketIO instead of regular Flask with production fixes
        socketio.run(
            app, 
            host='0.0.0.0', 
            port=5000, 
            debug=False,
            allow_unsafe_werkzeug=True,  # Fix for production deployment
            use_reloader=False,          # Prevent reloader issues in production
            log_output=True              # Enable logging for debugging
        )
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        print("🔄 Attempting fallback server configuration...")
        try:
            # Fallback configuration without unsafe_werkzeug
            socketio.run(
                app, 
                host='0.0.0.0', 
                port=5000, 
                debug=False,
                use_reloader=False
            )
        except Exception as fallback_error:
            print(f"❌ Fallback also failed: {fallback_error}")
            print("💡 Try running with: python app.py --production")
            import sys
            sys.exit(1)
