
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

# Manual URL override for OAuth callback (set this if auto-detection fails)
MANUAL_CALLBACK_URL = os.getenv('STOCKX_CALLBACK_URL', None)  # e.g., 'https://your-app.replit.app'

# Global auth state
auth_state = {
    'authenticated': False,
    'auth_in_progress': False,
    'auth_code': None,
    'auth_error': None,
    'token_info': None
}

def get_replit_url():
    """Get the Replit app URL for OAuth callback with improved detection"""
    
    # Method 0: Check for manual override first
    if MANUAL_CALLBACK_URL:
        print(f"🎯 Using MANUAL override URL: {MANUAL_CALLBACK_URL}")
        return MANUAL_CALLBACK_URL
    
    # Method 1: Check REPLIT_DEV_DOMAIN (for development)
    replit_domain = os.getenv('REPLIT_DEV_DOMAIN')
    if replit_domain:
        url = f'https://{replit_domain}'
        print(f"🌐 Using REPLIT_DEV_DOMAIN: {url}")
        return url
    
    # Method 2: Check REPL_SLUG and REPL_OWNER (older format)
    replit_slug = os.getenv('REPL_SLUG')
    replit_owner = os.getenv('REPL_OWNER')
    if replit_slug and replit_owner:
        url = f'https://{replit_slug}.{replit_owner}.repl.co'
        print(f"🌐 Using REPL_SLUG/REPL_OWNER: {url}")
        return url
    
    # Method 3: Check for deployed Replit environment with REPLIT_URL
    replit_url = os.getenv('REPLIT_URL')
    if replit_url:
        print(f"🌐 Using REPLIT_URL: {replit_url}")
        return replit_url
    
    # Method 4: Try REPL_ID for new deployment format
    repl_id = os.getenv('REPL_ID')
    if repl_id:
        url = f'https://{repl_id}.replit.app'
        print(f"🌐 Using REPL_ID: {url}")
        return url
        
    # Method 5: Check if we're in any Replit environment
    if os.getenv('REPLIT_DEPLOYMENT') or os.getenv('REPL_HOME'):
        # Try to construct from available environment variables
        hostname = os.getenv('HOSTNAME', '')
        if '.replit.app' in hostname or '.repl.co' in hostname:
            url = f'https://{hostname}'
            print(f"🌐 Using HOSTNAME: {url}")
            return url
            
        # Last resort for deployed Replit
        print("⚠️ Detected Replit environment but couldn't determine URL")
        print("💡 To fix this, set the STOCKX_CALLBACK_URL environment variable")
        print("   Example: STOCKX_CALLBACK_URL=https://your-app-name.replit.app")
        print("Available environment variables:")
        for key, value in os.environ.items():
            if 'REPL' in key.upper():
                print(f"  {key}: {value}")
        
        # Use a generic Replit deployment URL (user will need to update)
        url = 'https://your-app.replit.app'
        print(f"🚨 FALLBACK URL: {url} - You MUST update the OAuth app settings")
        return url
    
    # Method 6: Check if running on a specific port (Replit detection)
    port = os.getenv('PORT')
    if port and (port == '5000' or port == '8080'):
        # This might be Replit, try common patterns
        workspace_name = os.path.basename(os.getcwd())
        possible_urls = [
            f'https://{workspace_name}.replit.app',
            f'https://{workspace_name}.{os.getenv("USER", "user")}.repl.co'
        ]
        for url in possible_urls:
            print(f"🔍 Testing possible Replit URL: {url}")
        
        # Return the first one, user can verify
        url = possible_urls[0]
        print(f"🌐 GUESSED URL: {url} - Please verify this is correct")
        print(f"💡 If wrong, set STOCKX_CALLBACK_URL environment variable to the correct URL")
        return url
    
    # Fallback for local development  
    url = 'http://localhost:5000'
    print(f"🏠 Local development URL: {url}")
    return url

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
    """Enhanced token refresh with better error handling and validation"""
    try:
        print("🔄 Starting token refresh process...")
        
        # Check if token file exists and is readable
        if not os.path.exists(TOKEN_FILE):
            print("❌ No token file found - cannot refresh")
            return False
            
        with open(TOKEN_FILE, 'r') as f:
            tokens = json.load(f)
        
        # Validate we have a refresh token
        if 'refresh_token' not in tokens:
            print("❌ No refresh token available - cannot refresh")
            return False
            
        # Prepare refresh request
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': tokens['refresh_token'],
            'client_id': STOCKX_CLIENT_ID,
            'client_secret': STOCKX_CLIENT_SECRET,
            'audience': 'gateway.stockx.com'
        }
        
        print("📡 Sending refresh request to StockX...")
        response = requests.post(
            'https://accounts.stockx.com/oauth/token',
            data=data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=30  # Increased timeout for reliability
        )
        
        if response.status_code == 200:
            new_tokens = response.json()
            
            # Validate the response contains required fields
            if 'access_token' not in new_tokens:
                print("❌ Invalid refresh response - no access token")
                return False
            
            # Preserve existing refresh token if not provided in response
            if 'refresh_token' not in new_tokens and 'refresh_token' in tokens:
                new_tokens['refresh_token'] = tokens['refresh_token']
                print("🔄 Preserved existing refresh token")
            
            # Add timestamp for tracking
            new_tokens['refreshed_at'] = time.time()
            
            # Atomic write to prevent corruption
            temp_file = TOKEN_FILE + '.tmp'
            with open(temp_file, 'w') as f:
                json.dump(new_tokens, f, indent=2)
            os.replace(temp_file, TOKEN_FILE)
            
            print(f"✅ Token refreshed successfully at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            return True
            
        elif response.status_code == 400:
            print("❌ Refresh token expired or invalid - full re-authentication required")
            return False
            
        elif response.status_code == 401:
            print("❌ Refresh token unauthorized - full re-authentication required")
            return False
            
        else:
            print(f"❌ Token refresh failed: HTTP {response.status_code}")
            try:
                error_data = response.json()
                if 'error_description' in error_data:
                    print(f"   Error: {error_data['error_description']}")
            except:
                print(f"   Response: {response.text[:200]}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ Token refresh timeout - network issues")
        return False
        
    except requests.exceptions.ConnectionError:
        print("❌ Token refresh connection error - check internet")
        return False
        
    except json.JSONDecodeError as e:
        print(f"❌ Token file corrupted: {str(e)}")
        return False
        
    except Exception as e:
        print(f"❌ Unexpected error during token refresh: {str(e)}")
        return False

def smart_auto_refresh_token():
    """Enhanced automatic token refresh with intelligent timing and error recovery"""
    global token_refresh_active
    token_refresh_active = True
    
    print("🚀 Starting enhanced automatic token refresh daemon")
    
    # Initial startup delay to let the app initialize
    time.sleep(45)
    
    while token_refresh_active:
        try:
            # Check if we should refresh based on token age and expiry
            should_refresh = False
            time_until_refresh = 39600  # Default 11 hours
            
            if os.path.exists(TOKEN_FILE):
                try:
                    with open(TOKEN_FILE, 'r') as f:
                        tokens = json.load(f)
                    
                    # Calculate when to refresh based on expires_in
                    expires_in = tokens.get('expires_in', 43200)  # Default 12 hours
                    refreshed_at = tokens.get('refreshed_at', os.path.getmtime(TOKEN_FILE))
                    
                    # Refresh when 80% of the token lifetime has passed
                    refresh_threshold = expires_in * 0.8
                    time_since_refresh = time.time() - refreshed_at
                    
                    if time_since_refresh >= refresh_threshold:
                        should_refresh = True
                        print(f"⏰ Token refresh due (age: {time_since_refresh/3600:.1f}h, threshold: {refresh_threshold/3600:.1f}h)")
                    else:
                        time_until_refresh = refresh_threshold - time_since_refresh
                        print(f"⏳ Next refresh in {time_until_refresh/3600:.1f} hours")
                        
                except (json.JSONDecodeError, KeyError, OSError) as e:
                    print(f"⚠️ Error checking token age: {e}")
                    should_refresh = True
            else:
                print("⚠️ No token file found")
            
            # Perform refresh if needed
            if should_refresh and token_refresh_active:
                success = refresh_access_token()
                if success:
                    print("✅ Automatic refresh successful")
                    # Sleep for the normal interval after successful refresh
                    time_until_refresh = 39600  # 11 hours
                else:
                    print("❌ Automatic refresh failed - will retry in 1 hour")
                    time_until_refresh = 3600  # 1 hour retry
            
            # Sleep in smaller chunks to allow for graceful shutdown
            sleep_chunks = int(time_until_refresh / 60)  # 1-minute chunks
            for i in range(sleep_chunks):
                if not token_refresh_active:
                    break
                time.sleep(60)
                
        except Exception as e:
            print(f"❌ Error in auto-refresh daemon: {str(e)}")
            # Sleep for 10 minutes before retrying
            for i in range(10):
                if not token_refresh_active:
                    break
                time.sleep(60)
    
    print("🛑 Automatic token refresh daemon stopped")

def start_enhanced_token_refresh_thread():
    """Start the enhanced automatic token refresh thread"""
    global token_refresh_thread
    if token_refresh_thread is None or not token_refresh_thread.is_alive():
        token_refresh_thread = threading.Thread(target=smart_auto_refresh_token, daemon=True)
        token_refresh_thread.start()
        print("🔄 Started enhanced automatic token refresh daemon")

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

def robust_authentication_check():
    """
    Comprehensive authentication check with automatic recovery
    Returns: (is_authenticated, error_message, recovery_action)
    """
    global auth_state
    
    try:
        # Step 1: Check if token file exists
        if not os.path.exists(TOKEN_FILE):
            return False, 'No token file found - first time setup required', 'authenticate'
        
        # Step 2: Load and validate token structure
        try:
            with open(TOKEN_FILE, 'r') as f:
                tokens = json.load(f)
        except json.JSONDecodeError:
            return False, 'Token file corrupted - re-authentication required', 'authenticate'
        
        if 'access_token' not in tokens:
            return False, 'Invalid token file - no access token found', 'authenticate'
        
        # Step 3: Store token info for display
        auth_state['token_info'] = {
            'access_token': tokens['access_token'][:50] + '...',
            'has_refresh_token': 'refresh_token' in tokens,
            'token_type': tokens.get('token_type', 'Bearer'),
            'expires_in': tokens.get('expires_in', 'Unknown'),
            'created_at': os.path.getmtime(TOKEN_FILE) if os.path.exists(TOKEN_FILE) else 'Unknown'
        }
        
        # Step 4: Test the token with a real API call
        headers = {
            'Authorization': f'Bearer {tokens["access_token"]}',
            'x-api-key': STOCKX_API_KEY
        }
        
        print("🔍 Testing access token validity...")
        response = requests.get(
            'https://api.stockx.com/v2/catalog/search?query=nike&pageSize=1',
            headers=headers,
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            if 'products' in data or 'count' in data:
                auth_state['authenticated'] = True
                auth_state['auth_error'] = None
                print("✅ Access token is valid and working!")
                return True, None, None
            else:
                print("⚠️ API returned unexpected data structure")
                return False, 'API returned unexpected data - token may be invalid', 'refresh_or_auth'
                
        elif response.status_code == 401:
            print("🔄 Access token expired, attempting refresh...")
            # Try to refresh the token
            if 'refresh_token' in tokens:
                if refresh_access_token():
                    print("✅ Token refreshed successfully!")
                    return True, None, None
                else:
                    print("❌ Token refresh failed")
                    return False, 'Token refresh failed - re-authentication required', 'authenticate'
            else:
                return False, 'Access token expired and no refresh token available', 'authenticate'
                
        elif response.status_code == 429:
            print("⚠️ Rate limited - will retry later")
            return False, 'API rate limited - try again in a few minutes', 'wait'
            
        else:
            print(f"⚠️ API returned status {response.status_code}")
            return False, f'API authentication failed - HTTP {response.status_code}', 'refresh_or_auth'
            
    except requests.exceptions.Timeout:
        return False, 'Network timeout during authentication check - check internet connection', 'retry'
        
    except requests.exceptions.ConnectionError:
        return False, 'Network connection error - check internet connection', 'retry'
        
    except Exception as e:
        error_msg = f'Authentication check failed: {str(e)}'
        print(f"❌ {error_msg}")
        return False, error_msg, 'authenticate'

def perform_smart_authentication():
    """
    Smart authentication that tries multiple recovery methods
    Returns: True if successful, False if manual intervention needed
    """
    print("🔐 Starting Smart Authentication System...")
    print("=" * 60)
    
    # Step 1: Check current authentication status
    is_auth, error_msg, recovery_action = robust_authentication_check()
    
    if is_auth:
        print("✅ Already authenticated and working!")
        return True
    
    print(f"⚠️ Authentication issue: {error_msg}")
    
    # Step 2: Try recovery based on the recommended action
    if recovery_action == 'refresh_or_auth':
        print("🔄 Attempting token refresh first...")
        if can_refresh_token() and refresh_access_token():
            # Verify the refresh worked
            is_auth, _, _ = robust_authentication_check()
            if is_auth:
                print("✅ Token refresh successful!")
                return True
    
    elif recovery_action == 'wait':
        print("⏸️ Rate limited - automatic retry will happen later")
        return False
        
    elif recovery_action == 'retry':
        print("🔄 Network issue detected - will retry automatically")
        return False
    
    # Step 3: If we get here, full authentication is needed
    print("🔐 Full authentication required")
    print("👆 Click the 'AUTHENTICATE NOW' button in the web interface")
    
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
    <script>
        // Initialize WebSocket immediately
        console.log('Initializing WebSocket...');
        var socket = io({
            transports: ['websocket', 'polling']
        });
        
        socket.on('connect', function() {
            console.log('✅ WebSocket connected');
            document.title = 'StockX Tools - Connected';
        });
        
        socket.on('disconnect', function() {
            console.log('❌ WebSocket disconnected');
            document.title = 'StockX Tools - Disconnected';
        });
        
        socket.on('process_output', function(data) {
            console.log('📨 PROCESS OUTPUT RECEIVED:', data);
            document.title = '* StockX Tools - New Output';
            document.body.style.backgroundColor = '#f0f8ff';
            setTimeout(function() {
                document.title = 'StockX Tools - Web Interface';
                document.body.style.backgroundColor = '';
            }, 1000);
            
            // Find the output container
            var outputContainer = document.getElementById('output-' + data.script_id);
            if (outputContainer) {
                var pre = outputContainer.querySelector('pre');
                if (pre) {
                    var existingContent = pre.textContent || '';
                    pre.textContent = existingContent + data.line + '\\n';
                    pre.scrollTop = pre.scrollHeight;
                    pre.style.borderLeft = '3px solid #28a745';
                    setTimeout(function() {
                        pre.style.borderLeft = '1px solid #ddd';
                    }, 500);
                    console.log('✅ Added line to container, new length:', pre.textContent.length);
                } else {
                    console.log('❌ No pre element found');
                }
            } else {
                console.log('❌ No output container found for:', data.script_id);
                
                // Create emergency container if it doesn't exist
                var recentActivity = document.getElementById('recent-activity');
                if (!recentActivity) {
                    // Create recent-activity div if it doesn't exist
                    recentActivity = document.createElement('div');
                    recentActivity.id = 'recent-activity';
                    recentActivity.innerHTML = '<h2>📊 Recent Activity</h2>';
                    document.body.appendChild(recentActivity);
                    console.log('✅ Created recent-activity container');
                }
                
                var emergencyDiv = document.createElement('div');
                emergencyDiv.innerHTML = '<h3>' + data.script_id + ' (Live Stream)</h3><div id="output-' + data.script_id + '"><pre style="background: #f0f8ff; padding: 10px; border: 1px solid #0066cc; max-height: 300px; overflow-y: auto;">' + data.line + '\\n</pre></div>';
                recentActivity.appendChild(emergencyDiv);
                console.log('✅ Created emergency container for:', data.script_id);
            }
        });
        
        socket.on('process_status', function(data) {
            console.log('📊 Process status:', data);
        });
        
        // Add event listener for ALL events to debug
        socket.onAny(function(event, data) {
            console.log('🔍 WebSocket event received:', event, data);
        });
        
        console.log('WebSocket initialization complete');
    </script>
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
                <div class="token-info" style="background: #d4edda; padding: 10px; border-radius: 5px; margin: 10px 0;">
                    <strong>🔑 Token Information:</strong><br>
                    📱 Access Token: {{ token_info.access_token }}<br>
                    🎫 Token Type: {{ token_info.token_type }}<br>
                    🔄 Has Refresh Token: {{ '✅ Yes' if token_info.has_refresh_token else '❌ No' }}<br>
                    ⏱️ Expires In: {{ token_info.expires_in }} seconds<br>
                    📅 Last Updated: {{ token_info.created_at }}
                </div>
            {% endif %}
            <div style="margin: 10px 0;">
                <a href="/auth/reset" onclick="return confirm('This will clear your authentication. Are you sure?')" 
                   style="background: #ffc107; color: #212529; padding: 8px 16px; text-decoration: none; border-radius: 4px; margin-right: 10px;">
                    🔄 Reset Authentication
                </a>
            </div>
        {% elif auth_in_progress %}
            <p class="warning">⏳ Authentication in progress...</p>
            <p>Complete the authentication in the browser window that opened.</p>
            <div style="margin: 10px 0;">
                <a href="/auth/reset" style="background: #6c757d; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px;">
                    ❌ Cancel Authentication
                </a>
            </div>
        {% elif auth_error %}
            <p class="error">❌ NOT AUTHENTICATED</p>
            <div style="background: #f8d7da; color: #721c24; padding: 10px; border-radius: 5px; margin: 10px 0;">
                <strong>⚠️ Error:</strong> {{ auth_error }}
            </div>
            <div style="margin: 10px 0;">
                <a href="/auth/start" class="auth-button" style="background: #28a745; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; margin-right: 10px; font-weight: bold;">
                    🔑 AUTHENTICATE NOW
                </a>
                <a href="/auth/reset" style="background: #dc3545; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px;">
                    🔄 Reset & Try Again
                </a>
            </div>
        {% else %}
            <p class="error">❌ NOT AUTHENTICATED</p>
            <p>First time setup required. Click below to authenticate with StockX.</p>
            <div style="margin: 10px 0;">
                <a href="/auth/start" class="auth-button" style="background: #007bff; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                    🔑 START AUTHENTICATION
                </a>
            </div>
        {% endif %}
        
        <div style="margin: 15px 0;">
            <form action="/verify" method="post" style="display: inline;">
                <input type="submit" value="🔍 Verify Status" style="padding: 8px 16px; background: #17a2b8; color: white; border: none; border-radius: 4px; cursor: pointer;">
            </form>
            <a href="/auth/health" style="background: #6c757d; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px; margin-left: 10px;">
                🏥 Full Health Check
            </a>
        </div>
        
        {% if not authenticated %}
            <div style="background: #e9ecef; padding: 15px; border-radius: 5px; margin: 10px 0;">
                <h4>💡 Troubleshooting Tips:</h4>
                <ul style="text-align: left; margin: 0;">
                    <li>🌐 Make sure you're connected to the internet</li>
                    <li>🔒 Check that this Replit app URL is allowed in StockX OAuth settings</li>
                    <li>🔄 Try "Reset Authentication" if you're having issues</li>
                    <li>📱 If callback URL mismatch, set STOCKX_CALLBACK_URL environment variable</li>
                </ul>
            </div>
        {% endif %}
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
        
        <h3>�� Inventory Analysis</h3>
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
    """Enhanced OAuth callback handler with better error handling"""
    global auth_state
    
    # Get parameters from the callback
    auth_code = request.args.get('code')
    error = request.args.get('error')
    error_description = request.args.get('error_description', '')
    
    print(f"🔔 OAuth callback received - Code: {'✅' if auth_code else '❌'}, Error: {'✅' if error else '❌'}")
    
    # Handle OAuth errors
    if error:
        auth_state['auth_error'] = f"{error}: {error_description}"
        auth_state['auth_in_progress'] = False
        
        print(f"❌ OAuth error: {error}")
        print(f"   Description: {error_description}")
        
        # Provide specific guidance based on error type
        if 'callback' in error_description.lower() or 'mismatch' in error_description.lower():
            current_url = get_replit_url()
            callback_url = f"{current_url}/auth/callback"
            
            return render_template_string("""
            <html>
            <head><title>🚨 OAuth Callback URL Mismatch</title></head>
            <body style="font-family: Arial; padding: 30px; max-width: 800px; margin: 0 auto;">
                <h1 style="color: red;">🚨 OAuth Callback URL Mismatch</h1>
                <p><strong>Problem:</strong> {{ error_description }}</p>
                
                <h2>📋 How to Fix This:</h2>
                <ol>
                    <li><strong>Current detected URL:</strong> <code>{{ callback_url }}</code></li>
                    <li><strong>If this URL is wrong:</strong>
                        <ul>
                            <li>Set the environment variable: <code>STOCKX_CALLBACK_URL=https://your-actual-app-url.replit.app</code></li>
                            <li>Or update your Replit secrets with the correct URL</li>
                        </ul>
                    </li>
                    <li><strong>If the URL is correct:</strong>
                        <ul>
                            <li>The StockX OAuth app settings need to be updated</li>
                            <li>Add <code>{{ callback_url }}</code> to the allowed callback URLs</li>
                        </ul>
                    </li>
                </ol>
                
                <h2>🔧 Quick Actions:</h2>
                <p><a href="/auth/reset" style="background: #dc3545; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">🔄 Reset Authentication</a></p>
                <p><a href="/" style="background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">🏠 Return to Main Page</a></p>
                
                <h2>🐛 Debug Information:</h2>
                <pre style="background: #f8f9fa; padding: 15px; border: 1px solid #dee2e6; border-radius: 5px;">
Detected URL: {{ current_url }}
Callback URL: {{ callback_url }}
Error: {{ error }}
Description: {{ error_description }}
Manual Override: {{ manual_override }}
Environment Variables:
{% for key, value in env_vars %}
  {{ key }}: {{ value }}
{% endfor %}
                </pre>
            </body>
            </html>
            """, 
            error=error,
            error_description=error_description, 
            callback_url=callback_url,
            current_url=current_url,
            manual_override=MANUAL_CALLBACK_URL or 'Not set',
            env_vars=[(k, v) for k, v in os.environ.items() if 'REPL' in k.upper()]
            )
        
        else:
            # Generic error handling
            return render_template_string("""
            <html>
            <head><title>❌ Authentication Error</title></head>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1 style="color: red;">❌ Authentication Error</h1>
                <p><strong>Error:</strong> {{ error }}</p>
                <p><strong>Description:</strong> {{ error_description }}</p>
                
                <h2>🔧 What to Try:</h2>
                <ul style="text-align: left; display: inline-block;">
                    <li>Click "Reset Authentication" below and try again</li>
                    <li>Check your internet connection</li>
                    <li>Try again in a few minutes</li>
                </ul>
                
                <p><a href="/auth/reset" style="background: #dc3545; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">🔄 Reset Authentication</a></p>
                <p><a href="/" style="background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">🏠 Return to Main Page</a></p>
            </body>
            </html>
            """, error=error, error_description=error_description)
    
    # Handle successful authorization code
    if auth_code:
        print(f"✅ Authorization code received: {auth_code[:20]}...")
        
        # Attempt to exchange code for tokens
        try:
            if exchange_code_for_tokens(auth_code):
                auth_state['authenticated'] = True
                auth_state['auth_in_progress'] = False
                auth_state['auth_code'] = auth_code
                auth_state['auth_error'] = None
                
                print("✅ Token exchange successful!")
                
                # Start the token refresh daemon
                try:
                    start_enhanced_token_refresh_thread()
                except Exception as e:
                    print(f"⚠️ Warning: Could not start token refresh thread: {e}")
                
                return render_template_string("""
                <html>
                <head><title>✅ Authentication Successful</title></head>
                <body style="font-family: Arial; text-align: center; padding: 50px; background: #d4edda;">
                    <h1 style="color: green;">✅ Authentication Successful!</h1>
                    <p style="font-size: 18px;">🎉 StockX API is now ready to use!</p>
                    <p>✅ Access token is valid</p>
                    <p>✅ Automatic refresh is enabled</p>
                    <p>✅ All systems operational</p>
                    
                    <p style="margin-top: 30px;">
                        <a href="/" style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-size: 16px;">
                            🚀 Start Using the API
                        </a>
                    </p>
                    
                    <script>
                        // Auto-redirect after 5 seconds
                        setTimeout(function() {
                            window.location.href = '/';
                        }, 5000);
                    </script>
                </body>
                </html>
                """)
            else:
                # Token exchange failed
                auth_state['auth_error'] = 'Token exchange failed'
                auth_state['auth_in_progress'] = False
                
                return render_template_string("""
                <html>
                <head><title>❌ Token Exchange Failed</title></head>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1 style="color: red;">❌ Token Exchange Failed</h1>
                    <p>We received the authorization code but couldn't exchange it for tokens.</p>
                    
                    <h2>🔧 What to Try:</h2>
                    <ul style="text-align: left; display: inline-block;">
                        <li>Check your internet connection</li>
                        <li>Try the authentication process again</li>
                        <li>Contact support if the problem persists</li>
                    </ul>
                    
                    <p><a href="/auth/reset" style="background: #dc3545; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">🔄 Try Again</a></p>
                    <p><a href="/" style="background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">🏠 Return to Main Page</a></p>
                </body>
                </html>
                """)
                
        except Exception as e:
            print(f"❌ Exception during token exchange: {e}")
            auth_state['auth_error'] = f'Token exchange error: {str(e)}'
            auth_state['auth_in_progress'] = False
            
            return render_template_string("""
            <html>
            <head><title>❌ Authentication Error</title></head>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1 style="color: red;">❌ Authentication Error</h1>
                <p>An error occurred during authentication:</p>
                <p style="background: #f8d7da; color: #721c24; padding: 10px; border-radius: 5px; display: inline-block;">{{ error }}</p>
                
                <p><a href="/auth/reset" style="background: #dc3545; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">🔄 Try Again</a></p>
                <p><a href="/" style="background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">🏠 Return to Main Page</a></p>
            </body>
            </html>
            """, error=str(e))
    
    # No code and no error - something's wrong
    return render_template_string("""
    <html>
    <head><title>⚠️ Invalid Callback</title></head>
    <body style="font-family: Arial; text-align: center; padding: 50px;">
        <h1 style="color: orange;">⚠️ Invalid OAuth Callback</h1>
        <p>The callback didn't contain the expected parameters.</p>
        <p><a href="/auth/start" style="background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">🔄 Try Authentication Again</a></p>
        <p><a href="/" style="background: #6c757d; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">🏠 Return to Main Page</a></p>
    </body>
    </html>
    """)

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
    is_auth, error_msg, recovery_action = robust_authentication_check()
    auth_state['authenticated'] = is_auth
    if error_msg:
        auth_state['auth_error'] = error_msg
    return redirect(url_for('index'))

@app.route('/search', methods=['POST'])
def search_products():
    """Search for products and display detailed info"""
    is_auth, error_msg, recovery_action = robust_authentication_check()
    if not is_auth:
        flash(f'❌ SEARCH BLOCKED: {error_msg or "Authentication required"}. Please authenticate first.')
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
    
    # ALWAYS check authentication status with robust checking
    auth_status, error_msg, recovery_action = robust_authentication_check()
    auth_state['authenticated'] = auth_status
    if error_msg:
        auth_state['auth_error'] = error_msg
    
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
    
    # VERIFY AUTHENTICATION BEFORE PROCESSING UPLOAD
    is_auth, error_msg, recovery_action = robust_authentication_check()
    if not is_auth:
        flash(f'❌ UPLOAD BLOCKED: {error_msg or "Authentication required"}. Please authenticate first.')
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

@app.route('/simple_test')
def simple_test():
    """Simple WebSocket test page"""
    try:
        with open('simple_test.html', 'r') as f:
            return f.read()
    except FileNotFoundError:
        return "Simple test file not found", 404

@app.route('/debug_main')
def debug_main():
    """Debug main page WebSocket issues"""
    try:
        with open('debug_main.html', 'r') as f:
            return f.read()
    except FileNotFoundError:
        return "Debug main file not found", 404

@app.route('/websocket_test')
def websocket_test():
    """WebSocket test page"""
    try:
        with open('websocket_test.html', 'r') as f:
            return f.read()
    except FileNotFoundError:
        return "WebSocket test file not found", 404

@app.route('/test_streaming')
def test_streaming():
    """New streaming test page"""
    try:
        with open('test_streaming.html', 'r') as f:
            return f.read()
    except FileNotFoundError:
        return "Test streaming file not found", 404

@app.route('/stream/<script_id>')
def stream_output(script_id):
    """Stream output for a specific process using SSE"""
    def generate():
        if script_id in process_outputs:
            # Send all existing output
            for line in process_outputs[script_id]:
                yield f"data: {json.dumps({'line': line, 'status': 'history'})}\n\n"
        
        # Send heartbeat every 30 seconds to keep connection alive
        while script_id in running_processes:
            yield f": heartbeat\n\n"
            time.sleep(30)
    
    return Response(generate(), mimetype='text/event-stream')

@app.route('/working')
def working():
    """Working WebSocket demo page"""
    try:
        with open('working_websocket.html', 'r') as f:
            return f.read()
    except FileNotFoundError:
        return "Working WebSocket file not found", 404

@app.route('/simple')
def simple():
    """Simple polling interface"""
    try:
        with open('simple_polling.html', 'r') as f:
            return f.read()
    except FileNotFoundError:
        return "Simple polling file not found", 404

@app.route('/api/process_output/<script_id>')
def api_process_output(script_id):
    """API endpoint to get process output"""
    if script_id in process_outputs:
        return jsonify({
            'lines': process_outputs[script_id],
            'running': script_id in running_processes
        })
    else:
        return jsonify({
            'lines': [],
            'running': False
        })

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

@app.route('/auth/reset')
def reset_auth():
    """Reset authentication by clearing tokens and starting fresh"""
    global auth_state
    
    try:
        # Clear the token file
        if os.path.exists(TOKEN_FILE):
            # Backup the old token file just in case
            backup_file = TOKEN_FILE + f'.backup.{int(time.time())}'
            os.rename(TOKEN_FILE, backup_file)
            print(f"📋 Backed up old tokens to {backup_file}")
        
        # Reset auth state
        auth_state = {
            'authenticated': False,
            'auth_in_progress': False,
            'auth_code': None,
            'auth_error': None,
            'token_info': None
        }
        
        print("🔄 Authentication reset - cleared all tokens")
        flash('🔄 Authentication reset successfully. Please authenticate again.')
        
    except Exception as e:
        print(f"❌ Error during auth reset: {e}")
        flash(f'❌ Error during reset: {str(e)}')
    
    return redirect(url_for('index'))

def comprehensive_auth_health_check():
    """
    Comprehensive authentication health check and auto-recovery
    Returns: (status, details, actions_taken)
    """
    status = {
        'overall': 'unknown',
        'token_file': 'unknown',
        'token_structure': 'unknown', 
        'api_connectivity': 'unknown',
        'refresh_capability': 'unknown',
        'auto_refresh_thread': 'unknown'
    }
    
    details = []
    actions_taken = []
    
    try:
        # 1. Check token file existence and readability
        if not os.path.exists(TOKEN_FILE):
            status['token_file'] = 'missing'
            details.append("❌ Token file not found - first time setup required")
        else:
            try:
                with open(TOKEN_FILE, 'r') as f:
                    tokens = json.load(f)
                status['token_file'] = 'exists'
                details.append("✅ Token file exists and is readable")
                
                # 2. Check token structure
                required_fields = ['access_token']
                missing_fields = [field for field in required_fields if field not in tokens]
                
                if missing_fields:
                    status['token_structure'] = 'invalid'
                    details.append(f"❌ Token file missing required fields: {missing_fields}")
                else:
                    status['token_structure'] = 'valid'
                    details.append("✅ Token structure is valid")
                    
                    # 3. Check refresh token capability
                    if 'refresh_token' in tokens:
                        status['refresh_capability'] = 'available'
                        details.append("✅ Refresh token available for auto-renewal")
                    else:
                        status['refresh_capability'] = 'unavailable'
                        details.append("⚠️ No refresh token - full re-auth will be needed eventually")
                    
                    # 4. Test API connectivity
                    try:
                        headers = {
                            'Authorization': f'Bearer {tokens["access_token"]}',
                            'x-api-key': STOCKX_API_KEY
                        }
                        
                        response = requests.get(
                            'https://api.stockx.com/v2/catalog/search?query=test&pageSize=1',
                            headers=headers,
                            timeout=10
                        )
                        
                        if response.status_code == 200:
                            status['api_connectivity'] = 'working'
                            details.append("✅ API authentication working perfectly")
                        elif response.status_code == 401:
                            status['api_connectivity'] = 'expired'
                            details.append("🔄 Access token expired - attempting refresh")
                            
                            # Auto-recovery: Try to refresh token
                            if 'refresh_token' in tokens:
                                if refresh_access_token():
                                    status['api_connectivity'] = 'recovered'
                                    details.append("✅ Token refreshed successfully!")
                                    actions_taken.append("Auto-refreshed expired token")
                                else:
                                    status['api_connectivity'] = 'refresh_failed'
                                    details.append("❌ Token refresh failed - full re-auth needed")
                            else:
                                details.append("❌ Cannot refresh - no refresh token available")
                        else:
                            status['api_connectivity'] = 'error'
                            details.append(f"⚠️ API returned HTTP {response.status_code}")
                            
                    except requests.exceptions.Timeout:
                        status['api_connectivity'] = 'timeout'
                        details.append("⚠️ API request timeout - network issues")
                    except requests.exceptions.ConnectionError:
                        status['api_connectivity'] = 'network_error' 
                        details.append("❌ Network connection error")
                    except Exception as e:
                        status['api_connectivity'] = 'exception'
                        details.append(f"❌ API test failed: {str(e)}")
                        
            except json.JSONDecodeError:
                status['token_structure'] = 'corrupted'
                details.append("❌ Token file is corrupted - re-authentication required")
                
                # Auto-recovery: Backup corrupted file
                backup_file = TOKEN_FILE + f'.corrupted.{int(time.time())}'
                try:
                    os.rename(TOKEN_FILE, backup_file)
                    details.append(f"🔄 Backed up corrupted file to {backup_file}")
                    actions_taken.append("Backed up corrupted token file")
                except Exception as e:
                    details.append(f"⚠️ Could not backup corrupted file: {e}")
            except Exception as e:
                status['token_file'] = 'error'
                details.append(f"❌ Error reading token file: {str(e)}")
        
        # 5. Check auto-refresh thread status
        global token_refresh_thread
        if token_refresh_thread and token_refresh_thread.is_alive():
            status['auto_refresh_thread'] = 'running'
            details.append("✅ Auto-refresh daemon is running")
        else:
            status['auto_refresh_thread'] = 'stopped'
            details.append("⚠️ Auto-refresh daemon is not running")
            
            # Auto-recovery: Start the thread if we have valid tokens
            if status['api_connectivity'] in ['working', 'recovered']:
                try:
                    start_enhanced_token_refresh_thread()
                    status['auto_refresh_thread'] = 'started'
                    details.append("🔄 Started auto-refresh daemon")
                    actions_taken.append("Started token refresh daemon")
                except Exception as e:
                    details.append(f"❌ Could not start auto-refresh daemon: {e}")
        
        # 6. Determine overall status
        if status['api_connectivity'] in ['working', 'recovered']:
            status['overall'] = 'healthy'
        elif status['token_file'] == 'missing':
            status['overall'] = 'setup_required'
        elif status['token_structure'] == 'corrupted':
            status['overall'] = 'corrupted'
        elif status['api_connectivity'] == 'expired' and status['refresh_capability'] == 'available':
            status['overall'] = 'refresh_needed'
        elif status['api_connectivity'] in ['refresh_failed', 'error']:
            status['overall'] = 'reauth_required'
        else:
            status['overall'] = 'degraded'
            
    except Exception as e:
        status['overall'] = 'error'
        details.append(f"❌ Health check failed: {str(e)}")
    
    return status, details, actions_taken

@app.route('/auth/health')
def auth_health():
    """Detailed authentication health check endpoint"""
    status, details, actions_taken = comprehensive_auth_health_check()
    
    # Update global auth state based on health check
    global auth_state
    if status['overall'] == 'healthy':
        auth_state['authenticated'] = True
        auth_state['auth_error'] = None
    else:
        auth_state['authenticated'] = False
        auth_state['auth_error'] = f"Health check: {status['overall']}"
    
    return render_template_string("""
    <html>
    <head><title>🏥 Authentication Health Check</title></head>
    <body style="font-family: Arial; padding: 30px; max-width: 900px; margin: 0 auto;">
        <h1>🏥 Authentication Health Check</h1>
        
        <div style="background: {% if status.overall == 'healthy' %}#d4edda{% elif status.overall in ['setup_required', 'refresh_needed'] %}#fff3cd{% else %}#f8d7da{% endif %}; 
                    padding: 15px; border-radius: 8px; margin: 20px 0;">
            <h2>Overall Status: 
                {% if status.overall == 'healthy' %}✅ HEALTHY
                {% elif status.overall == 'setup_required' %}🔧 SETUP REQUIRED
                {% elif status.overall == 'refresh_needed' %}🔄 REFRESH NEEDED
                {% elif status.overall == 'reauth_required' %}🔑 RE-AUTHENTICATION REQUIRED
                {% elif status.overall == 'corrupted' %}💥 CORRUPTED
                {% elif status.overall == 'degraded' %}⚠️ DEGRADED
                {% else %}❌ ERROR
                {% endif %}
            </h2>
        </div>
        
        <h3>📋 Detailed Status:</h3>
        <ul>
        {% for detail in details %}
            <li>{{ detail }}</li>
        {% endfor %}
        </ul>
        
        {% if actions_taken %}
            <h3>⚡ Auto-Recovery Actions Taken:</h3>
            <ul style="color: green;">
            {% for action in actions_taken %}
                <li>✅ {{ action }}</li>
            {% endfor %}
            </ul>
        {% endif %}
        
        <h3>🔧 Recommended Actions:</h3>
        {% if status.overall == 'healthy' %}
            <p style="color: green;">🎉 Everything is working perfectly! No action needed.</p>
        {% elif status.overall == 'setup_required' %}
            <p><a href="/auth/start" style="background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">🔑 Start Authentication Setup</a></p>
        {% elif status.overall == 'refresh_needed' %}
            <p><a href="/auth/start" style="background: #ffc107; color: #212529; padding: 10px 20px; text-decoration: none; border-radius: 5px;">🔄 Refresh Authentication</a></p>
        {% else %}
            <p><a href="/auth/reset" style="background: #dc3545; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-right: 10px;">🔄 Reset & Start Fresh</a>
               <a href="/auth/start" style="background: #28a745; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">🔑 Authenticate Now</a></p>
        {% endif %}
        
        <h3>🔍 Technical Details:</h3>
        <pre style="background: #f8f9fa; padding: 15px; border: 1px solid #dee2e6; border-radius: 5px; overflow-x: auto;">
Token File: {{ status.token_file }}
Token Structure: {{ status.token_structure }}
API Connectivity: {{ status.api_connectivity }}
Refresh Capability: {{ status.refresh_capability }}
Auto-Refresh Thread: {{ status.auto_refresh_thread }}
Overall: {{ status.overall }}

Current URL: {{ current_url }}
Callback URL: {{ callback_url }}
Manual Override: {{ manual_override }}
        </pre>
        
        <div style="margin-top: 30px;">
            <a href="/" style="background: #6c757d; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">🏠 Return to Main Page</a>
            <a href="/auth/health" style="background: #17a2b8; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-left: 10px;">🔄 Refresh Health Check</a>
        </div>
    </body>
    </html>
    """, 
    status=status,
    details=details,
    actions_taken=actions_taken,
    current_url=get_replit_url(),
    callback_url=f"{get_replit_url()}/auth/callback",
    manual_override=MANUAL_CALLBACK_URL or 'Not set'
    )

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
            start_enhanced_token_refresh_thread()
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
