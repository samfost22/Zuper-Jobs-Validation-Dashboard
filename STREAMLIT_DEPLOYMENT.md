# Streamlit Dashboard Deployment Guide

## Overview

This guide will walk you through deploying the Zuper Jobs Validation Dashboard to Streamlit Cloud (free tier).

## Prerequisites

- GitHub account
- Zuper API credentials (API key and base URL)
- Git installed on your local machine

## Step 1: Prepare Your Code

1. **Create a local Git repository** (if not already done):
   ```bash
   cd "/path/to/zuper-netsuite interals ID"
   git init
   git add .
   git commit -m "Initial commit - Zuper Jobs Validation Dashboard"
   ```

2. **Create a `.gitignore` file** to exclude sensitive files:
   ```bash
   cat > .gitignore << 'EOF'
   # Secrets
   .streamlit/secrets.toml
   
   # Database
   *.db
   *.db-journal
   
   # Data files
   jobs_data.json
   organizations_data.json
   
   # Python
   __pycache__/
   *.pyc
   *.pyo
   *.pyd
   .Python
   env/
   venv/
   
   # IDE
   .vscode/
   .idea/
   *.swp
   *.swo
   *~
   
   # OS
   .DS_Store
   Thumbs.db
   EOF
   
   git add .gitignore
   git commit -m "Add .gitignore"
   ```

## Step 2: Create GitHub Repository

1. Go to [GitHub](https://github.com) and sign in
2. Click the "+" icon in the top right and select "New repository"
3. Name your repository (e.g., "zuper-jobs-dashboard")
4. Choose "Public" (required for Streamlit Cloud free tier)
5. Click "Create repository"

6. **Push your local code to GitHub**:
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/zuper-jobs-dashboard.git
   git branch -M main
   git push -u origin main
   ```

## Step 3: Set Up Zuper API Credentials Locally

1. **Copy the secrets template**:
   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```

2. **Edit `.streamlit/secrets.toml`** with your Zuper API credentials:
   ```toml
   [zuper]
   api_key = "your-actual-api-key-here"
   base_url = "https://us-east-1.zuperpro.com"
   ```

3. **NEVER commit `secrets.toml` to Git!** (It's already in `.gitignore`)

## Step 4: Test Locally

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the Streamlit app locally**:
   ```bash
   streamlit run streamlit_dashboard.py
   ```

3. **Test the dashboard**:
   - Open your browser to http://localhost:8501
   - Click "Refresh Data from API" to sync data
   - Verify metrics and job listings work correctly
   - Test filters and pagination

## Step 5: Deploy to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io/)

2. Click "New app"

3. Fill in the deployment form:
   - **Repository**: Select your GitHub repo (e.g., `YOUR_USERNAME/zuper-jobs-dashboard`)
   - **Branch**: `main`
   - **Main file path**: `streamlit_dashboard.py`

4. Click "Advanced settings" (optional but recommended):
   - **Python version**: 3.11 (or latest)

5. **Add secrets** (IMPORTANT!):
   - In the "Secrets" section, paste the contents of your local `.streamlit/secrets.toml`:
     ```toml
     [zuper]
     api_key = "your-actual-api-key-here"
     base_url = "https://us-east-1.zuperpro.com"
     ```

6. Click "Deploy!"

7. **Wait for deployment** (usually 2-5 minutes)

## Step 6: Access Your Dashboard

Once deployed, you'll receive a URL like:
```
https://your-app-name.streamlit.app
```

Share this URL with your team!

## Updating the Dashboard

To update your deployed dashboard:

1. **Make changes locally** and test with `streamlit run streamlit_dashboard.py`

2. **Commit and push changes**:
   ```bash
   git add .
   git commit -m "Description of changes"
   git push
   ```

3. Streamlit Cloud will **automatically redeploy** your app within a few minutes

## Updating Secrets

To update API credentials in Streamlit Cloud:

1. Go to your app on [share.streamlit.io](https://share.streamlit.io/)
2. Click the "⋮" menu → "Settings"
3. Click "Secrets" in the sidebar
4. Update the values
5. Click "Save"
6. The app will automatically restart

## Troubleshooting

### "ModuleNotFoundError"
- Check that all dependencies are in `requirements.txt`
- Redeploy the app

### "API credentials not configured"
- Verify secrets are set in Streamlit Cloud
- Check the secret format matches the template exactly

### "Database not found"
- Click "Refresh Data from API" in the sidebar to initialize the database

### App is slow or timing out
- Zuper API sync can take time with many jobs
- Consider running sync less frequently
- Database persists between runs on Streamlit Cloud

## Files Structure

```
zuper-netsuite interals ID/
├── streamlit_dashboard.py          # Main Streamlit app
├── streamlit_sync.py                # API sync module
├── sync_jobs_to_db.py               # Original sync script (used by streamlit_sync)
├── jobs_dashboard.py                # Flask app (kept for reference)
├── database_jobs_schema.sql         # Database schema
├── requirements.txt                 # Python dependencies
├── .streamlit/
│   ├── config.toml                  # Streamlit configuration
│   ├── secrets.toml.example         # Template for secrets
│   └── secrets.toml                 # YOUR secrets (NOT in Git!)
└── STREAMLIT_DEPLOYMENT.md          # This file
```

## Support

For issues or questions:
- Streamlit docs: https://docs.streamlit.io
- Zuper API docs: https://developers.zuper.co

