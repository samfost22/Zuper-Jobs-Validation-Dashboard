#!/usr/bin/env python3
"""
GitHub Artifact Downloader for Streamlit Cloud

Downloads the latest jobs-database artifact from GitHub Actions
to provide persistent data on Streamlit Cloud deployments.
"""

import os
import requests
import zipfile
import io
from pathlib import Path
from datetime import datetime


# Configuration
REPO_OWNER = "samfost22"
REPO_NAME = "Zuper-Jobs-Validation-Dashboard"
ARTIFACT_NAME = "jobs-database"
DATA_DIR = Path(__file__).parent / 'data'


def log(message: str):
    """Print timestamped log message"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def get_github_token() -> str:
    """Get GitHub token from Streamlit secrets or environment"""
    # Try Streamlit secrets first
    try:
        import streamlit as st
        token = st.secrets.get("github", {}).get("token", "")
        if token:
            return token
    except Exception:
        pass

    # Fall back to environment variable
    return os.environ.get("GITHUB_TOKEN", "")


def download_latest_artifact(target_path: str = None) -> bool:
    """
    Download the latest jobs-database artifact from GitHub Actions.

    Args:
        target_path: Where to save the database file. Defaults to data/jobs_validation.db

    Returns:
        True if download succeeded, False otherwise
    """
    if target_path is None:
        DATA_DIR.mkdir(exist_ok=True)
        target_path = str(DATA_DIR / 'jobs_validation.db')

    token = get_github_token()
    if not token:
        log("No GitHub token found - cannot download artifact")
        log("Add github.token to .streamlit/secrets.toml")
        return False

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    try:
        # List artifacts
        log(f"Fetching artifacts from {REPO_OWNER}/{REPO_NAME}...")
        api_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/artifacts"
        response = requests.get(api_url, headers=headers, params={"name": ARTIFACT_NAME})
        response.raise_for_status()

        artifacts = response.json().get("artifacts", [])
        if not artifacts:
            log(f"No '{ARTIFACT_NAME}' artifact found")
            return False

        # Get the most recent artifact
        latest = artifacts[0]  # Already sorted by most recent
        artifact_id = latest["id"]
        artifact_size = latest["size_in_bytes"]
        created_at = latest["created_at"]

        log(f"Found artifact: {artifact_size / 1024 / 1024:.1f}MB (created {created_at})")

        # Download the artifact zip
        download_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/artifacts/{artifact_id}/zip"
        log("Downloading artifact...")

        response = requests.get(download_url, headers=headers, stream=True)
        response.raise_for_status()

        # Extract the database from the zip
        log("Extracting database...")
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            # Find the database file in the zip
            db_files = [f for f in zf.namelist() if f.endswith('.db')]
            if not db_files:
                log("No database file found in artifact")
                return False

            # Extract to target path
            db_filename = db_files[0]
            with zf.open(db_filename) as src:
                with open(target_path, 'wb') as dst:
                    dst.write(src.read())

        file_size = os.path.getsize(target_path)
        log(f"Database downloaded: {file_size / 1024 / 1024:.1f}MB -> {target_path}")
        return True

    except requests.exceptions.HTTPError as e:
        log(f"GitHub API error: {e}")
        if e.response.status_code == 401:
            log("Authentication failed - check your GitHub token")
        elif e.response.status_code == 404:
            log("Repository or artifact not found")
        return False
    except Exception as e:
        log(f"Download failed: {e}")
        return False


def ensure_database_from_artifact(db_path: str = None) -> bool:
    """
    Ensure database exists, downloading from GitHub artifact if needed.

    Args:
        db_path: Path to the database file

    Returns:
        True if database exists (downloaded or already present), False otherwise
    """
    if db_path is None:
        db_path = str(DATA_DIR / 'jobs_validation.db')

    # Check if database already exists
    if os.path.exists(db_path):
        size = os.path.getsize(db_path)
        if size > 0:
            log(f"Database exists: {size / 1024 / 1024:.1f}MB")
            return True

    # Try to download from GitHub
    log("Database not found - attempting to download from GitHub...")
    return download_latest_artifact(db_path)


if __name__ == "__main__":
    # Test the download
    success = download_latest_artifact()
    if success:
        print("Download successful!")
    else:
        print("Download failed")
