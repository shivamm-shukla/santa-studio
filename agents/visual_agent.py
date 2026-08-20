from providers.registry import get_provider


def run(input_data: dict, config: dict) -> dict:
    """Input: {scenes: list[dict]}
    Output: {scene_assets: list[dict]}
    Each: {scene_index, asset_type, asset_path}

    Tries the primary visual provider first (Pexels); falls back to Pixabay
    if no result was found for a given scene's query.
    """
    scenes = input_data.get("scenes", [])
    primary = get_provider("visual", config)
    fallback_config = dict(config, ACTIVE_PROVIDERS={**config["ACTIVE_PROVIDERS"], "visual": "pixabay"})
    fallback = get_provider("visual", fallback_config)

    scene_assets = []
    for i, scene in enumerate(scenes):
        query = scene.get("visual_hint", "generic footage")
        result = primary.search(query)
        if not result.get("asset_path"):
            result = fallback.search(query)
        scene_assets.append(
            {
                "scene_index": i,
                "asset_type": result["asset_type"],
                "asset_path": result["asset_path"],
            }
        )

    return {"success": True, "output": {"scene_assets": scene_assets}, "error": None}
