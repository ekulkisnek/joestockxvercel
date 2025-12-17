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
from typing import List, Dict, Optional

app = Flask(__name__)
app.secret_key = 'stockx_tools_secret_key_2025'

# Check if running on Vercel (serverless environment)
IS_VERCEL = os.getenv('VERCEL') == '1' or os.getenv('VERCEL_ENV') is not None

# Initialize SocketIO with production-ready configuration
# Disable SocketIO on Vercel as it's not compatible with serverless
socketio = None
if not IS_VERCEL:
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
        try:
            socketio = SocketIO(
                app, 
                cors_allowed_origins="*",
                async_mode='threading',
                logger=False,
                engineio_logger=False
            )
        except Exception as e2:
            print(f"⚠️ Could not initialize SocketIO: {e2}")
            socketio = None
else:
    print("⚠️ Running on Vercel - SocketIO disabled (not compatible with serverless)")

# Create a no-op socketio object if None (for Vercel compatibility)
if socketio is None:
    class NoOpSocketIO:
        def emit(self, *args, **kwargs):
            pass  # No-op for serverless environments
        def run(self, *args, **kwargs):
            pass  # No-op
        def on(self, *args, **kwargs):
            # Decorator support - returns a no-op decorator
            def decorator(func):
                return func  # Return function unchanged
            return decorator
    socketio = NoOpSocketIO()

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

# StockX OAuth configuration - supports environment variables for Replit deployment
STOCKX_API_KEY = os.getenv('STOCKX_API_KEY', 'GH4A9FkG7E3uaWswtc87U7kw8A4quRsU6ciFtrUp')
STOCKX_CLIENT_ID = os.getenv('STOCKX_CLIENT_ID', 'QyK8U0Xir3L3wQjYtBlLuXpMOLANa5EL')
STOCKX_CLIENT_SECRET = os.getenv('STOCKX_CLIENT_SECRET', 'uqJXWo1oN10iU6qyAiTIap1B0NmuZMsZn6vGp7oO1uK-Ng4-aoSTbRHA5kfNV3Mn')

# Enhanced Replit detection (must be defined before token path resolution)
def is_replit_environment():
    """Check if running in Replit environment"""
    return (
        os.getenv('REPL_ID') is not None or 
        os.getenv('REPLIT_DB_URL') is not None or
        'replit' in os.getcwd().lower() or
        os.path.exists('/home/runner')
    )

def _resolve_token_file_path():
    """Determine where to store tokens. Honors STOCKX_TOKEN_FILE if set.
    On Replit, default to ~/.stockx/tokens_full_scope.json to avoid repo conflicts.
    Locally, default to ./tokens_full_scope.json.
    """
    # Explicit override takes precedence
    env_path = os.getenv('STOCKX_TOKEN_FILE')
    if env_path:
        return env_path
    
    # Prefer hidden home directory on hosted environments
    if is_replit_environment():
        home_dir = os.path.expanduser('~')
        hidden_dir = os.path.join(home_dir, '.stockx')
        return os.path.join(hidden_dir, 'tokens_full_scope.json')
    
    # Fallback: current working directory
    return os.path.join(os.getcwd(), 'tokens_full_scope.json')

TOKEN_FILE = _resolve_token_file_path()

# Manual URL override for OAuth callback (set this if auto-detection fails)
MANUAL_CALLBACK_URL = os.getenv('STOCKX_CALLBACK_URL', None)  # e.g., 'https://your-app.replit.app'

# (moved is_replit_environment above)

# Global auth state
auth_state = {
    'authenticated': False,
    'auth_in_progress': False,
    'auth_code': None,
    'auth_error': None,
    'token_info': None
}

