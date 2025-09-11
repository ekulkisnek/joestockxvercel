#!/usr/bin/env python3
"""
🔄 Manual Token Refresh Script for StockX API
Use this script to manually refresh your StockX token if the web interface doesn't work.
"""
import json
import requests
import os
import time
from datetime import datetime

# Configuration
STOCKX_API_KEY = os.getenv('STOCKX_API_KEY', 'GH4A9FkG7E3uaWswtc87U7kw8A4quRsU6ciFtrUp')
STOCKX_CLIENT_ID = os.getenv('STOCKX_CLIENT_ID', 'QyK8U0Xir3L3wQjYtBlLuXpMOLANa5EL')
STOCKX_CLIENT_SECRET = os.getenv('STOCKX_CLIENT_SECRET', 'uqJXWo1oN10iU6qyAiTIap1B0NmuZMsZn6vGp7oO1uK-Ng4-aoSTbRHA5kfNV3Mn')
TOKEN_FILE = 'tokens_full_scope.json'

def check_token_status():
    """Check current token status"""
    print("🔍 Checking current token status...")
    
    if not os.path.exists(TOKEN_FILE):
        print("❌ No token file found")
        return False, "No token file"
    
    try:
        with open(TOKEN_FILE, 'r') as f:
            tokens = json.load(f)
        
        print(f"📅 Token file last modified: {datetime.fromtimestamp(os.path.getmtime(TOKEN_FILE))}")
        print(f"🆔 Token type: {tokens.get('token_type', 'Unknown')}")
        print(f"⏱️ Expires in: {tokens.get('expires_in', 'Unknown')} seconds")
        print(f"🔄 Has refresh token: {'Yes' if 'refresh_token' in tokens else 'No'}")
        
        if 'refreshed_at' in tokens:
            refresh_time = datetime.fromtimestamp(tokens['refreshed_at'])
            print(f"🔄 Last refreshed: {refresh_time}")
        
        # Test the token
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
            print("✅ Token is valid and working!")
            return True, "Valid"
        elif response.status_code == 401:
            print("❌ Token is expired or invalid")
            return False, "Expired"
        else:
            print(f"⚠️ Unexpected response: {response.status_code}")
            return False, f"HTTP {response.status_code}"
            
    except Exception as e:
        print(f"❌ Error checking token: {str(e)}")
        return False, str(e)

def refresh_token():
    """Refresh the access token"""
    print("🔄 Attempting to refresh token...")
    
    try:
        with open(TOKEN_FILE, 'r') as f:
            tokens = json.load(f)
        
        if 'refresh_token' not in tokens:
            print("❌ No refresh token available")
            return False
        
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
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=15
        )
        
        if response.status_code == 200:
            new_tokens = response.json()
            
            # Preserve refresh token if not provided in response
            if 'refresh_token' not in new_tokens and 'refresh_token' in tokens:
                new_tokens['refresh_token'] = tokens['refresh_token']
                print("🔄 Preserved existing refresh token")
            
            # Add timestamp
            new_tokens['refreshed_at'] = time.time()
            
            # Save tokens
            with open(TOKEN_FILE, 'w') as f:
                json.dump(new_tokens, f, indent=2)
            
            print("✅ Token refreshed successfully!")
            print(f"📅 Refreshed at: {datetime.fromtimestamp(new_tokens['refreshed_at'])}")
            return True
        else:
            print(f"❌ Token refresh failed: {response.status_code}")
            try:
                error_data = response.json()
                print(f"   Error: {error_data}")
            except:
                print(f"   Response: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"❌ Error refreshing token: {str(e)}")
        return False

def main():
    """Main function"""
    print("🔄 StockX Token Refresh Script")
    print("=" * 50)
    
    # Check current status
    is_valid, status = check_token_status()
    
    if is_valid:
        print("\n✅ Token is already valid - no refresh needed!")
        return
    
    print(f"\n⚠️ Token status: {status}")
    
    if status == "No token file":
        print("💡 You need to authenticate first using the web interface")
        return
    
    # Attempt refresh
    if refresh_token():
        print("\n🧪 Testing refreshed token...")
        is_valid, new_status = check_token_status()
        if is_valid:
            print("🎉 Token refresh successful and verified!")
        else:
            print(f"⚠️ Token refresh completed but verification failed: {new_status}")
    else:
        print("\n❌ Token refresh failed")
        print("💡 You may need to re-authenticate using the web interface")

if __name__ == "__main__":
    main()
