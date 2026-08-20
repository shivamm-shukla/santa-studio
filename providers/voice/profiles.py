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

from providers.voice.filters import apply_filter

PROFILES_DIR = "runs/voice_profiles"
PROFILES_FILE = os.path.join(PROFILES_DIR, "profiles.json")


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

    ext = os.path.splitext(source_path)[1] or ".wav"
    original_path = os.path.join(profile_dir, f"original{ext}")
    shutil.copy(source_path, original_path)

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
