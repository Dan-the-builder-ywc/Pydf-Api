#!/bin/bash

# GCP Deployment Script for PDF API Backend

echo "🚀 Deploying PDF API Backend to Google Cloud..."

# Update system
echo "📦 Updating system..."
sudo apt update && sudo apt upgrade -y

# Install Python and pip
echo "🐍 Installing Python..."
sudo apt install python3-pip python3-venv -y

# Install system dependencies for PDF processing
echo "📄 Installing PDF processing dependencies..."
sudo apt install -y \
    libmupdf-dev \
    mupdf-tools \
    python3-dev \
    build-essential

# Install Python dependencies
echo "📚 Installing Python dependencies..."
cd ~/Pydf-Api
sudo pip3 install -r requirements.txt --break-system-packages

# Verify installations
echo "✅ Verifying installations..."
python3 --version
python3 -c "import fitz; print('PyMuPDF version:', fitz.__version__)"

# Create systemd service for auto-start
echo "⚙️ Creating systemd service..."
sudo tee /etc/systemd/system/pydf-api.service > /dev/null <<EOF
[Unit]
Description=PDF API Backend
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/Pydf-Api
Environment="PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/usr/local/bin/uvicorn dapi:app --host 0.0.0.0 --port 8001
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
sudo systemctl daemon-reload

# Enable and start service
sudo systemctl enable pydf-api
sudo systemctl start pydf-api

echo "✅ Deployment complete!"
echo "📊 Check status: sudo systemctl status pydf-api"
echo "📝 View logs: sudo journalctl -u pydf-api -f"
echo "🌐 Backend running at: http://$(curl -s ifconfig.me):8001"
echo ""
echo "🔥 Next steps:"
echo "1. Set up Cloudflare tunnel to expose the API"
echo "2. Run: ./setup_cloudflare_pdf.sh"
echo "3. The tunnel URL will be automatically saved to Google Sheets"

