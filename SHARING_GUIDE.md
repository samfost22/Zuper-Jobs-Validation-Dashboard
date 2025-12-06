# How to Share the Dashboard with Your Team

## Quick Start (Same Network)

**The dashboard is already accessible on your local network!**

### Step 1: Find Your Computer's IP Address
Your current IP is already showing in the dashboard output:
```
http://192.168.1.184:5001
```

### Step 2: Share the URL
Send this URL to your team members:
```
http://192.168.1.184:5001
```

**Requirements:**
- Your team must be on the same WiFi/network as you
- Your computer must be running the dashboard
- No firewall blocking port 5001

---

## Option 1: Keep Running on Your Mac (Local Network Access)

### Make it Always Run

**1. Keep the dashboard running in background:**
```bash
# Stop current instances
pkill -f "python3 dashboard.py"

# Start in background with nohup
cd "/Users/samfoster/zuper-netsuite interals ID"
nohup python3 dashboard.py > dashboard.log 2>&1 &

# Dashboard will keep running even if you close terminal
```

**2. Auto-start on Mac boot (optional):**
Create a LaunchAgent file:

```bash
# Create the plist file
cat > ~/Library/LaunchAgents/com.carbonrobotics.zuper-dashboard.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.carbonrobotics.zuper-dashboard</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>/Users/samfoster/zuper-netsuite interals ID/dashboard.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/samfoster/zuper-netsuite interals ID/dashboard.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/samfoster/zuper-netsuite interals ID/dashboard-error.log</string>
    <key>WorkingDirectory</key>
    <string>/Users/samfoster/zuper-netsuite interals ID</string>
</dict>
</plist>
EOF

# Load it
launchctl load ~/Library/LaunchAgents/com.carbonrobotics.zuper-dashboard.plist

# Dashboard will now start automatically on Mac boot!
```

**Share with team:**
```
http://192.168.1.184:5001
```

---

## Option 2: Deploy to a Cloud Server (Recommended)

Deploy to AWS, Google Cloud, Digital Ocean, or any cloud provider for 24/7 access from anywhere.

### A. Deploy to AWS (Free Tier Eligible)

**1. Launch EC2 Instance:**
- Instance type: t2.micro (free tier)
- OS: Ubuntu 22.04 LTS
- Security Group: Allow port 80 (HTTP)

**2. Connect and setup:**
```bash
# SSH into server
ssh -i your-key.pem ubuntu@your-server-ip

# Install dependencies
sudo apt update
sudo apt install -y python3-pip nginx

# Clone or upload your dashboard files
# You can use scp to copy the folder:
# scp -r "/Users/samfoster/zuper-netsuite interals ID" ubuntu@your-server-ip:/home/ubuntu/

# Install Python packages
cd /home/ubuntu/zuper-netsuite\ interals\ ID
pip3 install -r requirements.txt
pip3 install gunicorn

# Run initial sync
python3 sync_to_database.py

# Start dashboard with gunicorn (production server)
gunicorn -w 4 -b 127.0.0.1:5001 dashboard:app --daemon
```

**3. Setup nginx reverse proxy:**
```bash
sudo nano /etc/nginx/sites-available/zuper-dashboard

# Add this config:
server {
    listen 80;
    server_name your-domain.com;  # or your server IP

    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

# Enable site
sudo ln -s /etc/nginx/sites-available/zuper-dashboard /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

**4. Setup auto-start with systemd:**
```bash
sudo nano /etc/systemd/system/zuper-dashboard.service

# Add this:
[Unit]
Description=Zuper NetSuite Dashboard
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/zuper-netsuite interals ID
ExecStart=/usr/local/bin/gunicorn -w 4 -b 127.0.0.1:5001 dashboard:app
Restart=always

[Install]
WantedBy=multi-user.target

# Enable and start
sudo systemctl enable zuper-dashboard
sudo systemctl start zuper-dashboard
```

**Share with team:**
```
http://your-server-ip
```

### B. Deploy to Heroku (Easiest Cloud Option)

**1. Create Heroku account** (free tier available)

**2. Install Heroku CLI:**
```bash
brew install heroku/brew/heroku
```

**3. Prepare for Heroku:**
```bash
cd "/Users/samfoster/zuper-netsuite interals ID"

# Create Procfile
echo "web: gunicorn dashboard:app" > Procfile

