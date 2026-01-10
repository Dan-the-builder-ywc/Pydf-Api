# PDF API - GCP Deployment Guide

## Overview

This guide shows how to deploy the PDF API on the same GCP VM as mpy3juice, sharing resources to minimize costs.

## Architecture

```
GCP VM (e2-micro)
├── mpy3juice backend (port 8050)
│   └── Cloudflare Tunnel → https://xxx.trycloudflare.com (saved to Sheet C1)
└── PDF API backend (port 8001)
    └── Cloudflare Tunnel → https://yyy.trycloudflare.com (saved to Sheet D1)
```

## Prerequisites

1. GCP VM already running with mpy3juice
2. Service account JSON file at `~/Pydf-Api/mpy3juice/service-account.json`
3. Google Sheet ID: `16vzRuCGHzgRor2lmhRHyEbn8KFLdDnw1hbaF4xeTELo`

## Deployment Steps

### Step 1: SSH into GCP VM

```bash
gcloud compute ssh mpy3juice-backend
```

### Step 2: Clone PDF API Repository

```bash
cd ~
git clone https://github.com/Dan-the-builder-ywc/Pydf-Api.git
cd Pydf-Api
```

### Step 3: Make Scripts Executable

```bash
chmod +x deploy_gcp_pdf.sh
chmod +x setup_cloudflare_pdf.sh
chmod +x update_pdf_sheet.py
```

### Step 4: Deploy PDF API

```bash
./deploy_gcp_pdf.sh
```

This will:
- Install Python dependencies
- Install PDF processing libraries (PyMuPDF, etc.)
- Create systemd service `pydf-api`
- Start the API on port 8001

### Step 5: Setup Cloudflare Tunnel

```bash
./setup_cloudflare_pdf.sh
```

This will:
- Install cloudflared (if not already installed)
- Create systemd service `cloudflared-pdf`
- Start the tunnel
- Extract the tunnel URL
- Update Google Sheets cell D1 with the URL

### Step 6: Verify Deployment

```bash
# Check PDF API status
sudo systemctl status pydf-api

# Check Cloudflare tunnel status
sudo systemctl status cloudflared-pdf

# View PDF API logs
sudo journalctl -u pydf-api -f

# View tunnel logs
sudo journalctl -u cloudflared-pdf -f

# Get tunnel URL
cat /tmp/pdf_tunnel_url.txt
```

### Step 7: Test the API

```bash
# Get the tunnel URL
TUNNEL_URL=$(cat /tmp/pdf_tunnel_url.txt)

# Test health endpoint
curl $TUNNEL_URL/health

# Test docs
curl $TUNNEL_URL/docs
```

## Frontend Configuration

The frontend automatically fetches the API URL from Google Sheets cell D1.

### How it works:

1. `public/fetch-api-url.js` runs before the app loads
2. It fetches cell D1 from Google Sheets
3. Stores the URL in localStorage
4. `src/config.ts` reads from localStorage

### Manual Override (for development):

```javascript
// In browser console:
localStorage.setItem('PDF_API_URL', 'http://localhost:8001');
```

## Google Sheets Setup

### Sheet Structure:
- **Cell C1**: mpy3juice API URL (existing)
- **Cell D1**: PDF API URL (new)

### API Key Setup:

1. Go to: https://console.cloud.google.com/apis/credentials
2. Create API Key
3. Restrict to Google Sheets API
4. Update `public/fetch-api-url.js` with your API key

## Useful Commands

### Restart Services

```bash
# Restart PDF API
sudo systemctl restart pydf-api

# Restart Cloudflare tunnel
sudo systemctl restart cloudflared-pdf
```

### Update Code

```bash
cd ~/Pydf-Api
git pull
sudo systemctl restart pydf-api
```

### View Logs

```bash
# PDF API logs
sudo journalctl -u pydf-api -f

# Tunnel logs
sudo journalctl -u cloudflared-pdf -f

# Both together
sudo journalctl -u pydf-api -u cloudflared-pdf -f
```

### Stop Services

```bash
sudo systemctl stop pydf-api
sudo systemctl stop cloudflared-pdf
```

## Troubleshooting

### PDF API won't start

```bash
# Check logs
sudo journalctl -u pydf-api -n 50

# Check if port is in use
sudo lsof -i :8001

# Try manual start
cd ~/Pydf-Api
uvicorn dapi:app --host 0.0.0.0 --port 8001
```

### Cloudflare tunnel not working

```bash
# Check tunnel status
sudo systemctl status cloudflared-pdf

# Restart tunnel
sudo systemctl restart cloudflared-pdf

# Get new URL
sleep 20
sudo journalctl -u cloudflared-pdf -n 100 | grep trycloudflare.com
```

### Google Sheets not updating

```bash
# Check service account file exists
ls -la ~/Pydf-Api/mpy3juice/service-account.json

# Run update script manually
cd ~/Pydf-Api
python3 update_pdf_sheet.py
```

### Dependencies missing

```bash
# Reinstall dependencies
cd ~/Pydf-Api
sudo pip3 install -r requirements.txt --break-system-packages
```

## Cost Estimate

Running both APIs on the same e2-micro instance:
- **Free tier**: $0/month (if within limits)
- **After free tier**: ~$7-9/month

No additional cost for running both services on the same VM!

## Security Notes

1. Both services run on localhost and are only exposed via Cloudflare tunnels
2. No direct internet access to ports 8001 or 8050
3. Cloudflare provides DDoS protection
4. Service account has minimal permissions (Sheets API only)

## Auto-Start on Boot

Both services are configured to start automatically when the VM reboots:
- `pydf-api.service` - PDF API backend
- `cloudflared-pdf.service` - Cloudflare tunnel

## Monitoring

### Check both services:

```bash
sudo systemctl status pydf-api cloudflared-pdf
```

### Resource usage:

```bash
# CPU and memory
htop

# Disk space
df -h

# Network
sudo netstat -tulpn | grep -E '8001|8050'
```

## Next Steps

1. ✅ Deploy PDF API to GCP
2. ✅ Setup Cloudflare tunnel
3. ✅ Update Google Sheets with URL
4. ✅ Configure frontend to fetch URL
5. 🔄 Push frontend changes
6. 🎉 Test end-to-end

---

**Your PDF API is now running on GCP with automatic URL management!** 🚀

