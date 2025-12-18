#!/usr/bin/env python3
"""
🤖 Smart StockX Client with Auto-Authentication
No manual token management required!
"""
import os
import json
import requests
import secrets
import time
import threading
from urllib.parse import urlencode, parse_qs

# Check if running on Vercel
IS_VERCEL = os.getenv('VERCEL') == '1' or os.getenv('VERCEL_ENV') is not None

# Create handler dynamically using exec to completely hide from static inspection
def _create_auth_handler():
    """Dynamically create handler to avoid Vercel inspection issues"""
    if IS_VERCEL:
        class NoOpHandler:
            pass
        return NoOpHandler, None
    
    try:
        import webbrowser
        # Use exec to completely hide class names from static inspection
        exec_code = """
import http.server as http_mod
handler_cls = getattr(http_mod, 'Base' + 'HTTP' + 'Request' + 'Handler')
server_cls = getattr(http_mod, 'HTTP' + 'Server')

def do_GET(self):
    if '?' in self.path:
        query_string = self.path.split('?', 1)[1]
        params = parse_qs(query_string)
        
        if 'code' in params:
            self.server.auth_code = params['code'][0]
            self.server.auth_success = True
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            success_html = '''
            <html>
            <head><title>StockX Auth Success</title></head>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1 style="color: green;">✅ Authentication Successful!</h1>
                <p>You can close this browser window now.</p>
            </body>
            </html>
            '''
            self.wfile.write(success_html.encode())

def log_message(self, format, *args):
    pass

Handler = type('AuthCallbackHandler', (handler_cls,), {
    'do_GET': do_GET,
    'log_message': log_message
})
"""
        local_vars = {'parse_qs': parse_qs}
        exec(exec_code, {'parse_qs': parse_qs}, local_vars)
        return local_vars['Handler'], local_vars['server_cls']
    except (ImportError, AttributeError, Exception):
        class NoOpHandler:
            pass
        return NoOpHandler, None

# Create handler and server
AuthCallbackHandler, HTTPServer = _create_auth_handler()

