# 🔄 StockX Token Refresh Guide

This guide explains how to handle StockX API token refresh for your deployed Replit application.

## 🚀 Quick Fix for Deployed App

### Option 1: Use the Web Interface (Recommended)
1. Go to your deployed Replit app
2. Look for the **"🔄 Refresh Token"** button on the main page
3. Click it to automatically refresh your token
4. The page will reload to show updated token information

### Option 2: Manual Script
If the web interface doesn't work, run this in your Replit console:
```bash
python refresh_token_manual.py
```

## 🔧 How Token Refresh Works

### Automatic Refresh
- The app automatically starts a background thread that refreshes tokens every 11 hours
- Tokens are refreshed when they reach 80% of their lifetime
- The system preserves refresh tokens for future use

### Manual Refresh
- Use the web interface button for easy refresh
- The system validates the refresh worked before confirming success
- Failed refreshes will show error messages with next steps

## 🌐 Environment Variables for Replit

For better security and deployment, set these environment variables in your Replit secrets:

```bash
STOCKX_API_KEY=your_api_key_here
STOCKX_CLIENT_ID=your_client_id_here
STOCKX_CLIENT_SECRET=your_client_secret_here
STOCKX_CALLBACK_URL=https://your-app-name.replit.app
```

## 🔍 Troubleshooting

### Token Refresh Fails
1. **Check if you have a refresh token**: Look at the token info on the main page
2. **If no refresh token**: You need to re-authenticate completely
3. **If refresh token exists but fails**: Check your internet connection and try again

### Authentication Issues
1. **Callback URL mismatch**: Set `STOCKX_CALLBACK_URL` environment variable
2. **Invalid credentials**: Check your StockX OAuth app settings
3. **Rate limiting**: Wait a few minutes and try again

### Web Interface Not Working
1. **Check browser console**: Look for JavaScript errors
2. **Try manual script**: Run `python refresh_token_manual.py`
3. **Check server logs**: Look for error messages in the Replit console

## 📊 Token Status Endpoints

### Check Token Status
```bash
curl https://your-app.replit.app/token-status
```

### Manual Token Refresh
```bash
curl -X POST https://your-app.replit.app/refresh-token
```

## 🔄 Token Lifecycle

1. **Initial Authentication**: User authenticates via OAuth flow
2. **Token Storage**: Access and refresh tokens stored in `tokens_full_scope.json`
3. **Automatic Refresh**: Background thread refreshes tokens before expiry
4. **Manual Refresh**: Web interface allows manual refresh when needed
5. **Re-authentication**: Full OAuth flow if refresh token expires

## 🛠️ Development vs Production

### Development (Local)
- Uses `http://localhost:5000` as callback URL
- Tokens stored in local file system
- Manual refresh via web interface or script

### Production (Replit)
- Auto-detects Replit environment
- Uses environment variables for configuration
- Supports multiple Replit URL detection methods
- Background token refresh runs automatically

## 📝 Token File Structure

```json
{
  "access_token": "eyJ...",
  "refresh_token": "FKw...",
  "token_type": "Bearer",
  "expires_in": 43200,
  "scope": "openid offline_access",
  "refreshed_at": 1754706132.2132528
}
```

## 🚨 Important Notes

- **Never commit tokens to version control**
- **Refresh tokens can expire** - you may need to re-authenticate
- **Rate limiting applies** - don't refresh too frequently
- **Environment variables override hardcoded values** - use them for security

## 🔗 Related Files

- `app.py` - Main application with token refresh endpoints
- `refresh_token_manual.py` - Manual refresh script
- `auto_auth_system.py` - Standalone authentication system
- `smart_stockx_client.py` - Smart client with auto-refresh
- `tokens_full_scope.json` - Token storage file

## 💡 Pro Tips

1. **Set up environment variables** for better security
2. **Monitor token status** regularly using the web interface
3. **Keep refresh tokens** - they last longer than access tokens
4. **Test token refresh** before deploying to production
5. **Use the manual script** as a backup if web interface fails
