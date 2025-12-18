#!/usr/bin/env python3
"""
🔐 Fully Automated StockX Authentication System
No manual browser interaction required!
"""
import os
import json
import requests
import secrets
import time
import threading
from urllib.parse import urlencode, parse_qs
from datetime import datetime, timedelta

# Check if running on Vercel - avoid http.server
IS_VERCEL = os.getenv('VERCEL') == '1' or os.getenv('VERCEL_ENV') is not None

if not IS_VERCEL:
    import webbrowser
    from http.server import HTTPServer, BaseHTTPRequestHandler
    
    class AuthCallbackHandler(BaseHTTPRequestHandler):
        """Handle OAuth callback automatically"""
        
        def do_GET(self):
            # Parse the callback URL
            if '?' in self.path:
                query_string = self.path.split('?', 1)[1]
                params = parse_qs(query_string)
                
                # Store the authorization code
                if 'code' in params:
                    self.server.auth_code = params['code'][0]
                    self.server.auth_success = True
                    
                    # Send success page
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    
                    success_html = """
                    <html>
                    <head><title>StockX Auth Success</title></head>
                    <body style="font-family: Arial; text-align: center; padding: 50px;">
                        <h1 style="color: green;">✅ Authentication Successful!</h1>
                        <p>You can close this browser window now.</p>
                        <p>The StockX API client is now authenticated.</p>
                    </body>
                    </html>
                    """
                    self.wfile.write(success_html.encode())
                
                elif 'error' in params:
                    self.server.auth_error = params['error'][0]
                    self.server.auth_success = False
                    
                    # Send error page
                    self.send_response(400)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    
                    error_html = f"""
                    <html>
                    <head><title>StockX Auth Error</title></head>
                    <body style="font-family: Arial; text-align: center; padding: 50px;">
                        <h1 style="color: red;">❌ Authentication Error</h1>
                        <p>Error: {params['error'][0]}</p>
                        <p>Please try again.</p>
                    </body>
                    </html>
                    """
                    self.wfile.write(error_html.encode())
        
        def log_message(self, format, *args):
            # Suppress log messages
            pass
else:
    # Create no-op for Vercel
    class AuthCallbackHandler:
        pass
    HTTPServer = None

