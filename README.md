
# Required setup
Need these two files 
- pyproject.toml
- wrapper.py
'''
npm install -g wrangler@latest
wranger dev

pip install uv
uv tool install workers-py
uv run pywrangler init


'''

# Start the app in local
```
wrangler dev --port 8788
# with remote database
npx wrangler dev --port 8788 --remote
```

# Trigger the scheduled health-check job manually (local dev only)
Cron triggers do not fire automatically in `wrangler dev`. Use this endpoint to invoke the job on demand:
```
curl "http://localhost:8788/__scheduled"
```

# Deploy to Cloudflare Pages
Keep all variables as secret type
```
> Build command: npx wrangler deploy --env production --keep-vars
> Deploy command: npx wrangler deploy --env production --keep-vars
> Put Non-production branch deployment command as : npx wrangler versions upload
```