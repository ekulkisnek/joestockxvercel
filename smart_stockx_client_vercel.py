#!/usr/bin/env python3
"""
🤖 Smart StockX Client - Vercel-compatible version
No http.server dependencies
"""
import os
import json
import requests
import secrets
import time
import threading
from urllib.parse import urlencode, parse_qs

# No http.server imports - completely removed for Vercel compatibility
AuthCallbackHandler = None
HTTPServer = None

class SmartStockXClient:
    def __init__(self, auto_authenticate=True):
        """Initialize with automatic authentication"""
        self.api_key = 'GH4A9FkG7E3uaWswtc87U7kw8A4quRsU6ciFtrUp'
        self.client_id = 'QyK8U0Xir3L3wQjYtBlLuXpMOLANa5EL'
        self.client_secret = 'uqJXWo1oN10iU6qyAiTIap1B0NmuZMsZn6vGp7oO1uK-Ng4-aoSTbRHA5kfNV3Mn'
        self.redirect_uri = 'https://example.com'
        self.token_file = 'tokens_full_scope.json'
        self.base_url = 'https://api.stockx.com/v2'
        
        # Skip auto-authenticate on Vercel (requires local server)
        if auto_authenticate and not os.getenv('VERCEL'):
            self._ensure_authentication()
    
    def _ensure_authentication(self):
        """Ensure we have valid authentication"""
        if not self._is_token_valid():
            print("🔐 Authentication required...")
            if not self._can_refresh_token():
                print("🌐 Full authentication not available on Vercel")
            elif not self._refresh_access_token():
                print("🌐 Token refresh failed")
    
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
                new_token_data['refresh_token'] = refresh_token
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

