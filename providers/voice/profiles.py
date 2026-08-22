"""Persistent, named voice profiles - upload/clone-source and filter once,
reuse across every future run instead of re-uploading every time.

A profile's filtered.wav (when a filter has been applied) becomes the
actual reference sample handed to the voice provider for cloning - the
filter is baked into the profile's voice once, not reapplied per run.
"""

import json
import os
import shutil
import uuid
from datetime import datetime, timezone

from providers._ffmpeg_setup import ensure_ffmpeg_on_path
from providers.voice.filters import apply_filter

PROFILES_DIR = "runs/voice_profiles"
PROFILES_FILE = os.path.join(PROFILES_DIR, "profiles.json")


def _normalize_sample(source_path: str, dest_path: str) -> None:
    """Transcodes a clone reference to 24kHz mono 16-bit wav.

    Samples arrive in whatever the caller had - Telegram voice notes are
    opus in an .ogg container, browser uploads are often webm - and XTTS
    wants plain wav. Normalizing once here means every consumer (the
    cloner, the filter chain) reads the same format regardless of source.
    """
    ensure_ffmpeg_on_path()
    from pydub import AudioSegment

    audio = AudioSegment.from_file(source_path)
    audio.set_frame_rate(24000).set_channels(1).set_sample_width(2).export(
        dest_path, format="wav"
    )


def _load() -> dict:
    if not os.path.exists(PROFILES_FILE):
        return {}
    with open(PROFILES_FILE) as f:
        return json.load(f)


def _save(profiles: dict) -> None:
    os.makedirs(PROFILES_DIR, exist_ok=True)
    with open(PROFILES_FILE, "w") as f:
        json.dump(profiles, f, indent=2)


def list_profiles() -> dict:
    return _load()


def create_profile(name: str, source_path: str) -> dict:
    profile_id = str(uuid.uuid4())
    profile_dir = os.path.join(PROFILES_DIR, profile_id)
    os.makedirs(profile_dir, exist_ok=True)

    original_path = os.path.join(profile_dir, "original.wav")
    _normalize_sample(source_path, original_path)

    profiles = _load()
    profiles[profile_id] = {
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "original_path": original_path,
        "filtered_path": None,
        "filter_preset": None,
    }
    _save(profiles)
    return {"profile_id": profile_id, **profiles[profile_id]}


def apply_filter_to_profile(profile_id: str, preset: str) -> dict:
    profiles = _load()
    if profile_id not in profiles:
        raise KeyError(f"No such voice profile: {profile_id}")

    profile = profiles[profile_id]
    filtered_path = apply_filter(profile["original_path"], preset)

    # Move the filter's scratch output into the profile's own directory so
    # the profile is fully self-contained on disk.
    canonical_path = os.path.join(PROFILES_DIR, profile_id, "filtered.wav")
    shutil.move(filtered_path, canonical_path)

    profile["filtered_path"] = canonical_path
    profile["filter_preset"] = preset
    _save(profiles)
    return {"profile_id": profile_id, **profile}


def delete_profile(profile_id: str) -> None:
    profiles = _load()
    if profile_id in profiles:
        shutil.rmtree(os.path.join(PROFILES_DIR, profile_id), ignore_errors=True)
        del profiles[profile_id]
        _save(profiles)


def resolve_voice_path(profile_id: str) -> str:
    profiles = _load()
    if profile_id not in profiles:
        raise KeyError(f"No such voice profile: {profile_id}")
    profile = profiles[profile_id]
    return profile["filtered_path"] or profile["original_path"]