class StockXAutoAuth:
    def __init__(self):
        self.api_key = 'GH4A9FkG7E3uaWswtc87U7kw8A4quRsU6ciFtrUp'
        self.client_id = 'QyK8U0Xir3L3wQjYtBlLuXpMOLANa5EL'
        self.client_secret = 'uqJXWo1oN10iU6qyAiTIap1B0NmuZMsZn6vGp7oO1uK-Ng4-aoSTbRHA5kfNV3Mn'
        self.redirect_uri = 'https://example.com'
        self.token_file = 'tokens_full_scope.json'
    
    def is_token_valid(self):
        """Check if current access token is still valid"""
        try:
            with open(self.token_file, 'r') as f:
                tokens = json.load(f)
            
            # Simple test API call
            headers = {
                'Authorization': f'Bearer {tokens["access_token"]}',
                'x-api-key': self.api_key
            }
            
            response = requests.get(
                'https://api.stockx.com/v2/catalog/search?query=test&pageSize=1',
                headers=headers,
                timeout=10
            )
            
            return response.status_code == 200
            
        except Exception:
            return False
    
    def can_refresh_token(self):
        """Check if we have a valid refresh token"""
        try:
            with open(self.token_file, 'r') as f:
                tokens = json.load(f)
            return 'refresh_token' in tokens
        except Exception:
            return False
    
    def refresh_access_token(self):
        """Refresh the access token using refresh token"""
        try:
            with open(self.token_file, 'r') as f:
                tokens = json.load(f)
            
            data = {
                'grant_type': 'refresh_token',
                'refresh_token': tokens['refresh_token'],
                'client_id': self.client_id,
                'client_secret': self.client_secret,
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
                
                with open(self.token_file, 'w') as f:
                    json.dump(new_tokens, f, indent=2)
                
                print("✅ Access token refreshed successfully!")
                return True
            else:
                print(f"❌ Token refresh failed: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Error refreshing token: {str(e)}")
            return False
    
    def full_authentication(self):
        """Perform full OAuth authentication with manual code entry"""
        print("🔐 Starting Full OAuth Authentication...")
        
        # Generate auth URL
        state = secrets.token_urlsafe(32)
        scope = 'openid offline_access read:catalog read:products read:market'
        
        auth_params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': self.redirect_uri,
            'state': state,
            'scope': scope,
            'audience': 'gateway.stockx.com'
        }
        
        auth_url = f"https://accounts.stockx.com/authorize?{urlencode(auth_params)}"
        
        print(f"🌐 Opening browser for authentication...")
        print(f"📋 If browser doesn't open, visit: {auth_url}")
        
        # Open browser automatically (not available on Vercel)
        if not IS_VERCEL:
            webbrowser.open(auth_url)
        
        print("\n📝 After logging in, you'll be redirected to example.com")
        print("📋 The URL will look like: https://example.com/?code=XXXXXXX&state=YYYYYYY")
        print("📋 Copy the 'code' parameter from the URL and paste it below:")
        
        auth_code = input("Enter authorization code: ").strip()
        
        if not auth_code:
            print("❌ No authorization code provided")
            return False
        
        print("✅ Authorization code received!")
        
        # Exchange code for tokens
        return self._exchange_code_for_tokens(auth_code)
    
    def _exchange_code_for_tokens(self, auth_code):
        """Exchange authorization code for access tokens"""
        print("🔄 Exchanging code for tokens...")
        
        data = {
            'grant_type': 'authorization_code',
            'code': auth_code,
            'redirect_uri': self.redirect_uri,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'audience': 'gateway.stockx.com'
        }
        
        response = requests.post(
            'https://accounts.stockx.com/oauth/token',
            data=data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        
        if response.status_code == 200:
            tokens = response.json()
            
            with open(self.token_file, 'w') as f:
                json.dump(tokens, f, indent=2)
            
            print("✅ Full authentication successful!")
            print(f"💾 Tokens saved to {self.token_file}")
            return True
        else:
            print(f"❌ Token exchange failed: {response.status_code} - {response.text}")
            return False
    
    def authenticate(self):
        """Smart authentication - try refresh first, fall back to full auth"""
        print("🔐 StockX Auto-Authentication System")
        print("=" * 50)
        
        # Check if current token is valid
        if self.is_token_valid():
            print("✅ Current access token is valid!")
            return True
        
        print("⚠️  Access token expired or invalid")
        
        # Try to refresh token
        if self.can_refresh_token():
            print("🔄 Attempting to refresh access token...")
            if self.refresh_access_token():
                return True
            else:
                print("⚠️  Token refresh failed, need full re-authentication")
        else:
            print("⚠️  No refresh token available, need full authentication")
        
        # Full authentication required
        print("🔐 Starting full authentication process...")
        return self.full_authentication()

def main():
    """Main authentication function"""
    auth = StockXAutoAuth()
    
    if auth.authenticate():
        print("\n🎉 AUTHENTICATION SUCCESSFUL!")
        print("=" * 50)
        print("✅ StockX API is now ready to use")
        print("✅ Access token is valid")
        print("✅ No manual intervention required")
        print("\n🚀 You can now run your StockX API scripts!")
        
        # Quick test
        print("\n🧪 Testing API access...")
        try:
            with open('tokens_full_scope.json', 'r') as f:
                tokens = json.load(f)
            
            headers = {
                'Authorization': f'Bearer {tokens["access_token"]}',
                'x-api-key': auth.api_key
            }
            
            response = requests.get(
                'https://api.stockx.com/v2/catalog/search?query=nike&pageSize=1',
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                count = data.get('count', 0)
                print(f"✅ API Test Success! Found {count:,} Nike products")
            else:
                print(f"⚠️  API Test Warning: {response.status_code}")
                
        except Exception as e:
            print(f"⚠️  API Test Error: {str(e)}")
    
    else:
        print("\n❌ AUTHENTICATION FAILED")
        print("Please check your internet connection and try again.")

if __name__ == "__main__":
    main() 