def ensure_token_available():
    """Ensure a usable token file exists by migrating or refreshing via env.
    Returns True if a token becomes available, else False.
    """
    try:
        # Ensure directory for token file exists
        try:
            token_dir = os.path.dirname(TOKEN_FILE)
            if token_dir:
                os.makedirs(token_dir, exist_ok=True)
        except Exception:
            pass

        # If token already exists
        if os.path.exists(TOKEN_FILE):
            return True

        # Try legacy locations migration
        legacy_candidates = [
            os.path.join(os.getcwd(), 'tokens_full_scope.json'),
            os.path.join(os.path.dirname(os.getcwd()), 'tokens_full_scope.json')
        ]
        for candidate in legacy_candidates:
            try:
                if os.path.exists(candidate) and os.path.getsize(candidate) > 0:
                    with open(candidate, 'r') as src:
                        data = src.read()
                    with open(TOKEN_FILE, 'w') as dst:
                        dst.write(data)
                    print(f"🔄 Migrated token file from legacy path: {candidate} → {TOKEN_FILE}")
                    return True
            except Exception as e:
                print(f"⚠️ Token migration from {candidate} failed: {e}")

        # Try environment-provided refresh token
        env_refresh = os.getenv('STOCKX_REFRESH_TOKEN')
        if env_refresh:
            try:
                print("🔄 Attempting token creation via STOCKX_REFRESH_TOKEN env var...")
                data = {
                    'grant_type': 'refresh_token',
                    'refresh_token': env_refresh,
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
                    if 'refresh_token' not in tokens:
                        tokens['refresh_token'] = env_refresh
                    tokens['refreshed_at'] = time.time()
                    with open(TOKEN_FILE, 'w') as f:
                        json.dump(tokens, f, indent=2)
                    print("✅ Created new token file from env refresh token")
                    return True
                else:
                    print(f"❌ Env refresh token attempt failed: {response.status_code}")
            except Exception as e:
                print(f"❌ Error creating token from env refresh token: {e}")

        return False
    except Exception as e:
        print(f"❌ ensure_token_available error: {e}")
        return False

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
    port = os.getenv('PORT', '5000')
    url = f'http://localhost:{port}'
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
            
            # Ensure directory exists before writing
            try:
                token_dir = os.path.dirname(TOKEN_FILE)
                if token_dir:
                    os.makedirs(token_dir, exist_ok=True)
            except Exception:
                pass
            
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
        
        # Ensure directory exists before writing
        try:
            token_dir = os.path.dirname(TOKEN_FILE)
            if token_dir:
                os.makedirs(token_dir, exist_ok=True)
        except Exception:
            pass
        
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

def add_output(script_id: str, message: str):
    """Add output message to process outputs and emit via WebSocket"""
    if script_id not in process_outputs:
        process_outputs[script_id] = []
    
    process_outputs[script_id].append(message)
    
    # Emit via WebSocket
    socketio.emit('process_output', {
        'script_id': script_id,
        'line': message,
        'status': 'running'
    })

# HTML template for the web interface
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>StockX Tools - Web Interface</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    
    <!-- Favicon Configuration -->
    <link rel="icon" type="image/png" href="/static/greengoatlogoiphone.png">
    <link rel="apple-touch-icon" href="/static/greengoatlogoiphone.png">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <meta name="apple-mobile-web-app-title" content="StockX Tools">
    
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
        
        // Progressive Analysis Functionality
        socket.on('progress', function(data) {
            console.log('📊 Progress update:', data);
            updateProgress(data);
        });
        
        socket.on('result', function(data) {
            console.log('✅ Analysis result:', data);
            handleAnalysisResult(data);
        });
        
        socket.on('error', function(data) {
            console.log('❌ Analysis error:', data);
            handleAnalysisError(data);
        });
        
        // Progressive Analysis Form Handler
        document.addEventListener('DOMContentLoaded', function() {
            const progressiveForm = document.getElementById('progressive-analysis-form');
            if (progressiveForm) {
                progressiveForm.addEventListener('submit', function(e) {
                    e.preventDefault();
                    startProgressiveAnalysis();
                });
            }
        });
        
        function startProgressiveAnalysis() {
            const shoeQuery = document.getElementById('progressive_shoe_query').value;
            const size = document.getElementById('progressive_shoe_size').value;
            
            if (!shoeQuery) {
                alert('Please enter a shoe name or SKU');
                return;
            }
            
            // Show progress container
            document.getElementById('progress-container').style.display = 'block';
            document.getElementById('progress-fill').style.width = '0%';
            document.getElementById('progress-text').textContent = 'Starting analysis...';
            document.getElementById('progress-messages').innerHTML = '';
            
            // Disable form
            document.getElementById('progressive-analyze-btn').disabled = true;
            document.getElementById('progressive-analyze-btn').textContent = '🔄 Analyzing...';
            
            // Send analysis request
            socket.emit('analyze_shoe_progressive', {
                shoe_query: shoeQuery,
                size: size
            });
        }
        
        function updateProgress(data) {
            const progressFill = document.getElementById('progress-fill');
            const progressText = document.getElementById('progress-text');
            const progressMessages = document.getElementById('progress-messages');
            
            // Update progress bar
            if (data.progress_percentage) {
                progressFill.style.width = data.progress_percentage + '%';
            }
            
            // Update progress text
            progressText.textContent = data.message;
            
            // Add progress message
            const messageDiv = document.createElement('div');
            messageDiv.style.marginBottom = '5px';
            messageDiv.style.padding = '5px';
            messageDiv.style.borderRadius = '3px';
            messageDiv.style.backgroundColor = '#e9ecef';
            messageDiv.innerHTML = `<strong>${data.step}</strong> ${data.message}`;
            progressMessages.appendChild(messageDiv);
            progressMessages.scrollTop = progressMessages.scrollHeight;
        }
        
        function handleAnalysisResult(data) {
            // Re-enable form
            document.getElementById('progressive-analyze-btn').disabled = false;
            document.getElementById('progressive-analyze-btn').textContent = '🚀 Start Progressive Analysis';
            
            // Show success message
            const progressText = document.getElementById('progress-text');
            progressText.textContent = '✅ Analysis completed successfully!';
            progressText.style.color = '#28a745';
            
            // Create result display
            const progressMessages = document.getElementById('progress-messages');
            const resultDiv = document.createElement('div');
            resultDiv.style.marginTop = '15px';
            resultDiv.style.padding = '15px';
            resultDiv.style.backgroundColor = '#d4edda';
            resultDiv.style.border = '1px solid #c3e6cb';
            resultDiv.style.borderRadius = '5px';
            resultDiv.style.color = '#155724';
            
            if (data.success) {
                resultDiv.innerHTML = `
                    <h4>🎯 Analysis Complete</h4>
                    <p><strong>Query:</strong> ${data.query} (Size: ${data.size})</p>
                    <p><strong>Processing Time:</strong> ${data.processing_time ? data.processing_time.toFixed(2) : 'N/A'}s</p>
                    <p><strong>Status:</strong> ✅ Success</p>
                    ${data.final_recommendation && data.final_recommendation.recommendation ? 
                        `<p><strong>Recommendation:</strong> ${data.final_recommendation.recommendation}</p>` : ''}
                    <button onclick="window.location.href='/advanced_results'" style="background: #17a2b8; color: white; padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer;">
                        📋 View All Results
                    </button>
                `;
            } else {
                resultDiv.style.backgroundColor = '#f8d7da';
                resultDiv.style.border = '1px solid #f5c6cb';
                resultDiv.style.color = '#721c24';
                resultDiv.innerHTML = `
                    <h4>❌ Analysis Failed</h4>
                    <p><strong>Error:</strong> ${data.errors ? data.errors.join(', ') : 'Unknown error'}</p>
                `;
            }
            
            progressMessages.appendChild(resultDiv);
            progressMessages.scrollTop = progressMessages.scrollHeight;
        }
        
        function handleAnalysisError(data) {
            // Re-enable form
            document.getElementById('progressive-analyze-btn').disabled = false;
            document.getElementById('progressive-analyze-btn').textContent = '🚀 Start Progressive Analysis';
            
            // Show error message
            const progressText = document.getElementById('progress-text');
            progressText.textContent = '❌ Analysis failed';
            progressText.style.color = '#dc3545';
            
            // Add error message
            const progressMessages = document.getElementById('progress-messages');
            const errorDiv = document.createElement('div');
            errorDiv.style.marginTop = '15px';
            errorDiv.style.padding = '15px';
            errorDiv.style.backgroundColor = '#f8d7da';
            errorDiv.style.border = '1px solid #f5c6cb';
            errorDiv.style.borderRadius = '5px';
            errorDiv.style.color = '#721c24';
            errorDiv.innerHTML = `<h4>❌ Error</h4><p>${data.message || 'Unknown error occurred'}</p>`;
            
            progressMessages.appendChild(errorDiv);
            progressMessages.scrollTop = progressMessages.scrollHeight;
        }
        
        // Token refresh functionality
        function refreshToken() {
            const button = event.target;
            const originalText = button.innerHTML;
            
            // Show loading state
            button.innerHTML = '🔄 Refreshing...';
            button.disabled = true;
            
            fetch('/refresh-token', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Show success message
                    button.innerHTML = '✅ Refreshed!';
                    button.style.background = '#28a745';
                    
                    // Show success notification
                    showNotification('Token refreshed successfully!', 'success');
                    
                    // Reload page after 2 seconds to show updated token info
                    setTimeout(() => {
                        window.location.reload();
                    }, 2000);
                } else {
                    // Show error message
                    button.innerHTML = '❌ Failed';
                    button.style.background = '#dc3545';
                    
                    // Show error notification
                    showNotification(data.message || 'Token refresh failed', 'error');
                    
                    // Reset button after 3 seconds
                    setTimeout(() => {
                        button.innerHTML = originalText;
                        button.style.background = '#17a2b8';
                        button.disabled = false;
                    }, 3000);
                }
            })
            .catch(error => {
                console.error('Token refresh error:', error);
                button.innerHTML = '❌ Error';
                button.style.background = '#dc3545';
                
                showNotification('Network error during token refresh', 'error');
                
                // Reset button after 3 seconds
                setTimeout(() => {
                    button.innerHTML = originalText;
                    button.style.background = '#17a2b8';
                    button.disabled = false;
                }, 3000);
            });
        }
        
        // Notification system
        function showNotification(message, type) {
            // Remove existing notifications
            const existing = document.querySelector('.notification');
            if (existing) {
                existing.remove();
            }
            
            // Create notification
            const notification = document.createElement('div');
            notification.className = 'notification';
            notification.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                padding: 15px 20px;
                border-radius: 5px;
                color: white;
                font-weight: bold;
                z-index: 1000;
                max-width: 300px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            `;
            
            if (type === 'success') {
                notification.style.background = '#28a745';
            } else if (type === 'error') {
                notification.style.background = '#dc3545';
            } else {
                notification.style.background = '#17a2b8';
            }
            
            notification.textContent = message;
            document.body.appendChild(notification);
            
            // Auto-remove after 5 seconds
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.remove();
                }
            }, 5000);
        }
        
        console.log('WebSocket initialization complete');
    </script>
    <script src="{{ url_for('static', filename='app.js') }}"></script>
</head>
<body>
    <h1>🤖 StockX Tools</h1>
    <p style="margin-top: -6px">Complete StockX API integration with authentication, search, and bulk analysis</p>
    
    {% with messages = get_flashed_messages() %}
        {% if messages %}
            {% for message in messages %}
                <div style="padding: 10px; margin: 10px 0; background: #d4edda; border: 1px solid #c3e6cb; color: #155724; border-radius: 4px;">
                    {{ message }}
                </div>
            {% endfor %}
        {% endif %}
    {% endwith %}
    

    <div class="upload-section">
        <h2>📊 Bulk Analysis Tools</h2>
        <h3>�� Inventory Analysis</h3>
        <!-- Upload CSV Option -->
        <div style="margin: 15px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px;">
            <h4>📁 Upload CSV File</h4>
            <form action="/upload" method="post" enctype="multipart/form-data" style="margin: 10px 0;">
                <input type="hidden" name="script_type" value="inventory">
                <label for="inventory_upload">Upload inventory CSV file:</label><br>
                <input type="file" name="file" id="inventory_upload" accept=".csv" style="margin: 5px 0;"><br>
                <input type="submit" value="Upload & Run Inventory Analysis" class="upload-button">
            </form>
        </div>
        
        <!-- Paste List Option -->
        <div style="margin: 15px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px;">
            <h4>📋 Paste Inventory List</h4>
            <p><em>Copy your inventory from Excel/Google Sheets and paste it here</em></p>
            <form action="/paste_inventory" method="post" style="margin: 10px 0;">
                <label for="pasted_inventory">Paste your inventory list:</label><br>
                <textarea name="inventory_text" id="pasted_inventory" rows="8" cols="60" 
                         placeholder="Jordan 3 white cement 88 - size 11 ($460)
Supreme air max 1 87 white - size 11.5x2, 12 ($210)
Yeezy bone 500 - size 4.5x13, 5x9, 5.5x4 ($185)
White cement 4 - size 8,8.5x2,9.5,10.5,11x8,11.5x3,12x4 ($245)"
                         style="margin: 5px 0; width: 100%; font-family: monospace;"></textarea><br>
                <input type="submit" value="Process Pasted Inventory" class="upload-button">
            </form>
        </div>
        
        <p><em>Both options analyze inventory against StockX market data with Alias pricing insights</em></p>
    </div>

    <div class="search-section">
        <h2>🎯 Advanced Shoe Analysis</h2>
        <p>Get detailed pricing analysis with your specific logic and all calculations shown</p>
        <form action="/advanced_analysis" method="post" style="margin: 10px 0;">
            <label for="advanced_shoe_query">Enter shoe name or SKU:</label><br>
            <input type="text" name="shoe_query" id="advanced_shoe_query" placeholder="Jordan 1 Chicago" required style="width: 300px; padding: 5px; margin: 5px 0;"><br>
            <label for="shoe_size">Size:</label><br>
            <input type="text" name="size" id="shoe_size" placeholder="10" value="10" style="width: 100px; padding: 5px; margin: 5px 0;"><br>
            <input type="submit" value="🎯 Analyze with Pricing Logic" class="search-button" style="background: #dc3545; color: white; padding: 10px 20px; font-weight: bold;">
        </form>
        <p><small><strong>Features:</strong> StockX + GOAT data, sales volume analysis, detailed calculations, automatic result saving</small></p>
        
        <div style="margin: 15px 0;">
            <a href="/advanced_results" style="background: #17a2b8; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px;">
                📋 View All Saved Results
            </a>
        </div>
    </div>
    
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
                <button onclick="refreshToken()" 
                   style="background: #17a2b8; color: white; padding: 8px 16px; border: none; border-radius: 4px; margin-right: 10px; cursor: pointer;">
                    🔄 Refresh Token
                </button>
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
        <p><a href="/tools" style="text-decoration: none;">📚 View Other Tools (Single Shoe, SKU Finder, Sales Volume, Advanced Multi‑Shoe)</a></p>
    </div>
    
    <div class="upload-section">
        <h2>📊 Bulk Analysis Tools</h2>
        

        <h3>�� Inventory Analysis</h3>
        <!-- Upload CSV Option -->
        <div style="margin: 15px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px;">
            <h4>📁 Upload CSV File</h4>
            <form action="/upload" method="post" enctype="multipart/form-data" style="margin: 10px 0;">
                <input type="hidden" name="script_type" value="inventory">
                <label for="inventory_upload">Upload inventory CSV file:</label><br>
                <input type="file" name="file" id="inventory_upload" accept=".csv" style="margin: 5px 0;"><br>
                <input type="submit" value="Upload & Run Inventory Analysis" class="upload-button">
            </form>
        </div>
        
        <!-- Paste List Option -->
        <div style="margin: 15px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px;">
            <h4>📋 Paste Inventory List</h4>
            <p><em>Copy your inventory from Excel/Google Sheets and paste it here</em></p>
            <form action="/paste_inventory" method="post" style="margin: 10px 0;">
                <label for="pasted_inventory">Paste your inventory list:</label><br>
                <textarea name="inventory_text" id="pasted_inventory" rows="8" cols="60" 
                         placeholder="Jordan 3 white cement 88 - size 11 ($460)
Supreme air max 1 87 white - size 11.5x2, 12 ($210)
Yeezy bone 500 - size 4.5x13, 5x9, 5.5x4 ($185)
White cement 4 - size 8,8.5x2,9.5,10.5,11x8,11.5x3,12x4 ($245)"
                         style="margin: 5px 0; width: 100%; font-family: monospace;"></textarea><br>
                <input type="submit" value="Process Pasted Inventory" class="upload-button">
            </form>
        </div>
        
        <p><em>Both options analyze inventory against StockX market data with Alias pricing insights</em></p>
        
        <h3>🔍 Single Shoe Analysis</h3>
        <!-- Single Shoe Analysis -->
        <div style="margin: 15px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px;">
            <h4>🎯 Comprehensive Single Shoe Analysis</h4>
            <p><em>Get complete pricing, sales volume, and market insights for any shoe in one detailed report</em></p>
            <form action="/analyze_single_shoe" method="post" style="margin: 10px 0;">
                <label for="shoe_query">Enter shoe name, SKU, or description:</label><br>
                <input type="text" name="shoe_query" id="shoe_query" 
                       placeholder="e.g., Jordan 1 Chicago, DQ8426-067, Yeezy Boost 350 Cream"
                       style="margin: 5px 0; width: 300px; padding: 5px;" required><br>
                <input type="submit" value="🔍 Analyze This Shoe" class="upload-button">
            </form>
            <p><small><strong>Features:</strong> StockX pricing, Alias insights, sales velocity, size-by-size breakdown, market recommendations</small></p>
        </div>
        
        <h3>🔍 SKU Finder</h3>
        <!-- SKU Finder -->
        <div style="margin: 15px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px;">
            <h4>🔍 Find StockX SKUs</h4>
            <p><em>Paste a list of shoe names and get their corresponding StockX SKUs and official names</em></p>
            <form action="/find_skus" method="post" style="margin: 10px 0;">
                <label for="shoe_text">Paste your shoe list:</label><br>
                <textarea name="shoe_text" id="shoe_text" rows="8" cols="60" 
                         placeholder="Jordan 1 Chicago
Nike Dunk Low Panda
Yeezy Boost 350 Cream
Air Jordan 4 White Cement
Nike Air Max 1"
                         style="margin: 5px 0; width: 100%; font-family: monospace;" required></textarea><br>
                <input type="submit" value="🔍 Find SKUs" class="upload-button">
            </form>
            <p><small><strong>Features:</strong> Smart parsing, StockX SKU lookup, official name matching, CSV export format, success rate tracking</small></p>
        </div>
        
        <h3>📈 Sales Volume Analysis</h3>
        <!-- Sales Volume CSV Upload -->
        <div style="margin: 15px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px;">
            <h4>📊 Upload CSV for Sales Volume Analysis</h4>
            <p><em>Analyze sales velocity and volume data for your shoe inventory using Alias API</em></p>
            <form action="/upload" method="post" enctype="multipart/form-data" style="margin: 10px 0;">
                <input type="hidden" name="script_type" value="sales_volume">
                <label for="sales_volume_upload">Upload CSV file with shoe names/SKUs:</label><br>
                <input type="file" name="file" id="sales_volume_upload" accept=".csv" style="margin: 5px 0;"><br>
                <input type="submit" value="Upload & Run Sales Volume Analysis" class="upload-button">
            </form>
            <p><small><strong>Features:</strong> Sales velocity per day, total sales counts, price analysis, reliability indicators, duplicate detection</small></p>
        </div>
    </div>
    
    <div class="results-section">
        <h2>📁 Results & Downloads</h2>
        <p><strong>Your processed files are saved in these locations:</strong></p>
        <ul>
            <li><strong>uploads/</strong> - Your uploaded CSV files and analysis results</li>
            <li><strong>pricing_tools/</strong> - Analysis output files</li>
        </ul>
        <p><strong>Available Analysis Types:</strong></p>
        <ul>
            <li>📊 <strong>Inventory Analysis:</strong> StockX pricing with Alias data (stockx_enhanced_*.csv)</li>
            <li>📈 <strong>Sales Volume Analysis:</strong> Sales velocity and volume data (sales_volume_analysis_*.csv)</li>
            <li>🔍 <strong>Single Shoe Analysis:</strong> Comprehensive reports displayed directly on screen</li>
            <li>🔍 <strong>SKU Finder:</strong> Find StockX SKUs for shoe names (sku_finder_report_*.txt, sku_finder_results_*.csv)</li>
        </ul>
        <p><a href="/downloads" style="padding: 5px 10px; background: #17a2b8; color: white; text-decoration: none; border-radius: 4px;">View & Download All Results</a></p>
        <p><em>⏱️ Processing can take several minutes. Your files remain available even if you close the browser.</em></p>
    </div>
    
    {% if running_processes %}
    <hr>
    
    <div class="running-processes">
        <h2>🔄 Running Processes</h2>
        {% for script_id in running_processes %}
            <div style="margin: 10px 0; padding: 10px; border: 1px solid #ddd; background: #f9f9f9;">
                <span class="running-indicator">⏳ {{ script_id }} is running...</span>
                <button onclick="stopProcess('{{ script_id }}')" 
                        style="background: #dc3545; color: white; border: none; padding: 4px 8px; margin-left: 10px; cursor: pointer;">
                    Stop Process
                </button>
            </div>
        {% endfor %}
        <p><small>Real-time streaming updates via WebSocket</small></p>
    </div>
    {% endif %}
    
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
                    <pre style="max-height: 300px; overflow-y: auto; background: #f5f5f5; padding: 10px; border: 1px solid #ddd; border-radius: 4px; white-space: pre-wrap; display: flex; flex-direction: column-reverse;">{{ output.content }}</pre>
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
        
        if script_type == 'inventory':
            command = f'python3 inventory_stockx_analyzer.py "../uploads/{filename}"'
            working_dir = 'pricing_tools'
        elif script_type == 'sales_volume':
            command = f'python3 sales_volume_analyzer.py "../uploads/{filename}"'
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

@app.route('/paste_inventory', methods=['POST'])
def paste_inventory():
    """Handle pasted inventory list - REQUIRES REAL AUTHENTICATION"""
    inventory_text = request.form.get('inventory_text', '').strip()
    
    if not inventory_text:
        flash('No inventory text provided')
        return redirect(url_for('index'))
    
    # VERIFY AUTHENTICATION BEFORE PROCESSING
    is_auth, error_msg, recovery_action = robust_authentication_check()
    if not is_auth:
        flash(f'❌ PASTE PROCESSING BLOCKED: {error_msg or "Authentication required"}. Please authenticate first.')
        return redirect(url_for('index'))
    
    # Save pasted text to a temporary file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{timestamp}_pasted_inventory.txt"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(inventory_text)
    
    flash(f'Pasted inventory saved: {filename}')
    
    # Auto-run the script with pasted list option
    script_id = f"paste_inventory_{datetime.now().strftime('%H%M%S')}"
    command = f'python3 inventory_stockx_analyzer.py --list "../uploads/{filename}"'
    working_dir = 'pricing_tools'
    
    # Start script in background thread
    thread = threading.Thread(
        target=run_script_async,
        args=(script_id, command, working_dir)
    )
    thread.daemon = True
    thread.start()
    
    return redirect(url_for('index'))

@app.route('/analyze_single_shoe', methods=['POST'])
def analyze_single_shoe():
    """Handle single shoe analysis - REQUIRES AUTHENTICATION"""
    shoe_query = request.form.get('shoe_query', '').strip()
    
    if not shoe_query:
        flash('Please enter a shoe name or SKU')
        return redirect(url_for('index'))
    
    # VERIFY AUTHENTICATION BEFORE PROCESSING
    is_auth, error_msg, recovery_action = robust_authentication_check()
    if not is_auth:
        flash(f'❌ ANALYSIS BLOCKED: {error_msg or "Authentication required"}. Please authenticate first.')
        return redirect(url_for('index'))
    
    try:
        # Import and run single shoe analyzer
        sys.path.append(os.path.join(os.getcwd(), 'pricing_tools'))
        from single_shoe_analyzer import SingleShoeAnalyzer
        
        analyzer = SingleShoeAnalyzer()
        result = analyzer.analyze_single_shoe(shoe_query)
        
        # Generate comprehensive HTML response
        return render_single_shoe_analysis(result)
        
    except Exception as e:
        flash(f'Analysis error: {str(e)}')
        return redirect(url_for('index'))

@app.route('/find_skus', methods=['POST'])
def find_skus():
    """Handle SKU finder - REQUIRES AUTHENTICATION"""
    shoe_text = request.form.get('shoe_text', '').strip()
    
    if not shoe_text:
        flash('Please paste your shoe list')
        return redirect(url_for('index'))
    
    # VERIFY AUTHENTICATION BEFORE PROCESSING
    is_auth, error_msg, recovery_action = robust_authentication_check()
    if not is_auth:
        flash(f'❌ SKU FINDER BLOCKED: {error_msg or "Authentication required"}. Please authenticate first.')
        return redirect(url_for('index'))
    
    try:
        # Create script ID for tracking
        script_id = f"sku_finder_{datetime.now().strftime('%H%M%S')}"
        
        # Import and run SKU finder
        sys.path.append(os.path.join(os.getcwd(), 'pricing_tools'))
        from sku_finder import SKUFinder
        
        # Initialize process tracking
        running_processes[script_id] = True
        process_outputs[script_id] = []
        
        def run_sku_finder():
            try:
                add_output(script_id, "🔍 SKU FINDER STARTED")
                add_output(script_id, f"📋 Processing {len(shoe_text.split(chr(10)))} lines...")
                
                # Initialize SKU finder with error handling
                try:
                    finder = SKUFinder()
                    add_output(script_id, "✅ SKU Finder initialized successfully")
                except Exception as init_error:
                    add_output(script_id, f"❌ Failed to initialize SKU Finder: {init_error}")
                    return
                
                # Parse the shoe list
                try:
                    shoes = finder.parse_shoe_list(shoe_text)
                    add_output(script_id, f"📋 Parsed {len(shoes)} shoes from input")
                except Exception as parse_error:
                    add_output(script_id, f"❌ Failed to parse shoe list: {parse_error}")
                    return
                
                # Find SKUs with timeout protection
                add_output(script_id, "🔍 Starting SKU search process...")
                try:
                    results = finder.find_skus(shoes)
                    add_output(script_id, "✅ SKU search completed successfully")
                except Exception as search_error:
                    add_output(script_id, f"❌ SKU search failed: {search_error}")
                    return
                
                # Generate report
                add_output(script_id, "📊 Generating report...")
                try:
                    report = finder.generate_report(results)
                    add_output(script_id, "✅ Report generated successfully")
                except Exception as report_error:
                    add_output(script_id, f"❌ Failed to generate report: {report_error}")
                    return
                
                # Save report to file
                try:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    output_file = f"sku_finder_report_{timestamp}.txt"
                    output_path = os.path.join('pricing_tools', output_file)
                    
                    with open(output_path, 'w') as f:
                        f.write(report)
                    
                    # Also save as CSV for easy download
                    csv_file = f"sku_finder_results_{timestamp}.csv"
                    csv_path = os.path.join('pricing_tools', csv_file)
                    
                    # Generate CSV with StockX links
                    csv_content = finder.generate_csv_report(results)
                    with open(csv_path, 'w', encoding='utf-8') as f:
                        f.write(csv_content)
                    
                    add_output(script_id, f"📁 Report saved: {output_file}")
                    add_output(script_id, f"📊 CSV results saved: {csv_file}")
                    add_output(script_id, f"🔗 StockX links included in CSV")
                except Exception as save_error:
                    add_output(script_id, f"❌ Failed to save report: {save_error}")
                
                add_output(script_id, "✅ SKU FINDER COMPLETED")
                add_output(script_id, "")
                add_output(script_id, report)
                
            except Exception as e:
                add_output(script_id, f"❌ SKU Finder error: {str(e)}")
                import traceback
                add_output(script_id, f"🔍 Error details: {traceback.format_exc()}")
            finally:
                running_processes.pop(script_id, None)
        
        # Start SKU finder in background thread
        thread = threading.Thread(target=run_sku_finder)
        thread.daemon = True
        thread.start()
        
        flash(f'🔍 SKU Finder started! Check the outputs section for results.')
        return redirect(url_for('index'))
        
    except Exception as e:
        flash(f'SKU Finder error: {str(e)}')
        return redirect(url_for('index'))

@app.route('/advanced_analysis', methods=['POST'])
def advanced_analysis():
    """Handle advanced shoe analysis with pricing logic - REQUIRES AUTHENTICATION"""
    shoe_query = request.form.get('shoe_query', '').strip()
    size = request.form.get('size', '10').strip()
    
    if not shoe_query:
        flash('Please enter a shoe name or SKU')
        return redirect(url_for('index'))
    
    # VERIFY AUTHENTICATION BEFORE PROCESSING
    is_auth, error_msg, recovery_action = robust_authentication_check()
    if not is_auth:
        flash(f'❌ ANALYSIS BLOCKED: {error_msg or "Authentication required"}. Please authenticate first.')
        return redirect(url_for('index'))
    
    try:
        # Import and run advanced shoe analyzer
        sys.path.append(os.path.join(os.getcwd(), 'pricing_tools'))
        from advanced_shoe_analyzer import AdvancedShoeAnalyzer
        
        analyzer = AdvancedShoeAnalyzer()
        result = analyzer.analyze_shoe_with_pricing_logic(shoe_query, size)
        
        # Generate comprehensive HTML response
        return render_advanced_analysis(result)
        
    except Exception as e:
        flash(f'Advanced analysis error: {str(e)}')
        return redirect(url_for('index'))

@app.route('/advanced_results')
def advanced_results():
    """Display all saved advanced analysis results"""
    try:
        # Import analyzer to get results
        sys.path.append(os.path.join(os.getcwd(), 'pricing_tools'))
        from advanced_shoe_analyzer import AdvancedShoeAnalyzer
        
        analyzer = AdvancedShoeAnalyzer()
        results = analyzer.get_all_results()
        
        return render_advanced_results_list(results)
        
    except Exception as e:
        flash(f'Error loading results: {str(e)}')
        return redirect(url_for('index'))

@app.route('/tools')
def other_tools():
    """Subpage for auxiliary tools to declutter the main page"""
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>📚 Tools</title>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .card { border: 1px solid #ddd; border-radius: 6px; padding: 16px; margin-bottom: 16px; }
            .btn { display: inline-block; padding: 8px 16px; background: #007bff; color: #fff; text-decoration: none; border-radius: 4px; }
            .btn-secondary { background: #17a2b8; }
        </style>
    </head>
    <body>
        <h1>📚 Other Tools</h1>
        <p><a href="/" class="btn">← Back to Main</a></p>

        <div class="card">
            <h2>🔍 Single Shoe Analysis</h2>
            <h3>🎯 Comprehensive Single Shoe Analysis</h3>
            <p>Get complete pricing, sales volume, and market insights for any shoe in one detailed report</p>
            <form action="/advanced_analysis" method="post" style="margin: 10px 0;">
                <label for="advanced_shoe_query">Enter shoe name, SKU, or description:</label><br>
                <input type="text" name="shoe_query" id="advanced_shoe_query" placeholder="e.g., Jordan 1 Chicago, DQ8426-067, Yeezy Boost 350 Cream" style="width: 420px; padding: 6px;" required>
                <label for="shoe_size" style="margin-left: 10px;">Size:</label>
                <input type="text" name="size" id="shoe_size" placeholder="10" value="10" style="width: 80px; padding: 6px;">
                <button type="submit" class="btn" style="margin-left: 10px;">Run Analysis</button>
            </form>
        </div>

        <div class="card">
            <h2>🔍 SKU Finder</h2>
            <h3>🔍 Find StockX SKUs</h3>
            <p>Paste a list of shoe names and get their corresponding StockX SKUs and official names</p>
            <form action="/find_skus" method="post">
                <textarea name="shoe_text" rows="8" cols="60" placeholder="Jordan 1 Chicago\nNike Dunk Low Panda\nYeezy Boost 350 Cream\nAir Jordan 4 White Cement\nNike Air Max 1" style="width: 100%; font-family: monospace;"></textarea><br>
                <button type="submit" class="btn">Find SKUs</button>
            </form>
            <p><small>Features: Smart parsing, StockX SKU lookup, official name matching, CSV export format, success rate tracking</small></p>
        </div>

        <div class="card">
            <h2>📈 Sales Volume Analysis</h2>
            <h3>📊 Upload CSV for Sales Volume Analysis</h3>
            <p>Analyze sales velocity and volume data for your shoe inventory using Alias API</p>
            <form action="/upload" method="post" enctype="multipart/form-data">
                <input type="hidden" name="script_type" value="sales_volume">
                <label for="sales_volume_upload">Upload CSV file with shoe names/SKUs:</label><br>
                <input type="file" name="file" id="sales_volume_upload" accept=".csv" style="margin: 5px 0;">
                <button type="submit" class="btn">Run Sales Volume</button>
            </form>
            <p><small>Features: Sales velocity per day, total sales counts, price analysis, reliability indicators, duplicate detection</small></p>
        </div>

        <div class="card">
            <h2>📚 Advanced Multi‑Shoe Analysis</h2>
            <p>Upload a sheet or paste a list to run the same advanced logic across multiple shoes.</p>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                <div style="border: 1px solid #ddd; padding: 12px; border-radius: 6px;">
                    <h4>📁 Upload CSV</h4>
                    <form action="/advanced_multi_upload" method="post" enctype="multipart/form-data" style="margin: 10px 0;">
                        <label for="advanced_multi_upload">Upload CSV with shoe and size columns:</label><br>
                        <input type="file" name="file" id="advanced_multi_upload" accept=".csv" style="margin: 5px 0;"><br>
                        <button type="submit" class="btn">Run Advanced Multi‑Shoe</button>
                    </form>
                    <p><small>Flexible column detection: name/SKU, size, price, condition.</small></p>
                </div>
                <div style="border: 1px solid #ddd; padding: 12px; border-radius: 6px;">
                    <h4>📋 Paste List</h4>
                    <form action="/advanced_multi_paste" method="post" style="margin: 10px 0;">
                        <label for="advanced_multi_inventory_text">Paste your list:</label><br>
                        <textarea name="advanced_multi_inventory_text" id="advanced_multi_inventory_text" rows="8" cols="60" 
                                 placeholder="DQ8426 067 - sz12 x2\nJordan 1 Retro High OG 'Royal Reimagined' - sz10 ($235)\nDD1391 100 - sz10.5" 
                                 style="margin: 5px 0; width: 100%; font-family: monospace;"></textarea><br>
                        <button type="submit" class="btn">Run Advanced Multi‑Shoe</button>
                    </form>
                    <p><small>SKU and name formats supported; sizes like sz10, 10W, 5Y, etc.</small></p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """)

@app.route('/advanced_multi_upload', methods=['POST'])
def advanced_multi_upload():
    """Upload CSV and run advanced analysis for multiple shoes"""
    if 'file' not in request.files:
        flash('No file selected')
        return redirect(url_for('index'))
    file = request.files['file']
    if file.filename == '':
        flash('No file selected')
        return redirect(url_for('index'))

    # VERIFY AUTHENTICATION BEFORE PROCESSING
    is_auth, error_msg, _ = robust_authentication_check()
    if not is_auth:
        flash(f'❌ MULTI ANALYSIS BLOCKED: {error_msg or "Authentication required"}. Please authenticate first.')
        return redirect(url_for('index'))

    try:
        # Save uploaded file
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Parse items using inventory analyzer (for normalization and extraction)
        sys.path.append(os.path.join(os.getcwd(), 'pricing_tools'))
        from inventory_stockx_analyzer import InventoryStockXAnalyzer
        from advanced_shoe_analyzer import AdvancedShoeAnalyzer

        inv = InventoryStockXAnalyzer()
        items = inv.parse_csv_flexible(filepath)

        if not items:
            flash('❌ No valid rows detected in CSV')
            return redirect(url_for('index'))

        analyzer = AdvancedShoeAnalyzer()
        results = []
        for item in items:
            shoe_query = item.shoe_name
            size = item.size or '10'
            try:
                res = analyzer.analyze_shoe_with_pricing_logic(shoe_query, size)
                results.append(res)
            except Exception as e:
                results.append({'success': False, 'query': shoe_query, 'size': size, 'errors': [str(e)], 'timestamp': datetime.now().isoformat()})

        return render_advanced_multi_analysis(results)

    except Exception as e:
        flash(f'Advanced multi analysis error: {str(e)}')
        return redirect(url_for('index'))

@app.route('/advanced_multi_paste', methods=['POST'])
def advanced_multi_paste():
    """Paste list and run advanced analysis for multiple shoes"""
    text = request.form.get('advanced_multi_inventory_text', '').strip()
    if not text:
        flash('No list provided')
        return redirect(url_for('index'))

    # VERIFY AUTHENTICATION BEFORE PROCESSING
    is_auth, error_msg, _ = robust_authentication_check()
    if not is_auth:
        flash(f'❌ MULTI ANALYSIS BLOCKED: {error_msg or "Authentication required"}. Please authenticate first.')
        return redirect(url_for('index'))

    try:
        # Use inventory analyzer's pasted list parser
        sys.path.append(os.path.join(os.getcwd(), 'pricing_tools'))
        from inventory_stockx_analyzer import InventoryStockXAnalyzer
        from advanced_shoe_analyzer import AdvancedShoeAnalyzer

        inv = InventoryStockXAnalyzer()
        items = inv.parse_pasted_list(text)

        if not items:
            flash('❌ No valid items detected in pasted list')
            return redirect(url_for('index'))

        analyzer = AdvancedShoeAnalyzer()
        results = []
        for item in items:
            shoe_query = item.shoe_name
            size = item.size or '10'
            try:
                res = analyzer.analyze_shoe_with_pricing_logic(shoe_query, size)
                results.append(res)
            except Exception as e:
                results.append({'success': False, 'query': shoe_query, 'size': size, 'errors': [str(e)], 'timestamp': datetime.now().isoformat()})

        return render_advanced_multi_analysis(results)

    except Exception as e:
        flash(f'Advanced multi analysis error: {str(e)}')
        return redirect(url_for('index'))

@app.route('/advanced_result/<timestamp>')
def view_advanced_result(timestamp):
    """View a specific advanced analysis result"""
    try:
        # Import analyzer to get specific result
        sys.path.append(os.path.join(os.getcwd(), 'pricing_tools'))
        from advanced_shoe_analyzer import AdvancedShoeAnalyzer
        
        analyzer = AdvancedShoeAnalyzer()
        results = analyzer.get_all_results()
        
        # Find the specific result
        target_result = None
        for result in results:
            if result.get('timestamp', '').replace(':', '').replace('-', '').replace('T', '').replace('.', '') == timestamp:
                target_result = result
                break
        
        if target_result:
            return render_advanced_analysis(target_result)
        else:
            flash('Result not found')
            return redirect(url_for('advanced_results'))
        
    except Exception as e:
        flash(f'Error loading result: {str(e)}')
        return redirect(url_for('advanced_results'))

@app.route('/delete_advanced_result/<timestamp>', methods=['POST'])
def delete_advanced_result(timestamp):
    """Delete a specific advanced analysis result"""
    try:
        # Import analyzer to delete result
        sys.path.append(os.path.join(os.getcwd(), 'pricing_tools'))
        from advanced_shoe_analyzer import AdvancedShoeAnalyzer
        
        analyzer = AdvancedShoeAnalyzer()
        success = analyzer.delete_result(timestamp)
        
        if success:
            flash('Result deleted successfully')
        else:
            flash('Failed to delete result')
        
        return redirect(url_for('advanced_results'))
        
    except Exception as e:
        flash(f'Error deleting result: {str(e)}')
        return redirect(url_for('advanced_results'))

@app.route('/generate_alternatives/<timestamp>', methods=['POST'])
def generate_alternatives(timestamp):
    """Generate alternatives for a specific result"""
    try:
        # Import analyzer to generate alternatives
        sys.path.append(os.path.join(os.getcwd(), 'pricing_tools'))
        from advanced_shoe_analyzer import AdvancedShoeAnalyzer
        
        analyzer = AdvancedShoeAnalyzer()
        alternatives = analyzer.generate_alternatives_for_result(timestamp)
        
        if 'error' in alternatives:
            flash(f'Error generating alternatives: {alternatives["error"]}')
        else:
            flash('Alternatives generated successfully')
        
        return redirect(url_for('view_advanced_result', timestamp=timestamp))
        
    except Exception as e:
        flash(f'Error generating alternatives: {str(e)}')
        return redirect(url_for('advanced_results'))

def render_advanced_analysis(result: dict) -> str:
    """Render comprehensive advanced shoe analysis results with detailed calculations"""
    
    if not result.get('success'):
        error_msg = ', '.join(result.get('errors', ['Unknown error']))
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>❌ Advanced Analysis Failed</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .error {{ color: #d32f2f; background: #ffebee; padding: 15px; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <h1>❌ Advanced Analysis Failed</h1>
            <div class="error">
                <strong>Query:</strong> {result.get('query', 'Unknown')}<br>
                <strong>Size:</strong> {result.get('size', 'Unknown')}<br>
                <strong>Error:</strong> {error_msg}
            </div>
            <p><a href="/">← Back to Main Page</a></p>
        </body>
        </html>
        """
    
    # Extract data for rendering
    query = result.get('query', 'Unknown Shoe')
    size = result.get('size', 'Unknown')
    calculations = result.get('calculations', {})
    recommendation = result.get('final_recommendation', {})
    raw_data = result.get('raw_data', {})
    
    # Calculate profit analysis
    profit_data = calculate_profit_analysis(result)
    
    # Build comprehensive HTML response with detailed calculations
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>🎯 Advanced Analysis: {query}</title>
        <style>
            body {{ 
                font-family: 'Segoe UI', Arial, sans-serif; 
                margin: 0; 
                padding: 20px;
                line-height: 1.6;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
            }}
            .container {{ 
                max-width: 1200px; 
                margin: 0 auto; 
                background: white; 
                border-radius: 15px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.3);
                overflow: hidden;
            }}
            .header {{ 
                background: linear-gradient(135deg, #2c3e50, #34495e);
                color: white; 
                padding: 30px; 
                text-align: center;
            }}
            .header h1 {{ margin: 0; font-size: 2.5em; }}
            .header h2 {{ margin: 10px 0 0 0; font-weight: 300; opacity: 0.9; }}
            
            .content {{ padding: 20px; }}
            
            .recommendation-section {{ 
                background: linear-gradient(135deg, #27ae60, #2ecc71);
                color: white;
                padding: 30px;
                margin: 20px 0;
                border-radius: 15px;
                text-align: center;
                box-shadow: 0 8px 25px rgba(39, 174, 96, 0.3);
                border: 2px solid rgba(255,255,255,0.2);
            }}
            
            .recommendation {{ 
                font-size: 2.2em; 
                font-weight: bold; 
                padding: 25px; 
                border-radius: 12px;
                margin: 25px 0;
                text-align: center;
                box-shadow: 0 4px 15px rgba(0,0,0,0.2);
                border: 3px solid rgba(255,255,255,0.3);
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
            }}
            .rec-buy {{ 
                background: linear-gradient(135deg, #27ae60, #2ecc71); 
                color: white;
                animation: pulse 2s infinite;
            }}
            .rec-no-buy {{ 
                background: linear-gradient(135deg, #e74c3c, #c0392b); 
                color: white;
            }}
            
            @keyframes pulse {{
                0% {{ transform: scale(1); }}
                50% {{ transform: scale(1.02); }}
                100% {{ transform: scale(1); }}
            }}
            
            .calculation-step {{ 
                margin: 30px 0; 
                padding: 25px; 
                background: #f8f9fa;
                border-radius: 12px;
                border-left: 5px solid #3498db;
            }}
            .calculation-step h3 {{ 
                margin-top: 0; 
                color: #2c3e50;
                font-size: 1.3em;
            }}
            
            .calculation-detail {{ 
                background: white; 
                padding: 15px; 
                border-radius: 8px; 
                margin: 10px 0;
                border: 1px solid #ddd;
            }}
            
            .metric {{ 
                display: inline-block;
                background: #e7f3ff; 
                padding: 10px 15px; 
                border-radius: 8px;
                margin: 5px;
                font-weight: bold;
            }}
            
            .back-link {{ 
                position: fixed; 
                top: 30px; 
                right: 30px; 
                background: linear-gradient(135deg, #e74c3c, #c0392b);
                color: white; 
                padding: 12px 20px; 
                text-decoration: none; 
                border-radius: 25px;
                box-shadow: 0 4px 15px rgba(231, 76, 60, 0.3);
                font-weight: bold;
                transition: transform 0.2s;
                z-index: 1000;
            }}
            .back-link:hover {{ 
                transform: scale(1.05);
                box-shadow: 0 6px 20px rgba(231, 76, 60, 0.4);
            }}
            
            .confidence-high {{ border-left-color: #27ae60; }}
            .confidence-medium {{ border-left-color: #f39c12; }}
            .confidence-low {{ border-left-color: #e74c3c; }}
            
            .math-formula {{ 
                background: #f8f9fa;
                border: 2px solid #3498db;
                border-radius: 8px;
                padding: 15px;
                margin: 10px 0;
                font-family: monospace;
                font-size: 1.1em;
            }}
        </style>
    </head>
    <body>
        <a href="/" class="back-link">← Back to Main</a>
        
        <div class="container">
            <div class="header">
                <h1>🎯 Advanced Shoe Analysis</h1>
                <h2>{query} - Size {size}</h2>
                
                <!-- Platform Names Section -->
                <div style="background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                        <div style="text-align: center;">
                            <h3 style="color: #ffd700; margin: 0 0 10px 0;">📈 StockX Found:</h3>
                            <div style="font-size: 1.1em; font-weight: bold; color: #4CAF50;">
                                {raw_data.get('stockx', {}).get('product_name', 'Not found')}
                            </div>
                            <div style="font-size: 0.9em; opacity: 0.8; margin-top: 5px;">
                                SKU: {raw_data.get('stockx', {}).get('sku', 'N/A')}
                            </div>
                        </div>
                        <div style="text-align: center;">
                            <h3 style="color: #ffd700; margin: 0 0 10px 0;">🎯 Alias/GOAT Found:</h3>
                            <div style="font-size: 1.1em; font-weight: bold; color: #2196F3;">
                                {raw_data.get('alias', {}).get('catalog_match', {}).get('name', 'Not found')}
                            </div>
                            <div style="font-size: 0.9em; opacity: 0.8; margin-top: 5px;">
                                SKU: {raw_data.get('alias', {}).get('catalog_match', {}).get('sku', 'N/A')}
                            </div>
                        </div>
                    </div>
                </div>
                
                <p>Analysis completed at {datetime.fromisoformat(result.get('timestamp', '')).strftime('%Y-%m-%d %H:%M:%S')} | Processing Time: {result.get('processing_time', 0)}s | {get_confidence_emoji(recommendation.get('confidence', 'Unknown'))} Confidence: {recommendation.get('confidence', 'Unknown')}</p>
            </div>
            
            <div class="content">
                <!-- Final Recommendation -->
                <div class="recommendation-section">
                    <h2>🎯 FINAL RECOMMENDATION</h2>
                    <div class="recommendation {get_advanced_rec_class(recommendation.get('action', ''))}">
                        {recommendation.get('recommendation', 'No recommendation available')}
                    </div>
                    
                    {get_confidence_warning_section(recommendation.get('confidence', 'Unknown'), result) if 'low' in recommendation.get('confidence', '').lower() else ''}
                </div>
                
                <!-- Profit Analysis Section -->
                <div class="calculation-step" style="background: #f8f9fa; border-left: 5px solid #28a745;">
                    <h3 style="color: #2c3e50; font-size: 1.5em; text-align: center; margin-bottom: 20px;">💰 PROFIT ANALYSIS</h3>
                    
                    <div style="background: white; padding: 15px; border-radius: 8px; border: 1px solid #e9ecef;">
                        <!-- GOAT Lowest Ask Profit -->
                        <div style="margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #e9ecef;">
                            <h4 style="color: #2c3e50; margin: 0 0 10px 0; font-size: 1.2em;">🎯 Selling for GOAT Lowest Ask</h4>
                            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px;">
                                <div style="display: flex; align-items: center;">
                                    <span style="font-size: 1.8em; font-weight: bold; color: #28a745; margin-right: 15px;">${profit_data['actual_profit']:.2f}</span>
                                    <span style="font-size: 1.1em; color: #6c757d; font-weight: bold;">{profit_data['profit_percentage']:.1f}% Return</span>
                                </div>
                                <div style="font-size: 0.9em; color: #6c757d;">
                                    Receiving: <span style="color: #28a745; font-weight: bold;">${profit_data['after_fees_amount']:.2f}</span>
                                </div>
                            </div>
                        </div>
                        
                        <!-- GOAT Consignment Profit -->
                        <div style="margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #e9ecef;">
                            <h4 style="color: #2c3e50; margin: 0 0 10px 0; font-size: 1.2em;">📦 Selling for GOAT Consignment</h4>
                            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px;">
                                <div style="display: flex; align-items: center;">
                                    <span style="font-size: 1.8em; font-weight: bold; color: #28a745; margin-right: 15px;">${profit_data['consignment_actual_profit']:.2f}</span>
                                    <span style="font-size: 1.1em; color: #6c757d; font-weight: bold;">{profit_data['consignment_profit_percentage']:.1f}% Return</span>
                                </div>
                                <div style="font-size: 0.9em; color: #6c757d;">
                                    Receiving: <span style="color: #28a745; font-weight: bold;">${profit_data['consignment_after_fees']:.2f}</span>
                                </div>
                            </div>
                        </div>
                        
                        <!-- StockX Ask Profit -->
                        <div style="margin-bottom: 10px;">
                            <h4 style="color: #2c3e50; margin: 0 0 10px 0; font-size: 1.2em;">📈 Selling for StockX Ask</h4>
                            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px;">
                                <div style="display: flex; align-items: center;">
                                    <span style="font-size: 1.8em; font-weight: bold; color: #28a745; margin-right: 15px;">${profit_data['stockx_actual_profit']:.2f}</span>
                                    <span style="font-size: 1.1em; color: #6c757d; font-weight: bold;">{profit_data['stockx_profit_percentage']:.1f}% Return</span>
                                </div>
                                <div style="font-size: 0.9em; color: #6c757d;">
                                    Receiving: <span style="color: #28a745; font-weight: bold;">${profit_data['stockx_after_fees']:.2f}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Summary Note -->
                    <div style="background: #e7f3ff; padding: 10px; border-radius: 6px; margin-top: 15px; border: 1px solid #b3d9ff; text-align: center;">
                        <div style="font-size: 0.9em; color: #0056b3; font-weight: bold;">
                            💡 Actual Profit = Receiving Amount - Buy Price (${calculations.get('step_6_final_decision', {}).get('final_price', 'N/A')})
                        </div>
                    </div>
                </div>
                
                <!-- Key Pricing Information -->
                <div class="calculation-step" style="background: linear-gradient(135deg, #667eea, #764ba2); color: white; border-left: 5px solid #ffd700;">
                    <h3 style="color: white; font-size: 1.5em; text-align: center; margin-bottom: 25px;">💰 KEY PRICING INFORMATION</h3>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-top: 20px;">
                        <div style="background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; text-align: center;">
                            <h4 style="color: #ffd700; margin: 0 0 10px 0; font-size: 1.2em;">📈 StockX Bid</h4>
                            <div style="font-size: 2em; font-weight: bold; color: #ffffff;">${calculations.get('step_1_stockx_analysis', {}).get('stockx_bid', 'N/A')}</div>
                        </div>
                        <div style="background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; text-align: center;">
                            <h4 style="color: #ffd700; margin: 0 0 10px 0; font-size: 1.2em;">📊 StockX Ask</h4>
                            <div style="font-size: 2em; font-weight: bold; color: #ffffff;">${calculations.get('step_1_stockx_analysis', {}).get('stockx_ask', 'N/A')}</div>
                        </div>
                        <div style="background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; text-align: center;">
                            <h4 style="color: #ffd700; margin: 0 0 10px 0; font-size: 1.2em;">🎯 GOAT Absolute Lowest</h4>
                            <div style="font-size: 2em; font-weight: bold; color: #ffffff;">${calculations.get('step_5_alias_comparison', {}).get('goat_absolute_lowest', 'N/A')}</div>
                        </div>
                        <div style="background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; text-align: center;">
                            <h4 style="color: #ffd700; margin: 0 0 10px 0; font-size: 1.2em;">📦 GOAT Consignment</h4>
                            <div style="font-size: 2em; font-weight: bold; color: #ffffff;">${calculations.get('step_5_alias_comparison', {}).get('goat_consignment', 'N/A')}</div>
                        </div>
                        <div style="background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; text-align: center;">
                            <h4 style="color: #ffd700; margin: 0 0 10px 0; font-size: 1.2em;">🚚 GOAT Ship to Verify</h4>
                            <div style="font-size: 2em; font-weight: bold; color: #ffffff;">${calculations.get('step_5_alias_comparison', {}).get('goat_ship_to_verify', 'N/A')}</div>
                        </div>
                        <div style="background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; text-align: center;">
                            <h4 style="color: #ffd700; margin: 0 0 10px 0; font-size: 1.2em;">📊 GOAT Last Sale</h4>
                            <div style="font-size: 1.5em; font-weight: bold; color: #ffffff;">{get_goat_last_sale_info(result)}</div>
                        </div>
                    </div>
                </div>
                
                <!-- Sales Volume Information -->
                <div class="calculation-step" style="background: linear-gradient(135deg, #27ae60, #2ecc71); color: white; border-left: 5px solid #f39c12;">
                    <h3 style="color: white; font-size: 1.5em; text-align: center; margin-bottom: 25px;">📊 SALES VOLUME INFORMATION</h3>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-top: 20px;">
                        <div style="background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; text-align: center;">
                            <h4 style="color: #ffffff; margin: 0 0 10px 0; font-size: 1.2em;">📅 Sales Last Week</h4>
                            <div style="font-size: 2em; font-weight: bold; color: #ffffff;">{format_sales_display(raw_data.get('alias', {}).get('sales_volume', {}).get('sales_per_week', 0), 'week')}</div>
                        </div>
                        <div style="background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; text-align: center;">
                            <h4 style="color: #ffffff; margin: 0 0 10px 0; font-size: 1.2em;">📆 Sales Last Month</h4>
                            <div style="font-size: 2em; font-weight: bold; color: #ffffff;">{format_sales_display(raw_data.get('alias', {}).get('sales_volume', {}).get('sales_per_month', 0), 'month')}</div>
                        </div>
                        <div style="background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; text-align: center;">
                            <h4 style="color: #ffffff; margin: 0 0 10px 0; font-size: 1.2em;">📊 Sales Last 3 Months</h4>
                            <div style="font-size: 2em; font-weight: bold; color: #ffffff;">{format_sales_display(raw_data.get('alias', {}).get('sales_volume', {}).get('sales_per_3months', 0), '3 months')}</div>
                        </div>
                        <div style="background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; text-align: center;">
                            <h4 style="color: #ffffff; margin: 0 0 10px 0; font-size: 1.2em;">📈 Sales Last 6 Months</h4>
                            <div style="font-size: 2em; font-weight: bold; color: #ffffff;">{format_sales_display(raw_data.get('alias', {}).get('sales_volume', {}).get('sales_per_6months', 0), '6 months')}</div>
                        </div>
                        <div style="background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; text-align: center;">
                            <h4 style="color: #ffffff; margin: 0 0 10px 0; font-size: 1.2em;">📅 Sales Last Year</h4>
                            <div style="font-size: 2em; font-weight: bold; color: #ffffff;">{format_sales_display(raw_data.get('alias', {}).get('sales_volume', {}).get('sales_per_year', 0), 'year')}</div>
                        </div>
                        <div style="background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; text-align: center;">
                            <h4 style="color: #ffffff; margin: 0 0 10px 0; font-size: 1.2em;">📋 Total Sales</h4>
                            <div style="font-size: 2em; font-weight: bold; color: #ffffff;">{raw_data.get('alias', {}).get('sales_volume', {}).get('total_sales', 'N/A')}</div>
                        </div>
                    </div>
                    
                    <!-- Last 5 Sales Section -->
                    <div style="background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; margin-top: 20px;">
                        <h4 style="color: #ffd700; margin: 0 0 15px 0; font-size: 1.3em; text-align: center;">📈 Last 5 Sales</h4>
                        <div style="color: #ffffff; font-size: 1.1em; line-height: 1.6; text-align: left;">
                            {get_last_5_sales_display(result)}
                        </div>
                    </div>
                </div>
                
                <!-- Verification Information -->
                <div class="calculation-step">
                    <h3>🔍 Verification Information</h3>
                    <div class="calculation-detail">
                        <h4>StockX Match:</h4>
                        <p><strong>Product:</strong> {calculations.get('step_1_stockx_analysis', {}).get('stockx_product_name', 'N/A')}</p>
                        <p><strong>SKU:</strong> {calculations.get('step_1_stockx_analysis', {}).get('stockx_sku', 'N/A')}</p>
                        <p><strong>URL:</strong> <a href="{calculations.get('step_1_stockx_analysis', {}).get('stockx_url', '#')}" target="_blank">View on StockX</a></p>
                    </div>
                    <div class="calculation-detail">
                        <h4>Alias/GOAT Match:</h4>
                        <p><strong>Product:</strong> {calculations.get('step_5_alias_comparison', {}).get('alias_product_name', 'N/A')}</p>
                        <p><strong>SKU:</strong> {calculations.get('step_5_alias_comparison', {}).get('alias_sku', 'N/A')}</p>
                        <p><strong>Catalog ID:</strong> {calculations.get('step_5_alias_comparison', {}).get('alias_catalog_id', 'N/A')}</p>
                    </div>
                </div>
                
                <!-- Correction Options -->
                {build_correction_section(result.get('alternatives', {}), result.get('timestamp', '').split('T')[0].replace('-', ''))}
                
                <!-- Step 1: StockX Analysis -->
                {build_calculation_step_html('Step 1: StockX Analysis', calculations.get('step_1_stockx_analysis', {}))}
                
                <!-- Step 2: Volume Check -->
                {build_calculation_step_html('Step 2: Volume Check', calculations.get('step_2_volume_check', {}))}
                
                <!-- Step 3: Ask Calculation -->
                {build_calculation_step_html('Step 3: Ask Calculation (High Volume)', calculations.get('step_3_ask_calculation', {}))}
                
                <!-- Step 4: Bid Analysis -->
                {build_calculation_step_html('Step 4: Bid Analysis', calculations.get('step_4_bid_analysis', {}))}
                
                <!-- Step 5: Alias/GOAT Comparison -->
                {build_calculation_step_html('Step 5: Alias/GOAT Comparison', calculations.get('step_5_alias_comparison', {}))}
                
                <!-- Step 6: Final Decision -->
                {build_calculation_step_html('Step 6: Final Decision Logic', calculations.get('step_6_final_decision', {}))}
                
                <!-- Pricing Calculation Explanations -->
                <div class="calculation-step" style="background: linear-gradient(135deg, #9b59b6, #8e44ad); color: white; border-left: 5px solid #f1c40f;">
                    <h3 style="color: white; font-size: 1.5em; text-align: center; margin-bottom: 25px;">🧮 PRICING CALCULATION EXPLANATIONS</h3>
                    
                    <div class="calculation-detail" style="background: rgba(255,255,255,0.1); color: white;">
                        <h4 style="color: #f1c40f;">📈 HIGH VOLUME PRICING (≥3 sales/week)</h4>
                        <p><strong>When to use:</strong> When weekly sales are 3 or more</p>
                        <p><strong>Formula:</strong> StockX Ask × 0.8</p>
                        <p><strong>What you pay:</strong> 20% less than StockX ask price</p>
                        <p><strong>Example:</strong> StockX Ask $192 × 0.8 = $153.6</p>
                        <p><strong>Logic:</strong> High volume means quick turnover, so we can be more aggressive with pricing</p>
                    </div>
                    
                    <div class="calculation-detail" style="background: rgba(255,255,255,0.1); color: white;">
                        <h4 style="color: #f1c40f;">📉 LOW VOLUME PRICING (<3 sales/week)</h4>
                        <p><strong>When to use:</strong> When weekly sales are less than 3</p>
                        <p><strong>Formula:</strong> GOAT Absolute Lowest × 0.85</p>
                        <p><strong>What you pay:</strong> 15% less than GOAT's absolute lowest price</p>
                        <p><strong>Example:</strong> GOAT Lowest $481 × 0.85 = $408.8</p>
                        <p><strong>Logic:</strong> Low volume means slower turnover, so we need to be more conservative and base pricing on GOAT's market</p>
                    </div>
                    
                    <div class="calculation-detail" style="background: rgba(255,255,255,0.1); color: white;">
                        <h4 style="color: #f1c40f;">🔍 STOCKX ONLY PRICING</h4>
                        <p><strong>When to use:</strong> When only StockX data is available (no GOAT data)</p>
                        <p><strong>Formula:</strong> StockX Bid × 0.9</p>
                        <p><strong>What you pay:</strong> 10% less than StockX bid price</p>
                        <p><strong>Example:</strong> StockX Bid $240 × 0.9 = $216</p>
                        <p><strong>Logic:</strong> Conservative approach when we only have one data source</p>
                    </div>
                    
                    <div class="calculation-detail" style="background: rgba(255,255,255,0.1); color: white;">
                        <h4 style="color: #f1c40f;">❓ NO DATA PRICING</h4>
                        <p><strong>When to use:</strong> When no pricing data is available</p>
                        <p><strong>Formula:</strong> No price calculated</p>
                        <p><strong>What you pay:</strong> Check alternative options</p>
                        <p><strong>Logic:</strong> When no market data exists, suggest checking alternatives</p>
                    </div>
                </div>
                
                <!-- Platform Fees Section -->
                <div class="calculation-step" style="background: linear-gradient(135deg, #e67e22, #d35400); color: white; border-left: 5px solid #f39c12;">
                    <h3 style="color: white; font-size: 1.5em; text-align: center; margin-bottom: 25px;">💰 PLATFORM FEES & COSTS</h3>
                    
                    <div class="calculation-detail" style="background: rgba(255,255,255,0.1); color: white;">
                        <h4 style="color: #f39c12;">🟠 GOAT/ALIAS FEES</h4>
                        <ul style="list-style: none; padding-left: 0;">
                            <li>📦 <strong>Ship to Verify:</strong> 9.5% + $5.00 processing fee</li>
                            <li>🏪 <strong>Consignment:</strong> 9.5% + $5.00 processing fee</li>
                            <li>💳 <strong>Payment Processing:</strong> 2.9% + $0.30 per transaction</li>
                            <li>📤 <strong>Shipping to GOAT:</strong> Free (GOAT provides label)</li>
                            <li>📥 <strong>Shipping to Buyer:</strong> Free (included in fees)</li>
                            <li>🔍 <strong>Authentication:</strong> Included in processing fee</li>
                        </ul>
                        <p><strong>Total GOAT Fees:</strong> ~12.4% + $5.30 per sale</p>
                    </div>
                    
                    <div class="calculation-detail" style="background: rgba(255,255,255,0.1); color: white;">
                        <h4 style="color: #f39c12;">🔵 STOCKX FEES</h4>
                        <ul style="list-style: none; padding-left: 0;">
                            <li>💼 <strong>Seller Fee:</strong> 9.5% for most items</li>
                            <li>💳 <strong>Payment Processing:</strong> 3% + $0.30 per transaction</li>
                            <li>📤 <strong>Shipping to StockX:</strong> Free (StockX provides label)</li>
                            <li>📥 <strong>Shipping to Buyer:</strong> Free (included in fees)</li>
                            <li>🔍 <strong>Authentication:</strong> Included in seller fee</li>
                            <li>⚡ <strong>Instant Sale:</strong> Additional 2% fee</li>
                        </ul>
                        <p><strong>Total StockX Fees:</strong> ~12.5% + $0.30 per sale</p>
                    </div>
                    
                    <div class="calculation-detail" style="background: rgba(255,255,255,0.1); color: white;">
                        <h4 style="color: #f39c12;">📊 FEE COMPARISON</h4>
                        <p><strong>GOAT vs StockX:</strong> Very similar fee structures (~12.4-12.5%)</p>
                        <p><strong>Key Differences:</strong></p>
                        <ul style="list-style: none; padding-left: 0;">
                            <li>• GOAT has higher base processing fee ($5.00 vs $0.30)</li>
                            <li>• StockX has instant sale option with additional 2% fee</li>
                            <li>• Both include authentication and shipping in base fees</li>
                        </ul>
                        <p><strong>Profit Margin Consideration:</strong> Our pricing calculations account for these fees to ensure profitable sales</p>
                    </div>
                </div>
                
                <!-- Calculated Data Section -->
                <div class="calculation-step" style="background: #f8f9fa; border-left: 5px solid #6c757d;">
                    <h3>🧮 CALCULATED DATA</h3>
                    <div class="calculation-detail">
                        <h4>How Each Calculation Was Derived:</h4>
                        
                        <div style="background: #e9ecef; padding: 15px; border-radius: 8px; font-family: monospace; font-size: 0.9em;">
                            <h5>📊 Step 1: StockX Analysis</h5>
                            <p>• <strong>StockX Bid:</strong> ${calculations.get('step_1_stockx_analysis', {}).get('stockx_bid', 'N/A')} (from StockX API)</p>
                            <p>• <strong>StockX Ask:</strong> ${calculations.get('step_1_stockx_analysis', {}).get('stockx_ask', 'N/A')} (from StockX API)</p>
                            <p>• <strong>Bid-Ask Spread:</strong> ${calculations.get('step_1_stockx_analysis', {}).get('bid_ask_spread', 'N/A')} (Ask - Bid)</p>
                            
                            <h5>📈 Step 2: Volume Check</h5>
                            <p>• <strong>Weekly Sales:</strong> {calculations.get('step_2_volume_check', {}).get('weekly_sales', 'N/A')} (from Alias API)</p>
                            <p>• <strong>High Volume:</strong> {calculations.get('step_2_volume_check', {}).get('is_high_volume', 'N/A')} (≥3 sales/week)</p>
                            <p>• <strong>Threshold:</strong> {calculations.get('step_2_volume_check', {}).get('threshold', 'N/A')} sales/week</p>
                            
                            <h5>🧮 Step 3: Ask Calculation (High Volume)</h5>
                            <p>• <strong>Original Ask:</strong> ${calculations.get('step_3_ask_calculation', {}).get('original_ask', 'N/A')}</p>
                            <p>• <strong>20% Reduction:</strong> ${calculations.get('step_3_ask_calculation', {}).get('ask_minus_20_percent', 'N/A')} (Ask × 0.8)</p>
                            <p>• <strong>Final Price:</strong> ${calculations.get('step_3_ask_calculation', {}).get('final_price', 'N/A')}</p>
                            
                            <h5>💎 Step 4: Bid Analysis</h5>
                            <p>• <strong>StockX Bid:</strong> {calculations.get('step_4_bid_analysis', {}).get('stockx_bid', 'N/A')} (current market bid)</p>
                            
                            <h5>🟠 Step 5: Alias/GOAT Comparison</h5>
                            <p>• <strong>Ship to Verify:</strong> ${calculations.get('step_5_alias_comparison', {}).get('goat_ship_to_verify', 'N/A')} (from Alias API)</p>
                            <p>• <strong>Consignment:</strong> ${calculations.get('step_5_alias_comparison', {}).get('goat_consignment', 'N/A')} (from Alias API)</p>
                            <p>• <strong>Absolute Lowest:</strong> ${calculations.get('step_5_alias_comparison', {}).get('goat_absolute_lowest', 'N/A')} (min of above two)</p>
                            
                            <h5>🎯 Step 6: Final Decision</h5>
                            <p>• <strong>Final Price:</strong> ${calculations.get('step_6_final_decision', {}).get('final_price', 'N/A')}</p>
                            <p>• <strong>Decision Reason:</strong> {calculations.get('step_6_final_decision', {}).get('decision_reason', 'N/A')}</p>
                            <p>• <strong>Calculation:</strong> {calculations.get('step_6_final_decision', {}).get('calculation_breakdown', 'N/A')}</p>
                        </div>
                        
                        <h4>Complete Calculation Object:</h4>
                        <pre style="background: #e9ecef; padding: 15px; border-radius: 8px; font-family: monospace; font-size: 0.9em;">
{json.dumps(calculations, indent=2)}
                        </pre>
                    </div>
                </div>
                
                <!-- Raw Data Section -->
                <div class="calculation-step">
                    <h3>📊 Raw Data</h3>
                    <div class="calculation-detail">
                        <h4>StockX Data:</h4>
                        <pre>{json.dumps(raw_data.get('stockx', {}), indent=2)}</pre>
                    </div>
                    <div class="calculation-detail">
                        <h4>Alias/GOAT Data:</h4>
                        <pre>{json.dumps(raw_data.get('alias', {}), indent=2)}</pre>
                    </div>
                </div>
                
                <!-- API Documentation -->
                <div class="calculation-step" style="background: #f8f9fa; border-left: 5px solid #17a2b8;">
                    <h3>📚 API VARIABLES DOCUMENTATION</h3>
                    
                    <div class="calculation-detail">
                        <h4>🟠 ALIAS/GOAT API VARIABLES</h4>
                        <p><strong>Endpoint:</strong> <code>https://api.alias.org/api/v1/pricing_insights/availability</code></p>
                        
                        <h5>Overall Availability (Ship-to-Verify):</h5>
                        <ul>
                            <li><code>lowest_listing_price_cents</code> - Lowest price to ship to GOAT</li>
                            <li><code>highest_offer_price_cents</code> - Highest offer GOAT will pay</li>
                            <li><code>last_sold_listing_price_cents</code> - Price of most recent sale</li>
                            <li><code>global_indicator_price_cents</code> - GOAT's suggested price</li>
                        </ul>
                        
                        <h5>Consigned Availability (<code>?consigned=true</code>):</h5>
                        <ul>
                            <li><code>lowest_listing_price_cents</code> - Lowest price for items GOAT already has</li>
                            <li><code>highest_offer_price_cents</code> - Highest offer for consigned items</li>
                            <li><code>last_sold_listing_price_cents</code> - Price of most recent consigned sale</li>
                            <li><code>global_indicator_price_cents</code> - GOAT's suggested price for consigned</li>
                        </ul>
                        
                        <h5>Recent Sales (<code>/pricing_insights/recent_sales</code>):</h5>
                        <ul>
                            <li><code>price_cents</code> - Sale price in cents</li>
                            <li><code>purchased_at</code> - Sale timestamp</li>
                            <li><code>product_condition</code> - Condition of sold item</li>
                            <li><code>packaging_condition</code> - Packaging condition</li>
                        </ul>
                        
                        <h5>Catalog Search (<code>/catalog</code>):</h5>
                        <ul>
                            <li><code>catalog_id</code> - Unique product identifier</li>
                            <li><code>name</code> - Product name</li>
                            <li><code>sku</code> - Product SKU</li>
                            <li><code>brand</code> - Brand name</li>
                            <li><code>gender</code> - Target gender</li>
                            <li><code>release_date</code> - Release date</li>
                            <li><code>product_category</code> - Product category</li>
                            <li><code>product_type</code> - Product type</li>
                            <li><code>size_unit</code> - Size unit system</li>
                            <li><code>allowed_sizes</code> - Available sizes</li>
                        </ul>
                    </div>
                    
                    <div class="calculation-detail">
                        <h4>🔵 STOCKX API VARIABLES</h4>
                        <p><strong>Endpoint:</strong> <code>https://stockx.com/api/products/</code></p>
                        
                        <h5>Product Data:</h5>
                        <ul>
                            <li><code>stockx_bid</code> - Current highest bid</li>
                            <li><code>stockx_ask</code> - Current lowest ask</li>
                            <li><code>stockx_shoe_name</code> - Product name</li>
                            <li><code>stockx_sku</code> - Product SKU</li>
                            <li><code>stockx_url</code> - Product URL</li>
                            <li><code>last_sale</code> - Most recent sale price</li>
                            <li><code>total_sold</code> - Total units sold</li>
                            <li><code>volatility</code> - Price volatility metric</li>
                        </ul>
                        
                        <h5>Market Data:</h5>
                        <ul>
                            <li><code>bid_ask_spread</code> - Difference between bid and ask</li>
                            <li><code>market_cap</code> - Market capitalization</li>
                            <li><code>trading_volume</code> - Trading volume</li>
                        </ul>
                    </div>
                    
                    <div class="calculation-detail">
                        <h4>❓ DATA AVAILABILITY CHECK</h4>
                        <p><strong>For this analysis:</strong></p>
                        <ul>
                            <li>✅ <strong>StockX Data:</strong> {len(raw_data.get('stockx', {}))} variables retrieved</li>
                            <li>✅ <strong>Alias Data:</strong> {len(raw_data.get('alias', {}))} variables retrieved</li>
                            <li>✅ <strong>Sales Volume:</strong> {len(raw_data.get('alias', {}).get('sales_volume', {}))} metrics available</li>
                            <li>✅ <strong>Pricing Data:</strong> {len(raw_data.get('alias', {}).get('pricing', {}))} price points available</li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

def render_advanced_multi_analysis(results: List[dict]) -> str:
    """Render a dashboard of multiple advanced analyses as summary cards"""
    def card_for_result(res: dict) -> str:
        query = res.get('query', 'Unknown')
        size = res.get('size', 'Unknown')
        ts = res.get('timestamp', '')
        success = res.get('success', False)
        if not success:
            err = ', '.join(res.get('errors', ['Unknown error']))
            return f"""
            <div class="result-card" style="background:#fff; border-left:5px solid #e74c3c; padding:16px; border-radius:10px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <div class="result-title">{query} - Size {size}</div>
                        <div class="result-meta">{ts}</div>
                    </div>
                    <div class="recommendation-badge badge-no-buy">ERROR</div>
                </div>
                <div style="color:#e74c3c;">{err}</div>
            </div>
            """

        calc = res.get('calculations', {})
        rec = res.get('final_recommendation', {})
        profit = calculate_profit_analysis(res)
        action = rec.get('action', 'UNKNOWN')
        price = rec.get('price')
        badge_class = 'badge-buy' if action == 'BUY' else 'badge-no-buy'
        badge_text = f"BUY ${price:.2f}" if action == 'BUY' and price else action

        # Key pricing fields
        stockx_bid = calc.get('step_1_stockx_analysis', {}).get('stockx_bid')
        stockx_ask = calc.get('step_1_stockx_analysis', {}).get('stockx_ask')
        alias = calc.get('step_5_alias_comparison', {})
        goat_abs = alias.get('goat_absolute_lowest')
        last5 = get_last_5_sales_display(res)
        goat_last_sale = get_goat_last_sale_info(res)

        return f"""
        <div class="result-card">
            <div class="result-header">
                <div>
                    <div class="result-title">{query} - Size {size}</div>
                    <div class="result-meta">{ts} | Confidence: {rec.get('confidence','Unknown')}</div>
                </div>
                <div class="recommendation-badge {badge_class}">{badge_text}</div>
            </div>
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px,1fr)); gap:12px;">
                <div class="metric">
                    <div class="metric-label">Final Recommendation</div>
                    <div style="font-weight:bold;">{rec.get('recommendation','')}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">GOAT Lowest</div>
                    <div>${goat_abs if goat_abs else 'N/A'}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">StockX Bid / Ask</div>
                    <div>${stockx_bid or 'N/A'} / ${stockx_ask or 'N/A'}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Profit (GOAT Lowest)</div>
                    <div>${profit['actual_profit']:.2f} ({profit['profit_percentage']:.1f}%)</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Profit (GOAT Consignment)</div>
                    <div>${profit['consignment_actual_profit']:.2f} ({profit['consignment_profit_percentage']:.1f}%)</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Profit (StockX Ask)</div>
                    <div>${profit['stockx_actual_profit']:.2f} ({profit['stockx_profit_percentage']:.1f}%)</div>
                </div>
                <div class="metric">
                    <div class="metric-label">GOAT Last Sale</div>
                    <div>{goat_last_sale}</div>
                </div>
                <div class="metric" style="grid-column: 1/-1; text-align:left;">
                    <div class="metric-label">Last 5 Sales</div>
                    <div>{last5}</div>
                </div>
            </div>
        </div>
        """

    # Page shell
    cards_html = "\n".join(card_for_result(r) for r in results)
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>📚 Advanced Multi‑Shoe Analysis</title>
        <style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; margin:0; padding:20px; background:#f0f2f5; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            .header {{ background: linear-gradient(135deg, #2c3e50, #34495e); color:#fff; padding:24px; border-radius:12px; margin-bottom:16px; }}
            .result-card {{ background:#fff; border-radius:10px; padding:16px; margin:12px 0; border-left:5px solid #3498db; }}
            .result-header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }}
            .result-title {{ font-size:1.2em; font-weight:bold; }}
            .result-meta {{ color:#666; font-size:0.9em; }}
            .recommendation-badge {{ padding:6px 12px; border-radius:18px; font-weight:bold; }}
            .badge-buy {{ background:#27ae60; color:#fff; }}
            .badge-no-buy {{ background:#e74c3c; color:#fff; }}
            .metric {{ background:#f8f9fa; padding:12px; border-radius:8px; text-align:center; }}
            .metric-label {{ font-size:0.8em; color:#666; text-transform:uppercase; letter-spacing:1px; margin-bottom:6px; }}
            .back-link {{ position:fixed; top:20px; right:20px; background:#e74c3c; color:#fff; padding:10px 16px; border-radius:22px; text-decoration:none; font-weight:bold; }}
        </style>
    </head>
    <body>
        <a href="/" class="back-link">← Back</a>
        <div class="container">
            <div class="header">
                <h1>📚 Advanced Multi‑Shoe Analysis</h1>
                <p>Summary of pricing recommendations, profits, and sales signals for each item.</p>
            </div>
            {cards_html}
        </div>
    </body>
    </html>
    """

def get_advanced_rec_class(action: str) -> str:
    """Get CSS class for advanced recommendation styling"""
    if action == 'BUY':
        return 'rec-buy'
    else:
        return 'rec-no-buy'

def get_best_sales_display(sales_volume: dict) -> tuple:
    """Get the best sales volume display - show first non-zero period"""
    periods = [
        ('sales_per_week', 'Sales Last Week'),
        ('sales_per_month', 'Sales Last Month'), 
        ('sales_per_3months', 'Sales Last 3 Months'),
        ('sales_per_6months', 'Sales Last 6 Months'),
        ('sales_per_year', 'Sales Last Year')
    ]
    
    for key, label in periods:
        value = sales_volume.get(key, 0)
        if value > 0:
            return key, label, value
    
    # If all are 0, return the first one
    return periods[0][0], periods[0][1], sales_volume.get(periods[0][0], 0)

def format_sales_display(value: int, period: str) -> str:
    """Format sales display with 'last' instead of 'per'"""
    if value == 0:
        return f"0 last {period.lower()}"
    else:
        return f"{value} last {period.lower()}"

def get_confidence_explanation(confidence: str, result: dict) -> str:
    """Get detailed explanation for confidence score"""
    confidence_lower = confidence.lower()
    
    if 'high' in confidence_lower:
        return "High confidence: Both StockX and Alias found exact matches with matching SKUs"
    elif 'medium' in confidence_lower:
        return "Medium confidence: Found matches but SKUs don't match exactly"
    elif 'low' in confidence_lower:
        # Check for specific reasons
        stockx_data = result.get('raw_data', {}).get('stockx', {})
        alias_data = result.get('raw_data', {}).get('alias', {})
        
        if not stockx_data.get('product_name'):
            return "Low confidence: No StockX match found"
        elif not alias_data.get('catalog_match', {}).get('name'):
            return "Low confidence: No Alias/GOAT match found"
        elif stockx_data.get('sku') != alias_data.get('catalog_match', {}).get('sku'):
            return "Low confidence: StockX and Alias found different SKUs"
        else:
            return "Low confidence: Limited data available from one or both platforms"
    else:
        return f"Confidence: {confidence}"

def get_confidence_emoji(confidence: str) -> str:
    """Get warning emoji based on confidence level"""
    confidence_lower = confidence.lower()
    
    if 'high' in confidence_lower:
        return "✅"
    elif 'medium' in confidence_lower:
        return "⚠️"
    elif 'low' in confidence_lower:
        return "🚨"
    else:
        return "❓"

def calculate_profit_analysis(result: dict) -> dict:
    """Calculate profit analysis based on GOAT pricing"""
    alias_data = result.get('raw_data', {}).get('alias', {})
    pricing = alias_data.get('pricing', {})
    calculations = result.get('calculations', {})
    
    # Get the buy price from the final recommendation
    buy_price = calculations.get('step_6_final_decision', {}).get('final_price', 0)
    
    # Get StockX ask price
    stockx_ask = calculations.get('step_1_stockx_analysis', {}).get('stockx_ask', 0)
    
    # Get GOAT absolute lowest price
    ship_price = pricing.get('ship_to_verify_price')
    consignment_price = pricing.get('consignment_price')
    
    # Filter out None values and find the minimum
    valid_prices = [p for p in [ship_price, consignment_price] if p is not None and p > 0]
    goat_lowest_price = min(valid_prices) if valid_prices else 0
    
    # GOAT fees (approximately 9.5% + $5)
    goat_fees = (goat_lowest_price * 0.095) + 5 if goat_lowest_price > 0 else 0
    
    # Calculate profit (selling for $1 less than GOAT lowest)
    selling_price = goat_lowest_price - 1
    after_fees_amount = selling_price - goat_fees if selling_price > goat_fees else 0
    actual_profit = after_fees_amount - buy_price if after_fees_amount > buy_price else 0
    profit_percentage = (actual_profit / buy_price * 100) if buy_price > 0 else 0
    
    # Calculate consignment profit (selling for $1 less than consignment price)
    consignment_selling_price = consignment_price - 1 if consignment_price > 0 else 0
    consignment_fees = (consignment_selling_price * 0.095) + 5 if consignment_selling_price > 0 else 0
    consignment_after_fees = consignment_selling_price - consignment_fees if consignment_selling_price > consignment_fees else 0
    consignment_actual_profit = consignment_after_fees - buy_price if consignment_after_fees > buy_price else 0
    consignment_profit_percentage = (consignment_actual_profit / buy_price * 100) if buy_price > 0 else 0
    
    # Calculate StockX ask profit (selling for $1 less than StockX ask)
    stockx_selling_price = stockx_ask - 1 if stockx_ask > 0 else 0
    stockx_fees = (stockx_selling_price * 0.095) + 5 if stockx_selling_price > 0 else 0
    stockx_after_fees = stockx_selling_price - stockx_fees if stockx_selling_price > stockx_fees else 0
    stockx_actual_profit = stockx_after_fees - buy_price if stockx_after_fees > buy_price else 0
    stockx_profit_percentage = (stockx_actual_profit / buy_price * 100) if buy_price > 0 else 0
    
    return {
        'buy_price': buy_price,
        'goat_lowest_price': goat_lowest_price,
        'goat_fees': goat_fees,
        'selling_price': selling_price,
        'after_fees_amount': after_fees_amount,
        'actual_profit': actual_profit,
        'profit_percentage': profit_percentage,
        'consignment_price': consignment_price,
        'consignment_selling_price': consignment_selling_price,
        'consignment_fees': consignment_fees,
        'consignment_after_fees': consignment_after_fees,
        'consignment_actual_profit': consignment_actual_profit,
        'consignment_profit_percentage': consignment_profit_percentage,
        'stockx_ask': stockx_ask,
        'stockx_selling_price': stockx_selling_price,
        'stockx_fees': stockx_fees,
        'stockx_after_fees': stockx_after_fees,
        'stockx_actual_profit': stockx_actual_profit,
        'stockx_profit_percentage': stockx_profit_percentage
    }

def get_goat_last_sale_info(result: dict) -> str:
    """Get GOAT last sale information"""
    alias_data = result.get('raw_data', {}).get('alias', {})
    pricing = alias_data.get('pricing', {})
    
    # Get last sale dates and prices
    last_with_you_date = pricing.get('last_with_you_date')
    last_consigned_date = pricing.get('last_consigned_date')
    last_with_you_price = pricing.get('last_with_you_price', 0)
    last_consigned_price = pricing.get('last_consigned_price', 0)
    
    if not last_with_you_date and not last_consigned_date:
        return "No recent sales data"
    
    # Determine which sale is more recent
    from datetime import datetime, timezone
    
    try:
        if last_with_you_date and last_consigned_date:
            with_you_dt = datetime.fromisoformat(last_with_you_date.replace('Z', '+00:00'))
            consigned_dt = datetime.fromisoformat(last_consigned_date.replace('Z', '+00:00'))
            
            if with_you_dt > consigned_dt:
                # With you sale is more recent
                days_ago = (datetime.now(timezone.utc) - with_you_dt).days
                return f"${last_with_you_price:.2f} ({days_ago} days ago)"
            else:
                # Consigned sale is more recent
                days_ago = (datetime.now(timezone.utc) - consigned_dt).days
                return f"${last_consigned_price:.2f} ({days_ago} days ago)"
        elif last_with_you_date:
            with_you_dt = datetime.fromisoformat(last_with_you_date.replace('Z', '+00:00'))
            days_ago = (datetime.now(timezone.utc) - with_you_dt).days
            return f"${last_with_you_price:.2f} ({days_ago} days ago)"
        elif last_consigned_date:
            consigned_dt = datetime.fromisoformat(last_consigned_date.replace('Z', '+00:00'))
            days_ago = (datetime.now(timezone.utc) - consigned_dt).days
            return f"${last_consigned_price:.2f} ({days_ago} days ago)"
    except Exception:
        return "Date parsing error"
    
    return "No recent sales data"

def get_last_5_sales_display(result: dict) -> str:
    """Get formatted display of last 5 sales"""
    alias_data = result.get('raw_data', {}).get('alias', {})
    sales_volume = alias_data.get('sales_volume', {})
    last_5_sales = sales_volume.get('last_5_sales', [])
    
    if not last_5_sales:
        return "No recent sales data available"
    
    from datetime import datetime, timezone
    
    sales_display = []
    for i, sale in enumerate(last_5_sales[:5], 1):
        try:
            sale_date = sale.get('date')
            sale_price = sale.get('price', 0)
            
            if sale_date:
                # Parse the date
                sale_dt = datetime.fromisoformat(sale_date.replace('Z', '+00:00'))
                days_ago = (datetime.now(timezone.utc) - sale_dt).days
                
                # Format the sale info
                if days_ago == 0:
                    time_ago = "Today"
                elif days_ago == 1:
                    time_ago = "1 day ago"
                else:
                    time_ago = f"{days_ago} days ago"
                
                sales_display.append(f"<strong>#{i}:</strong> ${sale_price:.2f} ({time_ago})")
            else:
                sales_display.append(f"<strong>#{i}:</strong> ${sale_price:.2f} (date unknown)")
        except Exception:
            sales_display.append(f"<strong>#{i}:</strong> ${sale.get('price', 0):.2f} (date error)")
    
    if not sales_display:
        return "No recent sales data available"
    
    return "<br>".join(sales_display)

def get_confidence_warning_section(confidence: str, result: dict) -> str:
    """Get confidence warning section with initial Alias match info"""
    if 'low' not in confidence.lower():
        return ""
    
    stockx_data = result.get('raw_data', {}).get('stockx', {})
    alias_data = result.get('raw_data', {}).get('alias', {})
    
    # Normalize SKUs for comparison (remove spaces and dashes)
    stockx_sku = stockx_data.get('sku', 'Unknown')
    alias_sku = alias_data.get('catalog_match', {}).get('sku', 'Unknown')
    
    stockx_sku_normalized = stockx_sku.replace('-', '').replace(' ', '') if stockx_sku else ''
    alias_sku_normalized = alias_sku.replace('-', '').replace(' ', '') if alias_sku else ''
    
    # Check if it's a SKU mismatch (after normalization)
    if stockx_sku_normalized != alias_sku_normalized:
        stockx_name = stockx_data.get('product_name', 'Unknown')
        alias_name = alias_data.get('catalog_match', {}).get('name', 'Unknown')
        
        return f"""
                        <div class="metric" style="background: #fff3cd; color: #856404; padding: 15px; border-radius: 8px; margin: 10px 0; text-align: left;">
                            <strong>🚨 SKU Mismatch Warning:</strong><br>
                            StockX found: {stockx_name} (SKU: {stockx_sku})<br>
                            Alias initially found: {alias_name} (SKU: {alias_sku})
                        </div>
        """
    else:
        # SKUs match after normalization, so confidence should be higher
        return f"""
                        <div class="metric" style="background: #d4edda; color: #155724; padding: 15px; border-radius: 8px; margin: 10px 0; text-align: left;">
                            <strong>✅ SKU Match Confirmed:</strong><br>
                            StockX and Alias SKUs match after normalization<br>
                            StockX: {stockx_sku} → Alias: {alias_sku}
                        </div>
        """

def build_calculation_step_html(step_title: str, step_data: dict) -> str:
    """Build HTML for a calculation step"""
    if not step_data:
        return ""
    
    # Determine confidence class
    confidence_class = 'confidence-high'  # Default
    
    html = f"""
    <div class="calculation-step {confidence_class}">
        <h3>{step_title}</h3>
        <div class="calculation-detail">
    """
    
    # Add each data point
    for key, value in step_data.items():
        if key == 'notes':
            html += f"<p><strong>Notes:</strong> {value}</p>"
        elif key == 'calculation':
            html += f'<div class="math-formula">{value}</div>'
        elif isinstance(value, (int, float)):
            html += f"<div class='metric'>{key.replace('_', ' ').title()}: {value}</div>"
        elif isinstance(value, bool):
            html += f"<div class='metric'>{key.replace('_', ' ').title()}: {'✅ Yes' if value else '❌ No'}</div>"
        elif value is not None:
            html += f"<div class='metric'>{key.replace('_', ' ').title()}: {value}</div>"
    
    html += "</div></div>"
    return html

def build_correction_section(alternatives: dict, timestamp: str = "") -> str:
    """Build HTML for correction options section"""
    # Check if alternatives exist and have content
    has_alternatives = (alternatives and 
                       (alternatives.get('stockx_alternatives') or alternatives.get('alias_alternatives')))
    
    if not has_alternatives:
        # Show button to generate alternatives
        return f"""
        <div class="calculation-step">
            <h3>🔧 Correction Options</h3>
            <p><em>If the matches above are incorrect, you can generate alternative matches:</em></p>
            
            <div style="margin: 20px 0;">
                <form method="POST" action="/generate_alternatives/{timestamp}" style="display: inline;">
                    <button type="submit" class="correction-btn" style="background: #17a2b8; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-weight: bold;">
                        Generate Alternative Matches
                    </button>
                </form>
                <p style="color: #666; font-size: 0.9em; margin-top: 10px;">
                    <em>This will search for other possible matches and may take a few seconds.</em>
                </p>
            </div>
        </div>
        """
    
    html = """
    <div class="calculation-step">
        <h3>🔧 Correction Options</h3>
        <p><em>If the matches above are incorrect, you can select alternatives:</em></p>
        
        <div style="margin: 20px 0;">
            <button onclick="toggleCorrections()" class="correction-btn" style="background: #ffc107; color: #212529; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-weight: bold;">
                Show Alternative Matches
            </button>
            <div id="correctionOptions" style="display: none; margin-top: 15px;">
    """
    
    # StockX alternatives
    if alternatives.get('stockx_alternatives'):
        html += "<h4>StockX Alternatives:</h4>"
        for i, alt in enumerate(alternatives['stockx_alternatives']):
            html += f"""
            <div class="alternative-option" style="margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 5px; border-left: 3px solid #007bff;">
                <input type="radio" name="stockx_alt" id="stockx_{i}" value="{alt['sku']}">
                <label for="stockx_{i}" style="margin-left: 10px; cursor: pointer;">
                    <strong>{alt['name']}</strong> (SKU: {alt['sku']})
                    <br><small style="color: #666;">Variation: {alt.get('variation', 'N/A')}</small>
                </label>
            </div>
            """
    
    # Alias alternatives
    if alternatives.get('alias_alternatives'):
        html += "<h4>Alias/GOAT Alternatives:</h4>"
        for i, alt in enumerate(alternatives['alias_alternatives']):
            html += f"""
            <div class="alternative-option" style="margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 5px; border-left: 3px solid #28a745;">
                <input type="radio" name="alias_alt" id="alias_{i}" value="{alt['catalog_id']}">
                <label for="alias_{i}" style="margin-left: 10px; cursor: pointer;">
                    <strong>{alt['name']}</strong> (SKU: {alt['sku']})
                    <br><small style="color: #666;">Search term: {alt.get('search_term', 'N/A')}</small>
                </label>
            </div>
            """
    
    html += """
            </div>
        </div>
    </div>
    
    <script>
        function toggleCorrections() {
            const options = document.getElementById('correctionOptions');
            const btn = event.target;
            if (options.style.display === 'none') {
                options.style.display = 'block';
                btn.textContent = 'Hide Alternative Matches';
                btn.style.background = '#6c757d';
            } else {
                options.style.display = 'none';
                btn.textContent = 'Show Alternative Matches';
                btn.style.background = '#ffc107';
            }
        }
    </script>
    """
    
    return html

def render_advanced_results_list(results: List[dict]) -> str:
    """Render list of all saved advanced analysis results"""
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>📋 Advanced Analysis Results</title>
        <style>
            body {{ 
                font-family: 'Segoe UI', Arial, sans-serif; 
                margin: 0; 
                padding: 20px;
                line-height: 1.6;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
            }}
            .container {{ 
                max-width: 1200px; 
                margin: 0 auto; 
                background: white; 
                border-radius: 15px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.3);
                overflow: hidden;
            }}
            .header {{ 
                background: linear-gradient(135deg, #2c3e50, #34495e);
                color: white; 
                padding: 30px; 
                text-align: center;
            }}
            .header h1 {{ margin: 0; font-size: 2.5em; }}
            
            .content {{ padding: 20px; }}
            
            .result-card {{ 
                background: #f8f9fa;
                border-radius: 10px;
                padding: 20px;
                margin: 15px 0;
                border-left: 5px solid #3498db;
                transition: transform 0.2s;
            }}
            .result-card:hover {{ 
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            }}
            
            .result-header {{ 
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 15px;
            }}
            
            .result-title {{ 
                font-size: 1.3em;
                font-weight: bold;
                color: #2c3e50;
            }}
            
            .result-meta {{ 
                color: #666;
                font-size: 0.9em;
            }}
            
            .recommendation-badge {{ 
                padding: 5px 15px;
                border-radius: 20px;
                font-weight: bold;
                font-size: 0.9em;
            }}
            .badge-buy {{ background: #27ae60; color: white; }}
            .badge-no-buy {{ background: #e74c3c; color: white; }}
            
            .action-buttons {{ 
                margin-top: 15px;
            }}
            
            .btn {{ 
                padding: 8px 16px;
                border-radius: 5px;
                text-decoration: none;
                margin-right: 10px;
                font-weight: bold;
            }}
            .btn-view {{ background: #3498db; color: white; }}
            .btn-delete {{ background: #e74c3c; color: white; }}
            
            .back-link {{ 
                position: fixed; 
                top: 30px; 
                right: 30px; 
                background: linear-gradient(135deg, #e74c3c, #c0392b);
                color: white; 
                padding: 12px 20px; 
                text-decoration: none; 
                border-radius: 25px;
                box-shadow: 0 4px 15px rgba(231, 76, 60, 0.3);
                font-weight: bold;
                transition: transform 0.2s;
                z-index: 1000;
            }}
            .back-link:hover {{ 
                transform: scale(1.05);
                box-shadow: 0 6px 20px rgba(231, 76, 60, 0.4);
            }}
            
            .empty-state {{ 
                text-align: center;
                padding: 50px;
                color: #666;
            }}
        </style>
    </head>
    <body>
        <a href="/" class="back-link">← Back to Main</a>
        
        <div class="container">
            <div class="header">
                <h1>📋 Advanced Analysis Results</h1>
                <p>All your saved shoe analyses with detailed pricing logic</p>
            </div>
            
            <div class="content">
                {build_results_list_html(results)}
            </div>
        </div>
    </body>
    </html>
    """

def build_results_list_html(results: List[dict]) -> str:
    """Build HTML for the results list"""
    if not results:
        return """
        <div class="empty-state">
            <h2>📭 No Results Yet</h2>
            <p>You haven't run any advanced analyses yet.</p>
            <p><a href="/" style="background: #3498db; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Run Your First Analysis</a></p>
        </div>
        """
    
    html = ""
    for result in results:
        query = result.get('query', 'Unknown')
        size = result.get('size', 'Unknown')
        timestamp = result.get('timestamp', '')
        recommendation = result.get('final_recommendation', {})
        action = recommendation.get('action', 'UNKNOWN')
        price = recommendation.get('price')
        confidence = recommendation.get('confidence', 'Unknown')
        
        # Format timestamp
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            formatted_time = timestamp
        
        # Create timestamp for URL
        url_timestamp = timestamp.replace(':', '').replace('-', '').replace('T', '').replace('.', '')
        
        badge_class = 'badge-buy' if action == 'BUY' else 'badge-no-buy'
        badge_text = f"BUY ${price}" if action == 'BUY' and price else action
        
        html += f"""
        <div class="result-card">
            <div class="result-header">
                <div>
                    <div class="result-title">{query} - Size {size}</div>
                    <div class="result-meta">
                        Analyzed: {formatted_time} | Confidence: {confidence}
                    </div>
                </div>
                <div class="recommendation-badge {badge_class}">{badge_text}</div>
            </div>
            
            <div class="action-buttons">
                <a href="/advanced_result/{url_timestamp}" class="btn btn-view">📊 View Details</a>
                <form action="/delete_advanced_result/{url_timestamp}" method="post" style="display: inline;">
                    <button type="submit" class="btn btn-delete" onclick="return confirm('Are you sure you want to delete this result?')">🗑️ Delete</button>
                </form>
            </div>
        </div>
        """
    
    return html

def render_single_shoe_analysis(result: dict) -> str:
    shoe_id = result.get('shoe_identification', {})
    market = result.get('market_summary', {})
    performance = result.get('sales_performance', {})
    pricing = result.get('pricing_insights', {})
    size_breakdown = result.get('size_breakdown', {})
    quality = result.get('data_quality', {})
    
    # Build comprehensive HTML response with organized layout
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>🔍 Analysis: {query}</title>
        <style>
            body {{ 
                font-family: 'Segoe UI', Arial, sans-serif; 
                margin: 0; 
                padding: 20px;
                line-height: 1.6;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
            }}
            .container {{ 
                max-width: 1200px; 
                margin: 0 auto; 
                background: white; 
                border-radius: 15px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.3);
                overflow: hidden;
            }}
            .header {{ 
                background: linear-gradient(135deg, #2c3e50, #34495e);
                color: white; 
                padding: 30px; 
                text-align: center;
            }}
            .header h1 {{ margin: 0; font-size: 2.5em; }}
            .header h2 {{ margin: 10px 0 0 0; font-weight: 300; opacity: 0.9; }}
            
            .content {{ padding: 20px; }}
            
            .priority-section {{ 
                background: linear-gradient(135deg, #27ae60, #2ecc71);
                color: white;
                padding: 25px;
                margin: 20px 0;
                border-radius: 12px;
                text-align: center;
            }}
            
            .recommendation {{ 
                font-size: 1.5em; 
                font-weight: bold; 
                padding: 20px; 
                border-radius: 10px;
                margin: 20px 0;
                text-align: center;
            }}
            .rec-strong-buy {{ background: linear-gradient(135deg, #27ae60, #2ecc71); color: white; }}
            .rec-buy {{ background: linear-gradient(135deg, #3498db, #2980b9); color: white; }}
            .rec-caution {{ background: linear-gradient(135deg, #f39c12, #e67e22); color: white; }}
            .rec-avoid {{ background: linear-gradient(135deg, #e74c3c, #c0392b); color: white; }}
            
            .metrics-grid {{ 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
                gap: 15px; 
                margin: 20px 0;
            }}
            .metric {{ 
                background: #f8f9fa; 
                padding: 20px; 
                border-radius: 10px;
                text-align: center;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }}
            .metric-label {{ 
                font-size: 0.9em; 
                color: #666; 
                margin-bottom: 5px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            .metric-value {{ 
                font-size: 1.5em; 
                font-weight: bold; 
                color: #2c3e50; 
            }}
            
            .section {{ 
                margin: 30px 0; 
                padding: 25px; 
                background: #f8f9fa;
                border-radius: 12px;
                border-left: 5px solid #3498db;
            }}
            .section h3 {{ 
                margin-top: 0; 
                color: #2c3e50;
                font-size: 1.3em;
            }}
            
            .size-grid {{ 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); 
                gap: 15px; 
                margin: 20px 0;
            }}
            .size-card {{ 
                background: white; 
                padding: 20px; 
                border-radius: 10px; 
                border: 1px solid #ddd;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                transition: transform 0.2s;
            }}
            .size-card:hover {{ transform: translateY(-2px); }}
            .size-title {{ 
                font-weight: bold; 
                color: #2c3e50; 
                margin-bottom: 15px;
                font-size: 1.1em;
                border-bottom: 2px solid #3498db;
                padding-bottom: 5px;
            }}
            
            table {{ 
                width: 100%; 
                border-collapse: collapse; 
                margin: 15px 0;
                background: white;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }}
            th, td {{ 
                padding: 12px 15px; 
                text-align: left; 
                border-bottom: 1px solid #eee; 
            }}
            th {{ 
                background: #34495e; 
                color: white;
                font-weight: 600;
                text-transform: uppercase;
                font-size: 0.9em;
                letter-spacing: 1px;
            }}
            tr:hover {{ background: #f8f9fa; }}
            
            .back-link {{ 
                position: fixed; 
                top: 30px; 
                right: 30px; 
                background: linear-gradient(135deg, #e74c3c, #c0392b);
                color: white; 
                padding: 12px 20px; 
                text-decoration: none; 
                border-radius: 25px;
                box-shadow: 0 4px 15px rgba(231, 76, 60, 0.3);
                font-weight: bold;
                transition: transform 0.2s;
                z-index: 1000;
            }}
            .back-link:hover {{ 
                transform: scale(1.05);
                box-shadow: 0 6px 20px rgba(231, 76, 60, 0.4);
            }}
            
            .quality-excellent {{ border-left-color: #27ae60; }}
            .quality-good {{ border-left-color: #3498db; }}
            .quality-fair {{ border-left-color: #f39c12; }}
            .quality-poor {{ border-left-color: #e74c3c; }}
            
            .highlight {{ 
                background: linear-gradient(135deg, #fff, #f8f9fa);
                border: 2px solid #3498db;
                border-radius: 10px;
                padding: 20px;
                margin: 20px 0;
            }}
        </style>
    </head>
    <body>
        <a href="/" class="back-link">← Back to Main</a>
        
        <div class="container">
            <div class="header">
                <h1>🔍 Comprehensive Shoe Analysis</h1>
                <h2>{query}</h2>
                <p>Analysis completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <div class="content">
                <!-- Priority Section - Market Summary -->
                <div class="priority-section">
                    <h2>💰 MARKET SUMMARY & RECOMMENDATION</h2>
                    <div class="recommendation {get_rec_class(market.get('recommended_action', ''))}">
                        {market.get('recommended_action', 'No recommendation available')}
                    </div>
                    
                    <div class="metrics-grid">
                        <div class="metric">
                            <div class="metric-label">Current Market Price</div>
                            <div class="metric-value">{market.get('current_market_price', 'N/A')}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Sales Velocity</div>
                            <div class="metric-value">{market.get('sales_velocity', 'N/A')}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Market Activity</div>
                            <div class="metric-value">{market.get('market_activity', 'N/A')}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Price Range</div>
                            <div class="metric-value">{market.get('price_range', 'N/A')}</div>
                        </div>
                    </div>
                </div>
                
                <!-- Shoe Identification -->
                <div class="section">
                    <h3>👟 SHOE IDENTIFICATION</h3>
                    <table>
                        <tr><th>Property</th><th>Value</th></tr>
                        <tr><td>Name</td><td>{shoe_id.get('name', 'Unknown')}</td></tr>
                        <tr><td>Brand</td><td>{shoe_id.get('brand', 'Unknown')}</td></tr>
                        <tr><td>SKU</td><td>{shoe_id.get('sku', 'N/A')}</td></tr>
                        <tr><td>Colorway</td><td>{shoe_id.get('colorway', 'N/A')}</td></tr>
                        <tr><td>Release Date</td><td>{shoe_id.get('release_date', 'N/A')}</td></tr>
                        <tr><td>Retail Price</td><td>${shoe_id.get('retail_price', 0)}</td></tr>
                    </table>
                </div>
                
                <!-- Sales Performance -->
                <div class="section">
                    <h3>📈 SALES PERFORMANCE</h3>
                    <div class="metrics-grid">
                        <div class="metric">
                            <div class="metric-label">Total Sales</div>
                            <div class="metric-value">{performance.get('total_sales', 0)}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Active Sizes</div>
                            <div class="metric-value">{performance.get('active_sizes', 0)}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Analysis Period</div>
                            <div class="metric-value">{performance.get('analysis_period', 'N/A')}</div>
                        </div>
                    </div>
                    
                    {build_top_sizes_table(performance.get('top_performing_sizes', []))}
                </div>
                
                <!-- Size Breakdown -->
                {build_size_breakdown_section(size_breakdown)}
                
                <!-- Alias Pricing Insights -->
                {build_alias_pricing_section(pricing.get('alias_pricing', {}))}
                
                <!-- Data Quality Assessment -->
                <div class="section quality-{quality.get('overall_score', 'unknown').lower()}">
                    <h3>📊 DATA QUALITY ASSESSMENT</h3>
                    <div class="metrics-grid">
                        <div class="metric">
                            <div class="metric-label">Overall Quality</div>
                            <div class="metric-value">{quality.get('overall_score', 'Unknown')}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">StockX Data</div>
                            <div class="metric-value">{quality.get('stockx_quality', 'Unknown')}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Alias Data</div>
                            <div class="metric-value">{quality.get('alias_quality', 'Unknown')}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Volume Data</div>
                            <div class="metric-value">{quality.get('volume_quality', 'Unknown')}</div>
                        </div>
                    </div>
                    
                    {build_warnings_section(quality.get('warnings', []))}
                </div>
                
                <!-- Processing Info -->
                <div class="section">
                    <h3>ℹ️ ANALYSIS INFO</h3>
                    <p><strong>Processing Time:</strong> {result.get('processing_time', 0)} seconds</p>
                    <p><strong>Timestamp:</strong> {result.get('timestamp', 'Unknown')}</p>
                    <p><em>Analysis combines real-time StockX market data with Alias sales volume insights</em></p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

def get_rec_class(recommendation: str) -> str:
    """Get CSS class for recommendation styling"""
    if not recommendation:
        return 'rec-avoid'
    rec_lower = recommendation.lower()
    if 'strong buy' in rec_lower or '🔥' in recommendation:
        return 'rec-strong-buy'
    elif 'buy' in rec_lower or 'consider' in rec_lower or '📈' in recommendation:
        return 'rec-buy'
    elif 'caution' in rec_lower or '⚠️' in recommendation:
        return 'rec-caution'
    elif 'avoid' in rec_lower or '❌' in recommendation:
        return 'rec-avoid'
    else:
        return 'rec-buy'

def build_top_sizes_table(top_sizes: list) -> str:
    """Build HTML for top performing sizes table"""
    if not top_sizes:
        return ""
    
    html = """
    <div class="highlight">
        <h4>🏆 Top Performing Sizes</h4>
        <table>
            <tr><th>Size</th><th>Sales Count</th><th>Velocity/Day</th><th>Data Status</th></tr>
    """
    for size_data in top_sizes[:5]:
        limit_indicator = "API Limited" if size_data.get('hit_limit') else "Complete"
        limit_symbol = "≥" if size_data.get('hit_limit') else ""
        html += f"""
            <tr>
                <td>Size {size_data['size']}</td>
                <td>{limit_symbol}{size_data['sales']}</td>
                <td>{limit_symbol}{size_data['velocity']:.2f}</td>
                <td>{limit_indicator}</td>
            </tr>
        """
    html += "</table></div>"
    return html

def build_size_breakdown_section(size_breakdown: dict) -> str:
    """Build HTML for size breakdown section"""
    if not size_breakdown:
        return ""
    
    # Sort sizes numerically where possible
    try:
        sorted_sizes = sorted(size_breakdown.keys(), key=lambda x: float(str(x)) if str(x).replace('.', '').isdigit() else 999)
    except:
        sorted_sizes = sorted(size_breakdown.keys())
    
    html = """
    <div class="section">
        <h3>📏 SIZE-BY-SIZE BREAKDOWN</h3>
        <div class="size-grid">
    """
    
    for size in sorted_sizes[:12]:  # Show top 12 sizes
        size_data = size_breakdown[size]
        stockx = size_data.get('stockx_data', {})
        volume = size_data.get('volume_data', {})
        insights = size_data.get('combined_insights', {})
        
        html += f"""
        <div class="size-card">
            <div class="size-title">Size {size}</div>
            <p><strong>StockX Market:</strong><br>
            Bid: ${stockx.get('highest_bid', 'N/A')}<br>
            Ask: ${stockx.get('lowest_ask', 'N/A')}</p>
            
            <p><strong>Sales Volume:</strong><br>
            Count: {volume.get('sales_count', 0)}<br>
            Velocity: {volume.get('velocity_per_day', 0):.2f}/day</p>
            
            <p><strong>Insight:</strong><br>
            <em>{insights.get('recommendation', 'No data available')}</em></p>
        </div>
        """
    
    html += "</div></div>"
    return html

def build_alias_pricing_section(alias_pricing: dict) -> str:
    """Build HTML for Alias pricing section"""
    if not alias_pricing or not any(alias_pricing.values()):
        return ""
    
    html = """
    <div class="section">
        <h3>💎 ALIAS PRICING INSIGHTS</h3>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
    """
    
    pricing_items = [
        ('Consignment Price', alias_pricing.get('consignment_price')),
        ('Ship-to-Verify Price', alias_pricing.get('ship_to_verify_price')),
        ('Lowest Consigned', alias_pricing.get('lowest_consigned')),
        ('Last Consigned Price', alias_pricing.get('last_consigned_price')),
        ('Last Consigned Date', alias_pricing.get('last_consigned_date'))
    ]
    
    for label, value in pricing_items:
        if value is not None:
            display_value = f"${value}" if isinstance(value, (int, float)) else str(value)
            html += f"<tr><td>{label}</td><td>{display_value}</td></tr>"
    
    html += "</table></div>"
    return html

def build_warnings_section(warnings: list) -> str:
    """Build HTML for warnings section"""
    if not warnings:
        return ""
    
    html = "<div class='highlight'><h4>⚠️ Data Quality Warnings:</h4><ul>"
    for warning in warnings:
        html += f"<li>{warning}</li>"
    html += "</ul></div>"
    return html

@app.route('/downloads')
def list_downloads():
    """List available output files for download"""
    download_dirs = ['pricing_tools', 'uploads']
    files = []
    
    for directory in download_dirs:
        abs_dir = os.path.join(app.root_path, directory)
        if os.path.exists(abs_dir):
            try:
                dir_listing = os.listdir(abs_dir)
            except Exception:
                dir_listing = []
            for filename in dir_listing:
                # Look for CSV files and enhanced output files (which might be .txt or .csv)
                if (filename.endswith('.csv') or 
                    (filename.startswith('stockx_enhanced_') and (filename.endswith('.txt') or filename.endswith('.csv'))) or
                    (filename.startswith('sales_volume_analysis_') and filename.endswith('.csv'))):
                    filepath = os.path.join(abs_dir, filename)
                    try:
                        file_info = {
                            'name': filename,
                            'path': directory,  # keep relative path for URL
                            'size': os.path.getsize(filepath),
                            'modified': datetime.fromtimestamp(os.path.getmtime(filepath)).strftime('%Y-%m-%d %H:%M:%S')
                        }
                        files.append(file_info)
                    except (OSError, IOError):
                        # Skip files that can't be accessed
                        continue
    
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
                    <th>Actions</th>
                </tr>
                {% for file in files %}
                <tr>
                    <td>{{ file.name }}</td>
                    <td>{{ file.path }}</td>
                    <td>{{ "%.1f"|format(file.size/1024) }} KB</td>
                    <td>{{ file.modified }}</td>
                    <td>
                        <a href="/view_csv/{{ file.path }}/{{ file.name }}" class="download-btn" style="background: #28a745; margin-right: 5px;">
                            View
                        </a>
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
        abs_dir = os.path.join(app.root_path, directory)
        # Prevent path traversal
        if not abs_dir.startswith(app.root_path):
            flash('Invalid path')
            return redirect(url_for('list_downloads'))
        return send_from_directory(abs_dir, filename, as_attachment=True)
    except FileNotFoundError:
        flash('File not found')
        return redirect(url_for('list_downloads'))

@app.route('/view_csv/<path:directory>/<filename>')
def view_csv(directory, filename):
    """View CSV file contents in browser"""
    try:
        import csv
        abs_dir = os.path.join(app.root_path, directory)
        filepath = os.path.join(abs_dir, filename)
        
        if not os.path.exists(filepath):
            flash('File not found')
            return redirect(url_for('list_downloads'))
        
        # Read CSV data
        csv_data = []
        with open(filepath, 'r', encoding='utf-8') as file:
            csv_reader = csv.reader(file)
            for row in csv_reader:
                csv_data.append(row)
        
        if not csv_data:
            flash('Empty CSV file')
            return redirect(url_for('list_downloads'))
        
        headers = csv_data[0] if csv_data else []
        rows = csv_data[1:] if len(csv_data) > 1 else []
        
        # Limit rows for performance (show first 100 rows)
        if len(rows) > 100:
            rows = rows[:100]
            truncated = True
        else:
            truncated = False
        
        return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>View CSV: {{ filename }} - StockX Tools</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                table { border-collapse: collapse; width: 100%; font-size: 12px; }
                th, td { padding: 8px; text-align: left; border: 1px solid #ddd; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
                th { background-color: #f2f2f2; font-weight: bold; }
                .back-btn { background: #007bff; color: white; text-decoration: none; padding: 8px 16px; border-radius: 4px; margin-bottom: 20px; display: inline-block; }
                .download-btn { background: #28a745; color: white; text-decoration: none; padding: 8px 16px; border-radius: 4px; margin-left: 10px; }
                .truncated-notice { background: #fff3cd; padding: 10px; border: 1px solid #ffeeba; border-radius: 4px; margin: 10px 0; }
            </style>
        </head>
        <body>
            <h1>📄 {{ filename }}</h1>
            <a href="/downloads" class="back-btn">← Back to Downloads</a>
            <a href="/download/{{ directory }}/{{ filename }}" class="download-btn">Download File</a>
            
            {% if truncated %}
            <div class="truncated-notice">
                <strong>Notice:</strong> Showing first 100 rows only. Download the full file to see all data.
            </div>
            {% endif %}
            
            <h3>File Info</h3>
            <p><strong>Location:</strong> {{ directory }}/{{ filename }}</p>
            <p><strong>Total Rows:</strong> {{ total_rows }}</p>
            <p><strong>Columns:</strong> {{ headers|length }}</p>
            
            {% if headers %}
            <h3>CSV Data</h3>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            {% for header in headers %}
                            <th>{{ header }}</th>
                            {% endfor %}
                        </tr>
                    </thead>
                    <tbody>
                        {% for row in rows %}
                        <tr>
                            {% for cell in row %}
                            <td title="{{ cell }}">{{ cell }}</td>
                            {% endfor %}
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% else %}
            <p>No data to display</p>
            {% endif %}
        </body>
        </html>
        """, filename=filename, directory=directory, headers=headers, rows=rows, 
             truncated=truncated, total_rows=len(csv_data))
        
    except Exception as e:
        flash(f'Error reading CSV file: {str(e)}')
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

@socketio.on('analyze_shoe_progressive')
def handle_progressive_analysis(data):
    """Handle progressive shoe analysis with real-time updates via WebSocket"""
    shoe_query = data.get('shoe_query', '').strip()
    size = data.get('size', '10').strip()
    
    if not shoe_query:
        emit('error', {'message': 'Please enter a shoe name or SKU'})
        return
    
    try:
        # Import progressive loading analyzer
        sys.path.append(os.path.join(os.getcwd(), 'pricing_tools'))
        from progressive_loading_analyzer import ProgressiveLoadingAnalyzer
        
        def progress_callback(update):
            """Send progress updates via WebSocket"""
            emit('progress', update)
        
        analyzer = ProgressiveLoadingAnalyzer(progress_callback=progress_callback, max_workers=3)
        result = analyzer.analyze_shoe_with_progressive_loading(shoe_query, size)
        
        # Send final result
        emit('result', result)
        
    except Exception as e:
        emit('error', {'message': f'Analysis failed: {str(e)}'})

@app.route('/refresh-token', methods=['POST'])
def refresh_token_endpoint():
    """Web endpoint to manually refresh the StockX token"""
    try:
        print("🔄 Manual token refresh requested via web interface")
        
        # Check if we can refresh
        if not can_refresh_token():
            return jsonify({
                'success': False,
                'message': 'No refresh token available - full authentication required',
                'action': 'authenticate'
            }), 400
        
        # Attempt refresh
        if refresh_access_token():
            # Verify the refresh worked
            is_auth, error_msg, action = robust_authentication_check()
            if is_auth:
                return jsonify({
                    'success': True,
                    'message': 'Token refreshed successfully!',
                    'action': 'success'
                })
            else:
                return jsonify({
                    'success': False,
                    'message': f'Token refresh completed but verification failed: {error_msg}',
                    'action': action
                }), 400
        else:
            return jsonify({
                'success': False,
                'message': 'Token refresh failed - check logs for details',
                'action': 'authenticate'
            }), 500
            
    except Exception as e:
        print(f"❌ Error in token refresh endpoint: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Token refresh error: {str(e)}',
            'action': 'error'
        }), 500

@app.route('/token-status')
def token_status():
    """Get current token status and information"""
    try:
        if not os.path.exists(TOKEN_FILE):
            return jsonify({
                'has_token': False,
                'message': 'No token file found',
                'action': 'authenticate'
            })
        
        with open(TOKEN_FILE, 'r') as f:
            tokens = json.load(f)
        
        # Check if token is valid
        is_auth, error_msg, action = robust_authentication_check()
        
        token_info = {
            'has_token': True,
            'is_valid': is_auth,
            'has_refresh_token': 'refresh_token' in tokens,
            'expires_in': tokens.get('expires_in', 'Unknown'),
            'token_type': tokens.get('token_type', 'Bearer'),
            'last_refreshed': tokens.get('refreshed_at', 'Unknown'),
            'error_message': error_msg if not is_auth else None,
            'recommended_action': action
        }
        
        return jsonify(token_info)
        
    except Exception as e:
        return jsonify({
            'has_token': False,
            'message': f'Error reading token: {str(e)}',
            'action': 'error'
        }), 500
@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'greengoatlogoiphone.png', mimetype='image/png')

@app.route('/static/greengoatlogoiphone.png')
def goat_icon():
    return send_from_directory('static', 'greengoatlogoiphone.png', mimetype='image/png')

if __name__ == "__main__":
    try:
        port = int(os.getenv("PORT", 5000))
        print("🌐 Starting StockX Tools Web Interface...")
        print(f"📱 Access at: http://0.0.0.0:{port}")
        print("🔄 Real-time updates via WebSocket")
        print("=" * 50)
        # Ensure a token is present or automatically recovered
        try:
            if ensure_token_available():
                print("✅ Token file available")
            else:
                print("⚠️ No token available at startup - use /auth/start or /refresh-token when ready")
        except Exception as e:
            print(f"⚠️ Token ensure step warning: {e}")
        try:
            start_enhanced_token_refresh_thread()
        except Exception as e:
            print(f"⚠️ Warning: Could not start token refresh thread: {e}")
        port = int(os.getenv("PORT", 5000))
        socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True, use_reloader=False, log_output=True)
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        try:
            port = int(os.getenv("PORT", 5000))
            socketio.run(app, host="0.0.0.0", port=port, debug=False, use_reloader=False)
        except Exception as fallback_error:
            print(f"❌ Fallback also failed: {fallback_error}")
            import sys
            sys.exit(1)
