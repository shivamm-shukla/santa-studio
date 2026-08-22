from concurrent.futures import ThreadPoolExecutor

from providers.registry import get_provider

# Scene lookups are independent network round-trips, so they overlap
# rather than queue. Capped because the stock APIs rate-limit.
MAX_PARALLEL_SCENES = 6


def run(input_data: dict, config: dict) -> dict:
    """Input: {scenes: list[dict]}
    Output: {scene_assets: list[dict]}
    Each: {scene_index, asset_type, asset_path}

    Tries the primary visual provider first (Pexels); falls back to Pixabay
    if no result was found for a given scene's query.
    """
    try:
        scenes = input_data.get("scenes", [])
        if not scenes:
            return {
                "success": True,
                "output": {"scene_assets": [{"scene_index": 0, "asset_type": "video", "asset_path": ""}]},
                "error": None,
            }

        primary = get_provider("visual", config)
        pixabay_cfg = dict(config, ACTIVE_PROVIDERS={**config["ACTIVE_PROVIDERS"], "visual": "pixabay"})
        pixabay_fallback = get_provider("visual", pixabay_cfg)
        wikimedia_cfg = dict(config, ACTIVE_PROVIDERS={**config["ACTIVE_PROVIDERS"], "visual": "wikimedia"})
        wikimedia_fallback = get_provider("visual", wikimedia_cfg)

        def fetch(indexed_scene):
            i, scene = indexed_scene
            query = scene.get("visual_hint", "generic footage")
            result = None
            for provider in (primary, pixabay_fallback, wikimedia_fallback):
                try:
                    res = provider.search(query)
                    if res and res.get("asset_path"):
                        result = res
                        break
                except Exception:
                    continue

            return {
                "scene_index": i,
                "asset_type": (result or {}).get("asset_type") or "video",
                "asset_path": (result or {}).get("asset_path") or "",
            }

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SCENES) as pool:
            # map() preserves input order, so scenes stay in script order.
            scene_assets = list(pool.map(fetch, enumerate(scenes)))

        return {"success": True, "output": {"scene_assets": scene_assets}, "error": None}
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}
