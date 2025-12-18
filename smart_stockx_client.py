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

# Check if running on Vercel - BaseHTTPRequestHandler causes issues
IS_VERCEL = os.getenv('VERCEL') == '1' or os.getenv('VERCEL_ENV') is not None

if not IS_VERCEL:
    import webbrowser
    from http.server import HTTPServer, BaseHTTPRequestHandler
    
    class AuthCallbackHandler(BaseHTTPRequestHandler):
        """Handle OAuth callback automatically"""
        
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
                
                success_html = """
                <html>
                <head><title>StockX Auth Success</title></head>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1 style="color: green;">✅ Authentication Successful!</h1>
                    <p>You can close this browser window now.</p>
                </body>
                </html>
                """
                self.wfile.write(success_html.encode())
    
        def log_message(self, format, *args):
            pass
else:
    # Create no-op class for Vercel
    class AuthCallbackHandler:
        pass
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
            with open(self.token_file, 'r') as f:
                tokens = json.load(f)
            
            headers = {
                'Authorization': f'Bearer {tokens["access_token"]}',
                'x-api-key': self.api_key
            }
            
            response = requests.get(
                f'{self.base_url}/catalog/search?query=test&pageSize=1',
                headers=headers,
                timeout=10
            )
            
            return response.status_code == 200
        except Exception:
            return False
    
    def _can_refresh_token(self):
        """Check if we have a valid refresh token"""
        try:
            with open(self.token_file, 'r') as f:
                tokens = json.load(f)
            return 'refresh_token' in tokens
        except Exception:
            return False
    
    def _refresh_access_token(self):
        """Refresh the access token"""
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
                
                if 'refresh_token' not in new_tokens and 'refresh_token' in tokens:
                    new_tokens['refresh_token'] = tokens['refresh_token']
                
                with open(self.token_file, 'w') as f:
                    json.dump(new_tokens, f, indent=2)
                
                print("✅ Token refreshed!")
                return True
            return False
        except Exception:
            return False
    
    def _full_authentication(self):
        """Perform full OAuth authentication"""
        # Generate auth URL
        state = secrets.token_urlsafe(32)
        auth_params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': self.redirect_uri,
            'state': state,
            'scope': 'openid offline_access read:catalog read:products read:market',
            'audience': 'gateway.stockx.com'
        }
        
        auth_url = f"https://accounts.stockx.com/authorize?{urlencode(auth_params)}"
        
        print("🌐 Opening browser for authentication...")
        print(f"📋 If browser doesn't open, visit: {auth_url}")
        webbrowser.open(auth_url)
        
        print("\n📝 After logging in, you'll be redirected to example.com")
        print("📋 Copy the 'code' parameter from the URL and paste it below:")
        
        # Check if we're in a non-interactive environment (like from Flask app)
        import sys
        if not sys.stdin.isatty():
            print("❌ Cannot authenticate in non-interactive environment")
            print("💡 Please authenticate through the web interface first")
            raise Exception("Non-interactive authentication not supported")
        
        auth_code = input("Enter authorization code: ").strip()
        
        if not auth_code:
            raise Exception("No authorization code provided")
        
        self._exchange_code_for_tokens(auth_code)
    
    def _exchange_code_for_tokens(self, auth_code):
        """Exchange authorization code for tokens"""
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
            print("✅ Authentication successful!")
        else:
            raise Exception(f"Token exchange failed: {response.status_code}")
    
    def _get_headers(self):
        """Get authenticated headers"""
        with open(self.token_file, 'r') as f:
            tokens = json.load(f)
        
        return {
            'Authorization': f'Bearer {tokens["access_token"]}',
            'x-api-key': self.api_key,
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
    
    def search_products(self, query, page_size=20, page_number=1):
        """Search for products"""
        params = {
            'query': query,
            'pageSize': min(page_size, 100),
            'pageNumber': page_number
        }
        
        response = requests.get(
            f'{self.base_url}/catalog/search',
            headers=self._get_headers(),
            params=params,
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            
            products = []
            for product in data.get('products', []):
                processed_product = {
                    'id': product.get('productId'),
                    'title': product.get('title', 'Unknown Product'),
                    'brand': product.get('brand', 'Unknown'),
                    'style_id': product.get('styleId', ''),
                    'product_type': product.get('productType', ''),
                    'url_key': product.get('urlKey', ''),
                    'attributes': product.get('productAttributes', {}),
                    'raw': product
                }
                products.append(processed_product)
            
            return {
                'products': products,
                'count': data.get('count', 0),
                'page_number': data.get('pageNumber', 1),
                'page_size': data.get('pageSize', page_size),
                'has_next_page': data.get('hasNextPage', False),
                'query': query
            }
        else:
            raise Exception(f"Search failed: {response.status_code} - {response.text}")
    
    def get_product_details(self, product_id):
        """Get detailed product information"""
        response = requests.get(
            f'{self.base_url}/catalog/products/{product_id}',
            headers=self._get_headers(),
            timeout=15
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Product details failed: {response.status_code}")
    
    def get_market_data(self, product_id):
        """Get market data for a product"""
        response = requests.get(
            f'{self.base_url}/catalog/products/{product_id}/market-data',
            headers=self._get_headers(),
            timeout=15
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Market data failed: {response.status_code}")
    
    def quick_search(self, query, limit=5):
        """Quick search with basic info"""
        result = self.search_products(query, page_size=limit)
        
        print(f"🔍 Search: '{query}' - Found {result['count']:,} products")
        
        for i, product in enumerate(result['products'], 1):
            print(f"   {i}. {product['title']}")
            print(f"      Brand: {product['brand']} | Style: {product['style_id']}")
        
        return result['products']

def demo():
    """Demonstration of the smart client"""
    print("🤖 Smart StockX Client Demo")
    print("=" * 50)
    
    # Initialize client (auto-authenticates)
    client = SmartStockXClient()
    
    # Run searches
    queries = ["jordan 1", "yeezy 350", "nike dunk"]
    
    for query in queries:
        try:
            products = client.quick_search(query, limit=3)
            print()
        except Exception as e:
            print(f"❌ Error searching '{query}': {str(e)}")
    
    print("🎉 Demo complete!")

if __name__ == "__main__":
    demo() 