# Create runtime.txt
echo "python-3.11.0" > runtime.txt

# Update requirements.txt
echo "gunicorn==21.2.0" >> requirements.txt

# Initialize git
git init
git add .
git commit -m "Initial commit"
```

**4. Deploy:**
```bash
# Login to Heroku
heroku login

# Create app
heroku create zuper-netsuite-dashboard

# Push to Heroku
git push heroku main

# Your dashboard is now live!
```

**Share with team:**
```
https://zuper-netsuite-dashboard.herokuapp.com
```

### C. Deploy to Railway (Modern & Easy)

**1. Go to railway.app and sign up**

**2. Click "New Project" → "Deploy from GitHub"**

**3. Upload your folder and Railway will auto-detect Flask**

**Share with team:**
```
https://your-app.railway.app
```

---

## Option 3: Use ngrok (Quick Temporary Share)

Perfect for quick demos or testing!

**1. Install ngrok:**
```bash
brew install ngrok
```

**2. Create free ngrok account** at ngrok.com

**3. Expose your local dashboard:**
```bash
ngrok http 5001
```

**4. Share the URL ngrok gives you:**
```
https://abc123.ngrok.io
```

**Note:** Free ngrok URLs change each time. Paid plan gives permanent URLs.

---

## Option 4: Add Password Protection

Add basic authentication to any deployment:

**1. Install additional package:**
```bash
pip3 install flask-httpauth
```

**2. Update dashboard.py:**
```python
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash

auth = HTTPBasicAuth()

users = {
    "admin": generate_password_hash("your-secure-password"),
    "viewer": generate_password_hash("viewer-password")
}

@auth.verify_password
def verify_password(username, password):
    if username in users and check_password_hash(users.get(username), password):
        return username

# Add @auth.login_required to all routes
@app.route('/')
@auth.login_required
def index():
    return render_template('dashboard.html')
```

---

## Recommendation by Team Size

**Small team (2-5 people, same office):**
→ Option 1: Run on your Mac with auto-start

**Medium team (5-20 people, remote workers):**
→ Option 2B: Deploy to Heroku (easiest cloud)

**Large team (20+ people, production use):**
→ Option 2A: Deploy to AWS with proper security

**Quick demo:**
→ Option 3: Use ngrok

---

## Keeping Data Fresh for Team

### Setup Automated Sync (Any Deployment)

**On your Mac (cron job):**
```bash
crontab -e

# Add this line (sync every day at 6 AM)
0 6 * * * cd "/Users/samfoster/zuper-netsuite interals ID" && /usr/local/bin/python3 sync_to_database.py >> sync.log 2>&1
```

**On Cloud Server (cron job):**
```bash
crontab -e

# Add this line
0 6 * * * cd /path/to/dashboard && /usr/bin/python3 sync_to_database.py >> sync.log 2>&1
```

**On Heroku (Heroku Scheduler add-on):**
```bash
heroku addons:create scheduler:standard
heroku addons:open scheduler

# Add daily task:
python3 sync_to_database.py
```

---

## Security Recommendations

1. **Add Authentication** (see Option 4 above)
2. **Use HTTPS** (required for production)
3. **Limit Access** (firewall/VPN for sensitive data)
4. **Change Default Passwords** (if using auth)
5. **Regular Backups** of zuper_netsuite.db

---

## What to Share with Your Team

**Quick Start Email Template:**

```
Subject: Zuper-NetSuite Monitoring Dashboard Now Available

Hi Team,

I've set up a dashboard to monitor our Zuper organizations and NetSuite ID coverage.

Access the dashboard here:
http://192.168.1.184:5001
(Must be on office WiFi)

Features:
- Real-time org monitoring
- NetSuite ID coverage tracking
- Alerts for missing IDs
- Export to CSV

The dashboard updates automatically and alerts us when new organizations
are created without NetSuite IDs.

Current stats:
- 188 organizations
- 94.7% have NetSuite IDs
- 10 need attention

Questions? Let me know!

- Sam
```

---

## Support

Need help deploying? Common issues:

**Port already in use:**
```bash
lsof -i :5001
kill -9 <PID>
```

**Can't access from another computer:**
- Check firewall settings
- Ensure you're on same network
- Try http://192.168.1.184:5001 (not localhost)

**Database issues:**
```bash
python3 sync_to_database.py
```
