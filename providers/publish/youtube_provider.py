"""YouTube Publish Provider: uploads finished videos, sets metadata and custom thumbnails
via Google YouTube Data API v3 (OAuth2).
"""

import os
import paths
from providers.base import PublishProvider

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]
CREDENTIALS_FILE = os.getenv("YOUTUBE_CREDENTIALS_FILE", "client_secret.json")


def _token_file() -> str:
    env_token = os.getenv("YOUTUBE_TOKEN_FILE")
    if env_token:
        return env_token
    token_dir = paths.home() / "cache"
    os.makedirs(token_dir, exist_ok=True)
    return str(token_dir / "youtube_token.json")


class YouTubeProvider(PublishProvider):
    """YouTube Data API v3 provider for uploading long-form videos and shorts.

    Supports dry-run mode for testing and CI (SANTA_STUDIO_DRY_RUN=1).
    Uploads default to 'private' privacy status per YouTube API requirements for unverified projects.
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run or os.getenv("SANTA_STUDIO_DRY_RUN", "0").lower() in ("1", "true", "yes")

    def _get_authenticated_service(self):
        if self.dry_run:
            return None

        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as e:
            raise RuntimeError(
                "YouTube publishing requires google-api-python-client and google-auth-oauthlib. "
                "Run: pip install google-api-python-client google-auth-oauthlib"
            ) from e

        token_path = _token_file()
        creds = None
        if os.path.exists(token_path):
            try:
                creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            except Exception:
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(CREDENTIALS_FILE):
                    raise RuntimeError(
                        f"YouTube OAuth credentials file not found at {CREDENTIALS_FILE!r}. "
                        "Download OAuth 2.0 Client ID JSON from Google Cloud Console "
                        "and save as client_secret.json or set YOUTUBE_CREDENTIALS_FILE in .env."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)

            os.makedirs(os.path.dirname(token_path), exist_ok=True)
            with open(token_path, "w") as token:
                token.write(creds.to_json())

        return build("youtube", "v3", credentials=creds)

    def upload(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: list[str],
        thumbnail_path: str = "",
        privacy_status: str = "private",
    ) -> dict:
        if not self.dry_run and not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found at {video_path!r}")

        if self.dry_run:
            import hashlib
            dummy_id = hashlib.md5((title + video_path).encode()).hexdigest()[:11]
            return {
                "video_id": dummy_id,
                "video_url": f"https://www.youtube.com/watch?v={dummy_id}",
                "thumbnail_uploaded": bool(thumbnail_path and os.path.exists(thumbnail_path)),
                "dry_run": True,
            }

        from googleapiclient.http import MediaFileUpload

        youtube = self._get_authenticated_service()

        body = {
            "snippet": {
                "title": title[:100],
                "description": description,
                "tags": tags,
                "categoryId": "27",  # Education / Howto & Style
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
        request = youtube.videos().insert(part=",".join(body.keys()), body=body, media_body=media)

        response = None
        while response is None:
            status, response = request.next_chunk()

        video_id = response.get("id")
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        # Upload thumbnail if available
        thumbnail_uploaded = False
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                thumb_media = MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
                youtube.thumbnails().set(videoId=video_id, media_body=thumb_media).execute()
                thumbnail_uploaded = True
            except Exception:
                thumbnail_uploaded = False

        return {
            "video_id": video_id,
            "video_url": video_url,
            "thumbnail_uploaded": thumbnail_uploaded,
            "dry_run": False,
        }
