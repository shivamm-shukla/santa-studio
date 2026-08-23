import os
import runlog
from providers.registry import get_provider


def run(input_data: dict, config: dict) -> dict:
    """Input: {video_path: str, title: str, description: str, tags: list[str],
               thumbnail_path: str, privacy_status: str, run_id: str}
    Output: {published: bool, video_id: str, video_url: str,
             thumbnail_status: str, platform: str}
    """
    try:
        video_path = input_data.get("video_path")
        metadata = input_data.get("metadata") or {}

        title = input_data.get("title") or metadata.get("title") or "Santa Studio Video"
        description = input_data.get("description") or metadata.get("description") or ""
        tags = input_data.get("tags") or metadata.get("tags") or []
        thumbnail_path = input_data.get("thumbnail_path") or (input_data.get("thumbnail_output") or {}).get("thumbnail_path", "")
        privacy_status = input_data.get("privacy_status") or "private"

        provider = get_provider("publish", config)
        runlog.report(f"Uploading {os.path.basename(video_path or '')} as {privacy_status}", progress=0.3)
        runlog.report(f"Title: {title}", progress=0.35)

        upload_res = provider.upload(
            video_path=video_path or "",
            title=title,
            description=description,
            tags=tags,
            thumbnail_path=thumbnail_path,
            privacy_status=privacy_status,
        )

        thumb_status = "uploaded" if upload_res.get("thumbnail_uploaded") else "skipped"
        runlog.report(
            f"Live at {upload_res.get('video_url', '(no url)')}"
            + (" [dry run]" if upload_res.get("dry_run") else ""),
            progress=1.0,
        )

        return {
            "success": True,
            "output": {
                "published": True,
                "video_id": upload_res.get("video_id", ""),
                "video_url": upload_res.get("video_url", ""),
                "thumbnail_status": thumb_status,
                "platform": "youtube",
                "dry_run": upload_res.get("dry_run", False),
            },
            "error": None,
        }
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}

