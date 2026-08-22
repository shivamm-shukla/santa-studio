"""YouTube Publish Provider: uploads finished videos, sets metadata and custom thumbnails
via Google YouTube Data API v3 (OAuth2).
"""

import os
from providers.base import PublishProvider

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]
CREDENTIALS_FILE = os.getenv("YOUTUBE_CREDENTIALS_FILE", "client_secret.json")
TOKEN_FILE = os.getenv("YOUTUBE_TOKEN_FILE", "runs/youtube_token.json")


class YouTubeProvider(PublishProvider):
    """YouTube Data API v3 provider for uploading long-form videos and shorts.

    Requires:
    1. OAuth2 Client Secret JSON downloaded from Google Cloud Console
       (set path in .env as YOUTUBE_CREDENTIALS_FILE or place in project root as client_secret.json).
    2. `google-api-python-client` and `google-auth-oauthlib`.

    Uploads default to 'private' privacy status per YouTube API requirements for unverified projects.
    """

    def _get_authenticated_service(self):
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

        creds = None
        if os.path.exists(TOKEN_FILE):
            try:
                creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
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

            os.makedirs(os.path.dirname(TOKEN_FILE) if os.path.dirname(TOKEN_FILE) else ".", exist_ok=True)
            with open(TOKEN_FILE, "w") as token:
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
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found at {video_path!r}")

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
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                thumb_media = MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
                youtube.thumbnails().set(videoId=video_id, media_body=thumb_media).execute()
            except Exception:
                pass  # Thumbnail upload failure should not fail the overall video publish

        return {"video_id": video_id, "video_url": video_url}
