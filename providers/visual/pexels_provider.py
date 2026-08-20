from providers.base import VisualProvider


class PexelsProvider(VisualProvider):
    """Pexels API - free, commercially usable stock video/photo search."""

    def search(self, query: str, asset_type: str = "video") -> dict:
        # TODO: wire real Pexels API search call here
        return {
            "asset_type": asset_type,
            "asset_path": f"runs/stub_pexels_{asset_type}_{abs(hash(query)) % 10000}.mp4",
        }
