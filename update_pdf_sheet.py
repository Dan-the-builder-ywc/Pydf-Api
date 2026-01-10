#!/usr/bin/env python3
"""
Automatically update Google Sheet with PDF API Cloudflare Tunnel URL
Saves to cell D1
"""

import subprocess
import time
import re
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Same sheet as mpy3juice
SHEET_ID = "16vzRuCGHzgRor2lmhRHyEbn8KFLdDnw1hbaF4xeTELo"
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SERVICE_ACCOUNT_FILE = '/home/macproa2338/mpy3juice/service-account.json'  # Reuse existing service account

def get_tunnel_url():
    """Extract tunnel URL from cloudflared-pdf logs"""
    print("⏳ Waiting for cloudflared to generate URL...")
    time.sleep(15)
    
    try:
        # Get recent logs from cloudflared-pdf service
        result = subprocess.run(
            ["journalctl", "-u", "cloudflared-pdf", "--since", "5 minutes ago"],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Find ALL tunnel URLs and get the LAST one (most recent)
        matches = re.findall(r'(https://[a-z0-9-]+\.trycloudflare\.com)', result.stdout)
        if matches:
            tunnel_url = matches[-1]
            print(f"📍 Found {len(matches)} URLs, using most recent: {tunnel_url}")
            return tunnel_url
        else:
            print("❌ ERROR: Could not find tunnel URL in logs")
            return None
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return None

def update_sheet(tunnel_url):
    """Update Google Sheet cell D1 with PDF API tunnel URL"""
    try:
        # Authenticate
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        
        # Build service
        service = build('sheets', 'v4', credentials=creds)
        
        # Update cell D1 (PDF API URL)
        range_name = 'Sheet1!D1'
        values = [[tunnel_url]]
        body = {'values': values}
        
        result = service.spreadsheets().values().update(
            spreadsheetId=SHEET_ID,
            range=range_name,
            valueInputOption='RAW',
            body=body
        ).execute()
        
        print(f"✅ Successfully updated {result.get('updatedCells')} cell(s)")
        return True
        
    except Exception as e:
        print(f"❌ ERROR updating sheet: {e}")
        return False

def main():
    print("🚀 Starting PDF API Cloudflare Tunnel URL updater...")
    
    tunnel_url = get_tunnel_url()
    
    if not tunnel_url:
        print("❌ Failed to get tunnel URL")
        return 1
    
    print(f"🔗 Found tunnel URL: {tunnel_url}")
    
    if update_sheet(tunnel_url):
        print("✅ Google Sheet updated successfully!")
        print(f"📊 Sheet: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")
        print(f"📍 PDF API URL saved to cell D1")
        return 0
    else:
        print("❌ Failed to update Google Sheet")
        return 1

if __name__ == "__main__":
    exit(main())

