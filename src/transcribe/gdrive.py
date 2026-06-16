"""Google Drive folder URL resolution."""

import time
from pathlib import Path


def get_google_drive_folder_url(folder_path):
    """Get the Google Drive web URL for a folder."""
    try:
        from google.auth import default
        from googleapiclient.discovery import build

        # Get folder name from path
        folder_name = Path(folder_path).name

        # Authenticate using application default credentials (from gcloud)
        credentials, project = default(scopes=["https://www.googleapis.com/auth/drive.readonly"])

        # Set quota project explicitly
        if not project:
            project = "magmamoose-terraform"

        credentials = credentials.with_quota_project(project)

        # Build Drive API service
        service = build("drive", "v3", credentials=credentials)

        # Wait for folder to sync (retry up to 10 times with 5 second delay)
        max_retries = 10
        retry_delay = 5

        for attempt in range(max_retries):
            # Search for folder by name
            query = (
                f"name='{folder_name}' and "
                "mimeType='application/vnd.google-apps.folder' and trashed=false"
            )
            results = (
                service.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields="files(id, name, parents)",
                    pageSize=10,
                )
                .execute()
            )

            files = results.get("files", [])

            if files:
                folder_id = files[0]["id"]
                print(f"✓ Found folder in Google Drive after {attempt + 1} attempt(s)")
                return f"https://drive.google.com/drive/folders/{folder_id}"

            # If not found and not last attempt, wait for sync
            if attempt < max_retries - 1:
                print(f"Waiting for Google Drive to sync folder... ({attempt + 1}/{max_retries})")
                time.sleep(retry_delay)

        print(
            f"Warning: Could not find folder '{folder_name}' in Google Drive "
            f"after {max_retries} attempts"
        )
        print("Google Drive Desktop may still be syncing the folder.")
        return None

    except Exception as e:
        print(f"Warning: Failed to get Google Drive URL: {e}")
        print("Falling back to file:// link")
        return None
