import requests

from agents._llm_utils import call_llm_json
from providers.registry import get_provider

SYSTEM = (
    "You are a veteran researcher who prepares accurate, well-sourced "
    "briefings for YouTube scriptwriters. You use the provided verified source "
    "materials to synthesize key facts and accurate URLs. You are careful to "
    "flag anything you are not confident about rather than stating it as fact."
)

USER_AGENT = "SantaStudio/1.0 (contact@santastudio.dev)"


def _fetch_grounding_sources(topic: str) -> list[dict]:
    """Retrieves real encyclopedic sources and summaries for grounding."""
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": topic,
        "srlimit": 3,
        "format": "json",
    }
    headers = {"User-Agent": USER_AGENT}
    sources = []
    try:
        r = requests.get(url, params=params, headers=headers, timeout=8)
        r.raise_for_status()
        data = r.json()
        for item in data.get("query", {}).get("search", []):
            title = item.get("title")
            if not title:
                continue
            clean_title = title.replace(" ", "_")
            page_url = f"https://en.wikipedia.org/wiki/{clean_title}"

            # Fetch concise lead summary
            sum_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{clean_title}"
            try:
                sr = requests.get(sum_url, headers=headers, timeout=5)
                extract = sr.json().get("extract", "") if sr.status_code == 200 else ""
            except Exception:
                extract = ""

            snippet = item.get("snippet", "").replace('<span class="searchmatch">', "").replace("</span>", "")
            sources.append({
                "title": title,
                "url": page_url,
                "summary": (extract or snippet)[:600],
            })
    except Exception:
        pass
    return sources


def run(input_data: dict, config: dict) -> dict:
    """Input: {topic: str, reference_notes: dict}
    Output: {research_summary: str, sources: list[dict]}
    Each source: {title, url, key_facts: list[str]}
    """
    topic = input_data.get("topic", "the topic")
    grounded = _fetch_grounding_sources(topic)

    grounding_text = ""
    if grounded:
        grounding_text = "\nVerified source context:\n" + "\n".join(
            f"- Title: {s['title']}\n  URL: {s['url']}\n  Details: {s['summary']}"
            for s in grounded
        ) + "\nUse these real URLs and information for your sources list.\n"

    prompt = (
        f"Research the topic: {topic!r} for a YouTube video.\n"
        f"{grounding_text}"
        "Produce a research_summary (2-4 sentences) and a list of 2-4 sources, "
        "each with a title, a verified url, and 1-3 key_facts. If you are not "
        "confident in a specific fact, phrase it cautiously rather than as certain.\n"
        'Respond with ONLY a JSON object: {"research_summary": "...", '
        '"sources": [{"title": "...", "url": "...", "key_facts": ["...", "..."]}]}'
    )

    try:
        provider = get_provider("llm", config)
        parsed = call_llm_json(provider, prompt, SYSTEM)
        if not parsed.get("research_summary") or not parsed.get("sources"):
            raise ValueError(f"Missing 'research_summary' or 'sources' in LLM response: {parsed}")
        return {"success": True, "output": parsed, "error": None}
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}