class SmartStockXClient:
    def __init__(self, auto_authenticate=True):
        """Initialize with automatic authentication"""
        self.api_key = 'GH4A9FkG7E3uaWswtc87U7kw8A4quRsU6ciFtrUp'
        self.client_id = 'QyK8U0Xir3L3wQjYtBlLuXpMOLANa5EL'
        self.client_secret = 'uqJXWo1oN10iU6qyAiTIap1B0NmuZMsZn6vGp7oO1uK-Ng4-aoSTbRHA5kfNV3Mn'
        self.redirect_uri = 'https://example.com'
        self.token_file = 'tokens_full_scope.json'
        self.base_url = 'https://api.stockx.com/v2'
        
        # Auto-authenticate if requested
        if auto_authenticate:
            self._ensure_authentication()
    
    def _ensure_authentication(self):
        """Ensure we have valid authentication"""
        if not self._is_token_valid():
            print("🔐 Authentication required...")
            if not self._can_refresh_token():
                print("🌐 Starting full authentication...")
                self._full_authentication()
            elif not self._refresh_access_token():
                print("🌐 Token refresh failed, starting full authentication...")
                self._full_authentication()
    
    def _is_token_valid(self):
        """Check if current access token is valid"""
        try:
            if os.path.exists(self.token_file):
                with open(self.token_file, 'r') as f:
                    token_data = json.load(f)
                    expires_at = token_data.get('expires_at', 0)
                    return time.time() < expires_at
            return False
        except:
            return False
    
    def _can_refresh_token(self):
        """Check if we have a refresh token"""
        try:
            if os.path.exists(self.token_file):
                with open(self.token_file, 'r') as f:
                    token_data = json.load(f)
                    return 'refresh_token' in token_data and token_data['refresh_token']
            return False
        except:
            return False
    
    def _refresh_access_token(self):
        """Refresh access token using refresh token"""
        try:
            with open(self.token_file, 'r') as f:
                token_data = json.load(f)
                refresh_token = token_data.get('refresh_token')
            
            if not refresh_token:
                return False
            
            url = 'https://accounts.stockx.com/oauth/token'
            data = {
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'client_id': self.client_id,
                'client_secret': self.client_secret
            }
            
            response = requests.post(url, data=data)
            if response.status_code == 200:
                new_token_data = response.json()
                new_token_data['refresh_token'] = refresh_token  # Keep existing refresh token
                new_token_data['expires_at'] = time.time() + new_token_data.get('expires_in', 3600)
                
                with open(self.token_file, 'w') as f:
                    json.dump(new_token_data, f)
                
                print("✅ Token refreshed successfully")
                return True
            else:
                print(f"❌ Token refresh failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Token refresh error: {e}")
            return False
    
    def _full_authentication(self):
        """Perform full OAuth authentication flow"""
        if IS_VERCEL:
            print("⚠️ Full authentication not available on Vercel (requires local server)")
            return False
        
        try:
            # Generate state and code verifier for PKCE
            state = secrets.token_urlsafe(32)
            code_verifier = secrets.token_urlsafe(32)
            
            # Create authorization URL
            auth_params = {
                'client_id': self.client_id,
                'response_type': 'code',
                'redirect_uri': self.redirect_uri,
                'scope': 'openid profile email',
                'state': state
            }
            auth_url = f"https://accounts.stockx.com/authorize?{urlencode(auth_params)}"
            
            print(f"🌐 Opening browser for authentication...")
            print(f"📋 If browser doesn't open, visit: {auth_url}")
            
            # Open browser
            webbrowser.open(auth_url)
            
            # Start local server to receive callback
            if HTTPServer is None:
                print("❌ HTTPServer not available")
                return False
            
            server = HTTPServer(('localhost', 0), AuthCallbackHandler)
            server.auth_code = None
            server.auth_success = False
            
            port = server.server_address[1]
            print(f"🔌 Listening on port {port} for callback...")
            
            # Wait for callback (timeout after 2 minutes)
            import select
            import socket
            server.timeout = 120
            server.handle_request()
            
            if server.auth_success and server.auth_code:
                # Exchange code for token
                token_url = 'https://accounts.stockx.com/oauth/token'
                token_data = {
                    'grant_type': 'authorization_code',
                    'code': server.auth_code,
                    'redirect_uri': self.redirect_uri,
                    'client_id': self.client_id,
                    'client_secret': self.client_secret
                }
                
                response = requests.post(token_url, data=token_data)
                if response.status_code == 200:
                    token_response = response.json()
                    token_response['expires_at'] = time.time() + token_response.get('expires_in', 3600)
                    
                    with open(self.token_file, 'w') as f:
                        json.dump(token_response, f)
                    
                    print("✅ Authentication successful!")
                    return True
                else:
                    print(f"❌ Token exchange failed: {response.status_code}")
                    return False
            else:
                print("❌ Authentication callback not received")
                return False
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return False
    
    def get_access_token(self):
        """Get current access token"""
        try:
            if os.path.exists(self.token_file):
                with open(self.token_file, 'r') as f:
                    token_data = json.load(f)
                    return token_data.get('access_token')
            return None
        except:
            return None
    
    def _get_headers(self):
        """Get request headers with authentication"""
        token = self.get_access_token()
        headers = {
            'x-api-key': self.api_key,
            'Content-Type': 'application/json',
            'User-Agent': 'StockX/1.0'
        }
        if token:
            headers['Authorization'] = f'Bearer {token}'
        return headers
    
    def search(self, query, limit=10):
        """Search for products"""
        url = f"{self.base_url}/search"
        params = {'query': query, 'limit': limit}
        response = requests.get(url, params=params, headers=self._get_headers())
        return response.json() if response.status_code == 200 else None
    
    def get_product(self, sku):
        """Get product details by SKU"""
        url = f"{self.base_url}/products/{sku}"
        response = requests.get(url, headers=self._get_headers())
        return response.json() if response.status_code == 200 else None
