# Vercel Auto-Deployment Setup

This project is configured for automatic deployment to Vercel.

## ✅ Setup Complete

- ✅ Vercel project linked
- ✅ GitHub repository connected
- ✅ Auto-deployment enabled
- ✅ Production deployment successful

## 🌐 Deployment URLs

- **Production**: https://stockxreplitpricingdeployed.vercel.app
- **Project Dashboard**: https://vercel.com/lukes-projects-fe2e76bf/stockxreplitpricingdeployed

## 🔄 Auto-Deployment

Auto-deployment is enabled through Vercel's GitHub integration. Every push to the `main` branch will automatically trigger a new deployment.

### How it works:
1. Push code to GitHub `main` branch
2. Vercel detects the push
3. Builds and deploys automatically
4. Updates production URL

## 🔐 Environment Variables (Optional)

The app has default values for these variables, but you can override them in Vercel:

- `STOCKX_API_KEY` - StockX API key
- `STOCKX_CLIENT_ID` - StockX OAuth client ID
- `STOCKX_CLIENT_SECRET` - StockX OAuth client secret
- `STOCKX_TOKEN_FILE` - Path to token file (optional)
- `STOCKX_CALLBACK_URL` - OAuth callback URL (optional)
- `STOCKX_REFRESH_TOKEN` - Refresh token (optional)
- `PORT` - Server port (default: 5000)

### To add environment variables:

```bash
vercel env add STOCKX_API_KEY production
vercel env add STOCKX_CLIENT_ID production
vercel env add STOCKX_CLIENT_SECRET production
```

Or use the Vercel dashboard:
1. Go to https://vercel.com/lukes-projects-fe2e76bf/stockxreplitpricingdeployed/settings/environment-variables
2. Add variables for Production, Preview, and Development environments

## 📝 GitHub Actions (Optional)

A GitHub Actions workflow is included at `.github/workflows/deploy.yml` for additional deployment control. To use it:

1. Add `VERCEL_TOKEN` secret to GitHub:
   - Go to: https://github.com/ekulkisnek/stockxreplitpricingdeployed/settings/secrets/actions
   - Add secret: `VERCEL_TOKEN` = `oxUfegMXjwcOUULhpxKaRX9z`

Note: This is optional since Vercel's built-in GitHub integration already handles auto-deployment.

## 🚀 Manual Deployment

To manually deploy:

```bash
vercel --prod
```

## 📁 Project Structure

- `vercel.json` - Vercel configuration
- `api/index.py` - Serverless function handler
- `.vercel/` - Vercel project metadata (gitignored)

## ⚠️ Important Notes

1. **WebSocket Support**: Flask-SocketIO with WebSockets may have limitations on Vercel's serverless architecture. Long-lived connections might not work as expected.

2. **File Storage**: The `uploads/` and `advanced_analysis_results/` directories are gitignored. Consider using Vercel's storage solutions or external services for persistent file storage.

3. **Token Storage**: Token files are gitignored. Use environment variables or external storage for production.

## 🔍 Troubleshooting

- View deployment logs: `vercel logs`
- Inspect deployment: `vercel inspect <deployment-url>`
- Check build logs in Vercel dashboard

