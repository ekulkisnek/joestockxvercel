# 🚀 Replit Deployment Setup Guide

This guide will help you deploy and configure the StockX API authentication system on Replit with zero authentication issues.

## 📋 Prerequisites

1. A Replit account
2. Basic familiarity with environment variables
3. Access to StockX OAuth application settings (if you control them)

## 🔧 Step-by-Step Setup

### 1. Deploy to Replit

1. **Fork or Import** this repository to Replit
2. **Install Dependencies**: Replit should automatically detect and install from `requirements.txt`
3. **Run the Application**: Click the "Run" button

### 2. Configure OAuth Callback URL

This is the **MOST IMPORTANT** step to prevent authentication failures.

#### Option A: Automatic Detection (Recommended)
The system will try to automatically detect your Replit URL. Check the console output when you run the app:

```
🌐 Using REPLIT_DEV_DOMAIN: https://your-app-name.your-username.repl.co
```

#### Option B: Manual Override (If Auto-Detection Fails)
If you see messages like "Callback URL mismatch", set up manual override:

1. **Find Your Replit App URL**:
   - Look at the address bar when your app is running
   - It will be something like: `https://your-app-name.your-username.repl.co`

2. **Set Environment Variable**:
   - Go to your Replit project
   - Click on "Secrets" tab (🔒 icon in the sidebar)
   - Add a new secret:
     - **Key**: `STOCKX_CALLBACK_URL`
     - **Value**: `https://your-actual-app-url.repl.co` (replace with your real URL)

3. **Restart Your App**: Stop and run again

### 3. Update StockX OAuth Settings (If Needed)

If you control the StockX OAuth application, add your callback URL to the allowed list:

1. Add `https://your-app-url.repl.co/auth/callback` to allowed callback URLs
2. Make sure the client ID and secret match those in the code

### 4. Test Authentication

1. **Run Your App** on Replit
2. **Visit the Home Page** - you should see the authentication status
3. **Click "AUTHENTICATE NOW"** if not authenticated
4. **Check for Errors** - if you see callback URL mismatch, follow Option B above

## 🐛 Troubleshooting

### Common Issues and Solutions

#### "Callback URL mismatch" Error
**Problem**: OAuth redirect URL doesn't match StockX settings
**Solution**: 
1. Set `STOCKX_CALLBACK_URL` environment variable (see Option B above)
2. Or update StockX OAuth settings to include your Replit URL

#### "Token file not found" 
**Problem**: First time setup
**Solution**: This is normal - just click "AUTHENTICATE NOW"

#### "Network connection error"
**Problem**: Replit networking issues or API downtime
**Solution**: 
1. Check your internet connection
2. Try again in a few minutes
3. Use the "Full Health Check" to diagnose

#### Auto-refresh not working
**Problem**: Token refresh daemon stopped
**Solution**: 
1. Visit `/auth/health` for diagnosis
2. The system will auto-restart the daemon if possible

### 🏥 Health Check Tool

Visit `/auth/health` for a comprehensive diagnosis:
- ✅ Shows what's working
- ❌ Identifies problems
- 🔄 Attempts automatic fixes
- 📋 Provides specific instructions

## 📱 Environment Variables Reference

| Variable | Purpose | Example |
|----------|---------|---------|
| `STOCKX_CALLBACK_URL` | Manual URL override | `https://myapp.username.repl.co` |
| `REPLIT_DEV_DOMAIN` | Auto-detected by Replit | (automatic) |
| `REPL_SLUG` | Auto-detected by Replit | (automatic) |
| `REPL_OWNER` | Auto-detected by Replit | (automatic) |

## 🔄 Authentication Flow

1. **Initial Setup**: Click "START AUTHENTICATION"
2. **Browser Opens**: Complete OAuth on StockX website
3. **Automatic Return**: Browser redirects back to your app
4. **Token Storage**: Access and refresh tokens saved
5. **Auto-Refresh**: Tokens automatically renewed every 11 hours

## 🚨 Emergency Recovery

If everything breaks:

1. **Reset Authentication**: Click "Reset Authentication" button
2. **Clear Secrets**: Remove `STOCKX_CALLBACK_URL` if set incorrectly
3. **Restart App**: Stop and run again
4. **Start Fresh**: Click "START AUTHENTICATION"

## 🎯 Success Indicators

You know it's working when you see:
- ✅ "AUTHENTICATED - StockX API is ready to use"
- ✅ Green token information display
- ✅ "Auto-refresh daemon is running" in health check
- ✅ Successful API searches

## 📞 Getting Help

If you're still having issues:

1. **Check Health**: Visit `/auth/health` for detailed diagnosis
2. **Console Logs**: Check the Replit console for error messages
3. **Environment Check**: Verify your Replit URL is correct
4. **Manual Override**: Try setting `STOCKX_CALLBACK_URL` manually

## 🔒 Security Notes

- Tokens are stored locally in your Replit environment
- No sensitive data is transmitted except during OAuth
- Refresh tokens allow automatic renewal without re-authentication
- All API calls use HTTPS

---

## 🎉 That's It!

Once set up correctly, the system should work automatically with:
- ✅ Zero-maintenance authentication
- ✅ Automatic token refresh every 11 hours  
- ✅ Intelligent error recovery
- ✅ Clear status reporting

The authentication will persist across Replit restarts and should "just work" without any manual intervention. 