#!/bin/bash

# Setup Cloudflare Tunnel for PDF API

echo "🌐 Setting up Cloudflare Tunnel for PDF API..."

# Install cloudflared if not already installed
if ! command -v cloudflared &> /dev/null; then
    echo "📦 Installing cloudflared..."
    
    # Download and install cloudflared
    wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
    sudo dpkg -i cloudflared-linux-amd64.deb
    rm cloudflared-linux-amd64.deb
    
    echo "✅ cloudflared installed"
fi

# Create systemd service for cloudflared quick tunnel
echo "⚙️ Creating cloudflared service for PDF API..."
sudo tee /etc/systemd/system/cloudflared-pdf.service > /dev/null <<EOF
[Unit]
Description=Cloudflare Tunnel for PDF API
After=network.target pydf-api.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/Pydf-Api
ExecStart=/usr/local/bin/cloudflared tunnel --url http://localhost:8001
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
sudo systemctl daemon-reload

# Enable and start service
sudo systemctl enable cloudflared-pdf
sudo systemctl start cloudflared-pdf

echo "✅ Cloudflare tunnel started!"
echo "⏳ Waiting for tunnel URL to be generated..."
sleep 20

# Extract and display tunnel URL
TUNNEL_URL=$(sudo journalctl -u cloudflared-pdf -n 100 | grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1)

if [ -n "$TUNNEL_URL" ]; then
    echo "✅ Tunnel URL: $TUNNEL_URL"
    echo "$TUNNEL_URL" > /tmp/pdf_tunnel_url.txt
    
    # Update Google Sheet
    echo "📊 Updating Google Sheet..."
    python3 update_pdf_sheet.py
    
    echo ""
    echo "✅ Setup complete!"
    echo "🔗 PDF API is now accessible at: $TUNNEL_URL"
    echo "📊 URL saved to Google Sheets cell D1"
else
    echo "❌ Could not find tunnel URL. Check logs:"
    echo "   sudo journalctl -u cloudflared-pdf -f"
fi

