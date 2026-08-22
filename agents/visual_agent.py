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

        def fetch_scene_assets(indexed_scene):
            i, scene = indexed_scene
            hint = scene.get("visual_hint", "generic footage")
            queries = [q.strip() for q in hint.split(",") if q.strip()]
            if not queries:
                queries = ["generic footage"]

            text_words = len((scene.get("text") or "").split())
            if len(queries) == 1 and text_words >= 15:
                queries.append(f"{queries[0]} detail")

            scene_results = []
            seen_paths = set()
            for q in queries[:3]:
                result = None
                for provider in (primary, pixabay_fallback, wikimedia_fallback):
                    try:
                        res = provider.search(q)
                        if res and res.get("asset_path") and res["asset_path"] not in seen_paths:
                            result = res
                            seen_paths.add(res["asset_path"])
                            break
                    except Exception:
                        continue
                if result:
                    scene_results.append({
                        "scene_index": i,
                        "asset_type": result.get("asset_type") or "video",
                        "asset_path": result.get("asset_path") or "",
                    })

            if not scene_results:
                return [{
                    "scene_index": i,
                    "asset_type": "video",
                    "asset_path": "",
                }]
            return scene_results

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SCENES) as pool:
            nested_assets = list(pool.map(fetch_scene_assets, enumerate(scenes)))
            scene_assets = [asset for sublist in nested_assets for asset in sublist]

        return {"success": True, "output": {"scene_assets": scene_assets}, "error": None}
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}
