import os
from concurrent.futures import ThreadPoolExecutor

import runlog
from providers.registry import get_provider

# Scene lookups are independent network round-trips, so they overlap
# rather than queue. Capped because the stock APIs rate-limit.
MAX_PARALLEL_SCENES = 6


def run(input_data: dict, config: dict) -> dict:
    """Input: {scenes: list[dict]}
    Output: {scene_assets: list[dict]}
    Each: {scene_index, asset_type, asset_path}

    Tries the primary visual provider first (Pexels), then Pixabay, then
    Wikimedia. A scene none of them can serve is generated rather than left
    blank - a real photograph is always preferred, which is why generation is
    last and not first.
    """
    try:
        scenes = input_data.get("scenes", [])
        runlog.report(f"Sourcing footage for {len(scenes)} scene(s)", progress=0.1)
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
        # Only reached when three stock libraries have all come back empty,
        # which is the case it is for: shots no library carries.
        generated_cfg = dict(config, ACTIVE_PROVIDERS={**config["ACTIVE_PROVIDERS"], "visual": "generated"})
        generated_fallback = get_provider("visual", generated_cfg)

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
            for shot, q in enumerate(queries[:3]):
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

                if not result:
                    # Which shot this is decides how it gets photographed. Two
                    # scenes asking for the same subject should not come back
                    # as the same frame twice, and a video whose generated
                    # stills all share one light and one framing announces
                    # what made it however good any single frame is.
                    try:
                        res = generated_fallback.search(q, variation=i * len(queries[:3]) + shot)
                        if res and res.get("asset_path") and res["asset_path"] not in seen_paths:
                            result = res
                            seen_paths.add(res["asset_path"])
                    except Exception:
                        pass

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

        # Reported as each scene lands rather than inside the workers: the
        # bound run does not cross a ThreadPoolExecutor boundary.
        scene_assets = []
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SCENES) as pool:
            for done, assets in enumerate(pool.map(fetch_scene_assets, enumerate(scenes)), start=1):
                for asset in assets:
                    if asset.get("asset_path"):
                        runlog.report(
                            f"Scene {asset['scene_index']}: {os.path.basename(asset['asset_path'])}"
                        )
                scene_assets.extend(assets)
                runlog.report(f"{done}/{len(scenes)} scenes covered", progress=done / len(scenes))

        found = sum(1 for a in scene_assets if a.get("asset_path"))
        runlog.report(f"{found} clip(s) fetched for {len(scenes)} scene(s)", progress=1.0)
        return {"success": True, "output": {"scene_assets": scene_assets}, "error": None}
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}
