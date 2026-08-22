from concurrent.futures import ThreadPoolExecutor
import requests

from agents._llm_utils import call_llm_json
from providers.registry import get_provider

SYSTEM = (
    "You are an elite investigative research director leading a specialist research "
    "swarm for high-retention documentary YouTube videos. You prioritize depth, "
    "concrete numbers, causal chains, chronology, and disputed perspectives rather "
    "than superficial summaries."
)

USER_AGENT = "SantaStudio/1.0 (contact@santastudio.dev)"


def _fetch_wikipedia_sources(topic: str) -> list[dict]:
    """Retrieves real encyclopedic sources, full extracts, and URLs."""
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": topic,
        "srlimit": 5,
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
                "summary": extract or snippet,
            })
    except Exception:
        pass
    return sources


def _run_specialist_research(role: str, prompt: str, provider) -> dict:
    """Executes a single specialist research track."""
    sys_prompt = f"You are a specialist researcher focusing exclusively on: {role}."
    try:
        return call_llm_json(provider, prompt, sys_prompt)
    except Exception:
        return {}


def run(input_data: dict, config: dict) -> dict:
    """Input: {topic: str, reference_notes: dict}
    Output: {research_summary: str, chronology: list[dict], numbers_and_data: list[dict],
             disputed_claims: list[dict], sources: list[dict]}
    """
    topic = input_data.get("topic", "the topic")
    grounded = _fetch_wikipedia_sources(topic)

    grounding_text = ""
    if grounded:
        grounding_text = "\nVerified real-world source grounding:\n" + "\n".join(
            f"- {s['title']} ({s['url']}): {s['summary'][:400]}"
            for s in grounded
        ) + "\n"

    try:
        provider = get_provider("llm", config)

        # 4 Parallel Specialist Researchers
        prompts = {
            "chronology": (
                f"Topic: {topic!r}\n{grounding_text}\n"
                "Extract the precise chronological timeline of key events and causal milestones.\n"
                'Respond with JSON: {"timeline": [{"date": "...", "event": "...", "significance": "..."}]}'
            ),
            "numbers": (
                f"Topic: {topic!r}\n{grounding_text}\n"
                "Extract concrete numbers, measurements, financial figures, percentages, and metrics.\n"
                'Respond with JSON: {"metrics": [{"metric": "...", "value": "...", "context": "..."}]}'
            ),
            "counter_narrative": (
                f"Topic: {topic!r}\n{grounding_text}\n"
                "Identify controversies, competing explanations, criticisms, and alternative viewpoints.\n"
                'Respond with JSON: {"disputes": [{"claim": "...", "viewpoint_a": "...", "viewpoint_b": "..."}]}'
            ),
        }

        specialist_results = {}
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                role: pool.submit(_run_specialist_research, role, p, provider)
                for role, p in prompts.items()
            }
            for role, fut in futures.items():
                specialist_results[role] = fut.result()

        # Synthesis pass
        synthesis_prompt = (
            f"Topic: {topic!r}\n{grounding_text}\n"
            f"Chronology findings: {specialist_results.get('chronology')}\n"
            f"Metrics findings: {specialist_results.get('numbers')}\n"
            f"Controversies/Disputes: {specialist_results.get('counter_narrative')}\n"
            "Synthesize an authoritative research brief. Produce a rich research_summary (4-8 sentences), "
            "and a list of 3-5 real sources with URLs and key facts.\n"
            'Respond with JSON: {"research_summary": "...", "sources": [{"title": "...", "url": "...", "key_facts": ["..."]}]}'
        )

        synthesized = call_llm_json(provider, synthesis_prompt, SYSTEM)

        output = {
            "research_summary": synthesized.get("research_summary", ""),
            "chronology": specialist_results.get("chronology", {}).get("timeline", []),
            "numbers_and_data": specialist_results.get("numbers", {}).get("metrics", []),
            "disputed_claims": specialist_results.get("counter_narrative", {}).get("disputes", []),
            "sources": synthesized.get("sources") or [
                {"title": s["title"], "url": s["url"], "key_facts": [s["summary"][:120]]}
                for s in grounded[:3]
            ],
        }

        if not output["research_summary"]:
            raise ValueError(f"Empty research summary generated for topic {topic!r}")

        return {"success": True, "output": output, "error": None}
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}

