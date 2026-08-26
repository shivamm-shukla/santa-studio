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
    """Where the OAuth token lives.

    config/credentials/, which exists for exactly this: `export` excludes it
    by construction and `clean` will not touch it. It was being written to
    cache/ - the directory documented as safe to delete - so reclaiming disk
    silently signed the user out of YouTube.
    """
    env_token = os.getenv("YOUTUBE_TOKEN_FILE")
    if env_token:
        return env_token
    return str(paths.credentials_dir() / "youtube_token.json")


def _migrate_legacy_token(token_path: str) -> None:
    """Moves a token written by an older build into config/credentials/."""
    legacy = paths.home() / "cache" / "youtube_token.json"
    if legacy.exists() and not os.path.exists(token_path):
        os.makedirs(os.path.dirname(token_path), exist_ok=True)
        try:
            legacy.replace(token_path)
        except OSError:
            pass


def auth_status() -> dict:
    """Whether YouTube is connected, without starting an OAuth flow.

    An upload must never be the thing that discovers there are no
    credentials: `run_local_server` blocks the caller and opens a browser on
    whatever machine the server is running on, which is fine for a local app
    driven deliberately and wrong in the middle of a pipeline. So connecting
    is its own action, and this is how a UI knows whether it is needed.
    """
    token_path = _token_file()
    _migrate_legacy_token(token_path)

    status = {
        "connected": False,
        "token_path": token_path,
        "client_secret_present": os.path.exists(CREDENTIALS_FILE),
        "client_secret_path": CREDENTIALS_FILE,
        "detail": "",
    }

    try:
        from google.oauth2.credentials import Credentials
    except ImportError:
        status["detail"] = (
            "google-api-python-client and google-auth-oauthlib are not installed. "
            "Run: pip install google-api-python-client google-auth-oauthlib"
        )
        return status

    if not os.path.exists(token_path):
        status["detail"] = (
            "Not connected yet."
            if status["client_secret_present"]
            else f"No OAuth client secret at {CREDENTIALS_FILE!r}. Download an "
            "OAuth 2.0 Client ID (Desktop app) from the Google Cloud Console."
        )
        return status

    try:
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    except Exception as e:
        status["detail"] = f"Stored token could not be read ({e}). Connect again."
        return status

    # An expired token with a refresh token is still a connected account -
    # the next upload refreshes it. Only a token that cannot be refreshed
    # means the user has to do something.
    status["connected"] = bool(creds and (creds.valid or creds.refresh_token))
    status["expired"] = bool(getattr(creds, "expired", False))
    status["detail"] = "Connected." if status["connected"] else "Stored token is unusable. Connect again."
    return status


def connect(open_browser: bool = True) -> dict:
    """Runs the OAuth flow and stores the token. Blocks until it completes.

    Call this from a thread of its own, never from a request handler that
    something is waiting on.
    """
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as e:
        raise RuntimeError(
            "YouTube publishing requires google-api-python-client and "
            "google-auth-oauthlib. Run: pip install google-api-python-client "
            "google-auth-oauthlib"
        ) from e

    if not os.path.exists(CREDENTIALS_FILE):
        raise RuntimeError(
            f"YouTube OAuth credentials file not found at {CREDENTIALS_FILE!r}. "
            "Download OAuth 2.0 Client ID JSON from Google Cloud Console "
            "and save as client_secret.json or set YOUTUBE_CREDENTIALS_FILE in .env."
        )

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0, open_browser=open_browser)

    token_path = _token_file()
    os.makedirs(os.path.dirname(token_path), exist_ok=True)
    with open(token_path, "w") as token:
        token.write(creds.to_json())
    return auth_status()


def disconnect() -> dict:
    """Forgets the stored token. The Google-side grant is untouched."""
    token_path = _token_file()
    try:
        os.remove(token_path)
    except OSError:
        pass
    return auth_status()


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
            from googleapiclient.discovery import build
        except ImportError as e:
            raise RuntimeError(
                "YouTube publishing requires google-api-python-client and google-auth-oauthlib. "
                "Run: pip install google-api-python-client google-auth-oauthlib"
            ) from e

        token_path = _token_file()
        _migrate_legacy_token(token_path)
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
                # Deliberately not starting the browser flow here. An upload
                # runs inside a pipeline, often on a background thread and
                # sometimes on a machine nobody is sitting at;
                # `run_local_server` would block it and open a browser on the
                # server. Connecting is an explicit action - `connect()`,
                # `studio youtube connect`, or the button in the web UI.
                raise RuntimeError(
                    "YouTube is not connected. Run `studio youtube connect` "
                    "(or use Connect YouTube in the web UI) once, then publish. "
                    + (
                        ""
                        if os.path.exists(CREDENTIALS_FILE)
                        else f"An OAuth client secret is also needed at {CREDENTIALS_FILE!r}: "
                        "download an OAuth 2.0 Client ID (Desktop app) from the "
                        "Google Cloud Console."
                    )
                )

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
        publish_at: str = "",
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
                # YouTube only honours publishAt on a video that is private
                # until then, so scheduling one public is a contradiction it
                # answers by ignoring the schedule. Better to be private and
                # go out on time than public now and surprise someone.
                "privacyStatus": "private" if publish_at else privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }
        if publish_at:
            body["status"]["publishAt"] = publish_at

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
