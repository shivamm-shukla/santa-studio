from concurrent.futures import ThreadPoolExecutor
import requests

import runlog
from agents._llm_utils import call_llm_json
from providers.registry import get_provider
from providers.research import grounding

SYSTEM = (
    "You are an elite investigative research director leading a specialist research "
    "swarm for high-retention documentary YouTube videos. You prioritize depth, "
    "concrete numbers, causal chains, chronology, and disputed perspectives rather "
    "than superficial summaries."
)

USER_AGENT = "SantaStudio/1.0 (contact@santastudio.dev)"

# Words that carry no meaning for a search index but do drown one. A topic is
# a video title or a human's question - "Why the Kolar Gold Fields shut down"
# - and handing that to Wikipedia's search verbatim returned Novak Djokovic,
# Austin, Texas and Animal testing, because the question words matched far
# more pages than the subject did. Every run before this grounded its
# research on whatever those searches happened to return.
_STOPWORDS = frozenset("""
a an the this that these those and or but if then than so as of in on at to
from by for with about into over after before between during is are was were
be been being do does did done has have had can could should would will
shall may might must why how what when where who whom whose which
story history explained explain really actually truth behind rise fall
""".split())


def _search_queries(topic: str) -> list[str]:
    """Search strings to try for a topic, most specific first.

    A run of capitalised words is almost always the subject itself, and it is
    what an encyclopedia indexes under. Falling back to the topic stripped of
    question words covers a lowercase topic, and the raw topic covers the
    rest.
    """
    words = topic.split()

    proper, best = [], []
    for word in words:
        stripped = word.strip(".,:;!?\"'()")
        # Skip a leading capital that is only there because it starts the
        # sentence - "Why" is not part of the subject.
        if stripped[:1].isupper() and stripped.lower() not in _STOPWORDS:
            proper.append(stripped)
        else:
            if len(proper) > len(best):
                best = proper
            proper = []
    if len(proper) > len(best):
        best = proper

    queries = []
    if len(best) >= 2:
        queries.append(" ".join(best))

    keywords = [w for w in words if w.strip(".,:;!?\"'()").lower() not in _STOPWORDS]
    if keywords and len(keywords) != len(words):
        queries.append(" ".join(keywords))

    queries.append(topic)

    seen, ordered = set(), []
    for query in queries:
        key = query.lower().strip()
        if key and key not in seen:
            seen.add(key)
            ordered.append(query)
    return ordered


def _relevant_to(sources: list[dict], topic: str) -> list[dict]:
    """The sources actually about the topic, dropping the rest.

    Wikipedia's search never fails - it returns its best guesses however bad
    they are - so an irrelevant answer arrives looking exactly like a good
    one, and a title that shares nothing with the topic is noise the brief
    will otherwise be written from. Filtering rather than accepting or
    rejecting the whole set matters because a search often returns one good
    page and four unrelated ones.
    """
    terms = {w.strip(".,:;!?\"'()").lower() for w in topic.split()}
    terms = {t for t in terms if len(t) > 2 and t not in _STOPWORDS}
    if not terms:
        return sources

    kept = []
    for source in sources:
        title_words = {w.strip(".,:;!?\"'()").lower() for w in source["title"].split()}
        if terms & title_words:
            kept.append(source)
    return kept


def _fetch_wikipedia_sources(topic: str) -> list[dict]:
    """Real encyclopedic sources for a topic, or nothing.

    Tries progressively looser search strings and keeps the first set that
    has anything genuinely about the topic in it. Returning nothing is a
    valid answer: the brief is written without grounding rather than from
    the wrong subject.
    """
    for query in _search_queries(topic):
        kept = _relevant_to(_search_wikipedia(query), topic)
        if kept:
            return kept
    return []


def _search_wikipedia(topic: str) -> list[dict]:
    """One search against Wikipedia, with full extracts and URLs."""
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


def _cite(grounded: list[dict], drafted) -> list[dict]:
    """The fetched sources, carrying whatever facts the model attached to them.

    Matching is by URL, because that is the part that has to be true. A drafted
    source whose URL we never fetched is dropped: it is either a hallucination
    or an unverifiable claim, and neither belongs in a description that
    promises a viewer they can check the work.
    """
    facts_by_url: dict[str, list[str]] = {}
    for source in drafted or []:
        if not isinstance(source, dict):
            continue
        url = str(source.get("url") or "").strip().rstrip("/")
        if not url:
            continue
        facts = [str(f).strip() for f in source.get("key_facts") or [] if str(f).strip()]
        if facts:
            facts_by_url.setdefault(url, []).extend(facts)

    cited = []
    for source in grounded:
        url = source["url"]
        facts = facts_by_url.get(url.rstrip("/")) or []
        if not facts and source.get("summary"):
            facts = [source["summary"][:200]]
        cited.append({"title": source["title"], "url": url, "key_facts": facts})
    return cited


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
    runlog.report(f"Grounding {topic!r} against real sources", progress=0.05)

    # Three indexes, none of which needs a key: the encyclopedia for the shape
    # of the subject, the academic record for whether anyone measured it, and
    # the news record for who argued about it. A subject this channel takes on
    # is rarely settled, and Wikipedia alone will not show you that.
    grounded = grounding.merge(
        _fetch_wikipedia_sources(topic),
        grounding.academic(topic),
        grounding.news(topic),
    )
    for source in grounded:
        runlog.report(f"Source: {source['title']} - {source['url']}")
    runlog.report(f"{len(grounded)} source(s) grounded", progress=0.2)

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
        runlog.report(f"Dispatching {len(prompts)} specialists in parallel", progress=0.25)
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                role: pool.submit(_run_specialist_research, role, p, provider)
                for role, p in prompts.items()
            }
            # Reported from this thread rather than inside the workers: a
            # ThreadPoolExecutor does not carry the bound run across, so a
            # line emitted in a worker would have nowhere to go.
            for i, (role, fut) in enumerate(futures.items(), start=1):
                specialist_results[role] = fut.result()
                runlog.report(
                    f"{role.replace('_', ' ')} specialist reported back",
                    progress=0.25 + 0.45 * (i / len(futures)),
                )

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

        runlog.report("Synthesising the brief from all three tracks", progress=0.75)
        synthesized = call_llm_json(provider, synthesis_prompt, SYSTEM)

        output = {
            "research_summary": synthesized.get("research_summary", ""),
            "chronology": specialist_results.get("chronology", {}).get("timeline", []),
            "numbers_and_data": specialist_results.get("numbers", {}).get("metrics", []),
            "disputed_claims": specialist_results.get("counter_narrative", {}).get("disputes", []),
            # The sources that ship are the ones we fetched, never the ones
            # the model wrote. A synthesised URL looks exactly like a real one
            # and ends up in the published description as a citation a viewer
            # cannot check - which is worse than offering no citation at all.
            # The model's contribution is the facts, matched onto real URLs.
            "sources": _cite(grounded, synthesized.get("sources")),
        }

        if not output["research_summary"]:
            raise ValueError(f"Empty research summary generated for topic {topic!r}")

        runlog.report(
            f"Brief done: {len(output['chronology'])} dated events, "
            f"{len(output['numbers_and_data'])} figures, "
            f"{len(output['disputed_claims'])} disputed, "
            f"{len(output['sources'])} sources",
            progress=1.0,
        )
        return {"success": True, "output": output, "error": None}
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}

