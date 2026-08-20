from providers.base import VisualProvider


class PixabayProvider(VisualProvider):
    """Pixabay API - free fallback when Pexels has no result for a query."""

    def search(self, query: str, asset_type: str = "video") -> dict:
        # TODO: wire real Pixabay API search call here
        return {
            "asset_type": asset_type,
            "asset_path": f"runs/stub_pixabay_{asset_type}_{abs(hash(query)) % 10000}.mp4",
        }
