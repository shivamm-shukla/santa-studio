from concurrent.futures import ThreadPoolExecutor
import hashlib

import requests

import checkpoints
import runlog
from agents._llm_utils import call_llm_json
from providers.registry import get_provider
from providers.research import grounding, websearch

SYSTEM = (
    "You are an elite investigative research director leading a specialist research "
    "swarm for high-retention documentary YouTube videos. You prioritize depth, "
    "concrete numbers, causal chains, chronology, and disputed perspectives rather "
    "than superficial summaries."
)

PLAN_SYSTEM = (
    "You are a documentary researcher who finds things other people miss. "
    "You search the way an investigator does: for the primary document, the "
    "figure, the name, the criticism - not for the topic restated."
)

SCREEN_SYSTEM = (
    "You decide whether a source is about a subject. You are strict: a source "
    "that merely shares a word with the topic is not about it."
)

USER_AGENT = "SantaStudio/1.0 (contact@santastudio.dev)"

# How hard the agent is allowed to look. These bound effort, not findings:
# there is no cap on how many sources a run may end up citing, only on how
# many times it rethinks its queries and how many pages it opens in full.
SEARCH_ROUNDS = 3
QUERIES_PER_ROUND = 5
ENOUGH_SOURCES = 8         # stop early once the subject is this well covered
CANDIDATES_PER_ROUND = 60  # what one screening call is asked to judge
PAGES_READ = 10            # pages fetched and read rather than skimmed
EXCERPT = 2500             # characters kept from each of them
GROUNDING_BUDGET = 24000   # total source text handed to the swarm

# The length those numbers were chosen for. Everything above scales from
# here against what the run was actually asked for.
BASELINE_MINUTES = 5

# What a minute of finished video costs in material. A twenty-minute video
# is not a five-minute video said slowly; it is four times the events, the
# figures and the disagreements, and it needs the sources to carry them.
# Sub-linear because sources overlap - the tenth page on a subject repeats
# more of the ninth than the second repeated the first.
DEPTH_EXPONENT = 0.6

# Facts drawn out of each source. This was the real ceiling on how long a
# video could honestly be: the synthesis asked for "3-5 sources with key
# facts", so however many pages had been fetched and read, only a handful
# ever carried a claim into fact-checking - and the script is allowed to
# state nothing that did not come through there.
FACTS_PER_SOURCE = 4


def depth_for(target_minutes: int) -> dict:
    """How hard to look, for a video of this length.

    Research had no idea how long a video it was researching. Every run
    looked equally hard, which is too hard for a three-minute explainer and
    nowhere near hard enough for a twenty-minute one - and a script cannot
    be long about material that was never gathered.
    """
    scale = max(1.0, (max(1, int(target_minutes)) / BASELINE_MINUTES) ** DEPTH_EXPONENT)

    return {
        "sources": min(24, round(ENOUGH_SOURCES * scale)),
        "pages": min(28, round(PAGES_READ * scale)),
        "rounds": min(5, round(SEARCH_ROUNDS * scale ** 0.5)),
        "facts_per_source": min(8, round(FACTS_PER_SOURCE * scale ** 0.5)),
        "summary_sentences": min(20, round(6 * scale)),
        # The text budget has to move with the page count or the extra
        # reading is wasted: a run that opens twenty-eight pages and then
        # hands the swarm the same 24000 characters has trimmed most of what
        # it just read down to a title, while the synthesis is being asked
        # for facts from every one of those URLs. Capped well inside the
        # smallest window a provider here offers.
        "grounding": min(64000, round(GROUNDING_BUDGET * scale)),
    }

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


def _query_plan(
    topic: str, provider, tried: list[str], kept: list[dict], attempt: int = 0
) -> list[str]:
    """Search queries the agent wrote for itself.

    The topic is a video title. Handing a video title to a search index is
    how "how a metal box rewired world trade" came back as four papers on
    photosynthesis: nothing in that sentence names its own subject. Asked
    the same question in its own words, the agent searches "containerization
    shipping trade" and the first three results are the standard works.

    Later rounds see what has already been tried and what it turned up, so
    the second pass goes somewhere the first did not rather than rephrasing
    it. Falls back to the derived queries, which are worse but never empty.
    """
    history = ""
    if tried:
        history = (
            f"\nAlready searched: {tried}\n"
            f"Already found: {[s['title'] for s in kept][:12] or 'nothing usable'}\n"
            "Write queries that go somewhere these did not - a different "
            "period, a named person or body, the primary document, the "
            "figures, the criticism, the other side of the argument.\n"
        )

    # A second pass exists because the first one's findings did not survive
    # fact-checking, so repeating its instincts wastes the requests it costs.
    if attempt:
        history += (
            "\nAn earlier pass on this topic found sources whose claims could "
            "not be verified. Go for material that states things plainly and "
            "attributably: primary documents, official reports, statistical "
            "releases, named studies, contemporary coverage with figures in "
            "it.\n"
        )

    prompt = (
        f"Researching for a documentary: {topic!r}\n{history}\n"
        f"Write {QUERIES_PER_ROUND} search queries. Name the subject the way "
        "a source about it would name it, not the way the title does. Keep "
        "each one short, in English, and worth typing into a search engine.\n"
        'Respond with ONLY a JSON object: {"queries": ["...", "..."]}'
    )
    try:
        planned = call_llm_json(provider, prompt, PLAN_SYSTEM).get("queries")
    except Exception:
        planned = None

    queries = [str(q).strip() for q in planned or [] if str(q).strip()]
    if not queries:
        runlog.report("Could not plan searches; falling back to the topic itself")
        return _search_queries(topic)
    return queries[:QUERIES_PER_ROUND]


def _sweep(queries: list[str]) -> list[dict]:
    """Every index this project can reach, asked every query, merged.

    The open web is in here alongside the catalogues because most of what a
    documentary is built on was never catalogued: the report, the archive
    page, the trade body's own numbers. The catalogues are what make a claim
    citable; the web is what makes it findable.
    """
    def one(query: str) -> list[dict]:
        return grounding.merge(
            _search_wikipedia(query),
            websearch.search(query),
            grounding.academic(query, limit=8),
            grounding.news(query, limit=8),
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        groups = list(pool.map(one, queries))

    # Interleaved rather than concatenated. Screening judges a bounded number
    # of candidates per round, and concatenating means that bound is spent on
    # whatever the first query returned - so a query that found the good
    # source fourth never gets looked at.
    ordered = []
    for rank in range(max((len(g) for g in groups), default=0)):
        for group in groups:
            if rank < len(group):
                ordered.append(group[rank])
    return grounding.merge(ordered)


def _read_in_full(sources: list[dict], pages: int = PAGES_READ) -> None:
    """Opens the best of the sources and attaches what they actually say.

    A title and a snippet is enough to decide whether a source is worth
    citing and nowhere near enough to write from. Without this the brief is
    assembled out of what a search engine chose to show, and the depth this
    channel is aiming at is not reachable from search snippets.
    """
    worth_reading = sources[:pages]
    if not worth_reading:
        return

    def fetch(source: dict) -> None:
        text = websearch.read(source["url"], limit=EXCERPT)
        if text:
            source["content"] = text

    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(fetch, worth_reading))

    read = sum(1 for s in worth_reading if s.get("content"))
    runlog.report(f"Read {read} of {len(worth_reading)} source(s) in full")


# What a provider says when the prompt is bigger than it will take. The free
# tiers differ wildly here - Groq allows 8000 tokens a minute, Gemini a
# million - and which one answers is decided by whose allowance is left.
_TOO_LARGE = (
    "413", "too large", "context length", "tokens per minute",
    "reduce your message", "maximum context",
)


def _too_large(error) -> bool:
    """Whether a call failed for size rather than for anything being wrong."""
    text = str(error or "").lower()
    return any(marker in text for marker in _TOO_LARGE)


def _grounding_text(sources: list[dict], budget: int = GROUNDING_BUDGET) -> str:
    """The sources as the swarm sees them, inside a budget.

    What was read in full leads, because it carries the argument; the rest
    still ships its title and URL, so a source the agent found stays visible
    to the specialists even when there was no room to quote it.
    """
    lines, used = [], 0
    for source in sources:
        body = source.get("content") or source.get("summary") or ""
        entry = f"- {source['title']} ({source['url']}):\n{body}"
        if used + len(entry) > budget:
            entry = f"- {source['title']} ({source['url']})"
            if used + len(entry) > budget:
                break
        lines.append(entry)
        used += len(entry)
    return "\nVerified real-world source grounding:\n" + "\n".join(lines) + "\n"


def _screened(sources: list[dict], topic: str, provider) -> list[dict]:
    """The grounded set narrowed to what is actually about the topic.

    Wikipedia's results are word-filtered before they arrive here. OpenAlex
    and GDELT are not, and neither of those fails a search either: asked for
    "how a metal box rewired world trade", OpenAlex answered with four papers
    on photosynthesis, plant stress and a tomato fungus, because each carries
    the word "rewiring". All four shipped in that run's sources.md under "the
    sources this video is built on".

    Word overlap cannot separate those out - "world" is a genuine match
    against a paper on a warming world - so this judgement is made rather
    than computed. It is one call on a list of titles, and it fails closed
    onto the word filter: accepting whatever came back is the behaviour that
    wrote that document.
    """
    if not sources:
        return []

    listing = "\n".join(
        f"{i}. {s['title']} - {str(s.get('summary') or '')[:160]}"
        for i, s in enumerate(sources, start=1)
    )
    key = f"research:screen:{hashlib.sha256((topic + listing).encode()).hexdigest()[:16]}"

    kept_numbers = checkpoints.load(key)
    if not isinstance(kept_numbers, list):
        prompt = (
            f"Topic of the video: {topic!r}\n\n"
            f"Candidate sources:\n{listing}\n\n"
            "These came back from keyword searches, so some of them are about "
            "an entirely different subject that happens to share a word with "
            "the topic. Give the numbers of the ones genuinely about this "
            "topic - keep one only if a viewer who clicked it would find it is "
            "about the video's subject. Keeping nothing is a valid answer; "
            "keeping a near-miss is not.\n"
            'Respond with ONLY a JSON object: {"keep": [1, 3]}'
        )
        try:
            kept_numbers = call_llm_json(provider, prompt, SCREEN_SYSTEM).get("keep")
        except Exception:
            kept_numbers = None
        if not isinstance(kept_numbers, list):
            runlog.report("Could not screen the sources; falling back to word matching")
            return _relevant_to(sources, topic)
        checkpoints.save(key, kept_numbers)

    keep = {int(n) for n in kept_numbers if str(n).strip().isdigit()}
    kept = []
    for index, source in enumerate(sources, start=1):
        if index in keep:
            kept.append(source)
        else:
            runlog.report(f"Not about the topic, dropped: {source['title']}")
    return kept


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
        # A paper's summary is its journal, its year and how often it has been
        # cited. That is a bibliographic detail, not something the paper
        # claims - and handed to the fact-checker as a claim it comes back
        # flagged as unverifiable, which is both true and beside the point.
        # Only a source whose summary actually says something about the
        # subject contributes one.
        if not facts and source.get("summary") and source.get("kind") not in ("academic", "news"):
            facts = [source["summary"][:200]]
        cited.append({
            "title": source["title"],
            "url": url,
            "key_facts": facts,
            "note": source.get("summary", "")[:120],
        })
    return cited


def _run_specialist_research(role: str, prompt: str, ask) -> dict:
    """Executes a single specialist research track.

    A specialist that has already reported in this run is not asked again. The
    manager re-runs a whole agent when its output fails validation, and the
    swarm's three calls are three of a free tier's twenty requests for the day;
    spending them twice to re-derive answers already on disk is how a run ends
    up parked for want of allowance it had already used.
    """
    key = f"research:{role}:{hashlib.sha256(prompt.encode()).hexdigest()[:16]}"
    done = checkpoints.load(key)
    if done is not None:
        runlog.report(f"{role.replace('_', ' ')} specialist already reported; reusing it")
        return done

    sys_prompt = f"You are a specialist researcher focusing exclusively on: {role}."
    try:
        result = ask(prompt, sys_prompt)
    except Exception:
        return {}

    # Only a real answer is worth keeping: an empty one would pin the failure
    # in place for every later attempt.
    if result:
        checkpoints.save(key, result)
    return result


def run(input_data: dict, config: dict) -> dict:
    """Input: {topic: str, attempt: int, target_length_minutes: int}
    Output: {research_summary: str, chronology: list[dict], numbers_and_data: list[dict],
             disputed_claims: list[dict], sources: list[dict]}
    """
    topic = input_data.get("topic", "the topic")
    attempt = int(input_data.get("attempt") or 0)
    depth = depth_for(input_data.get("target_length_minutes") or BASELINE_MINUTES)

    runlog.report(
        f"Researching {topic!r}" + (" again, wider" if attempt else "")
        + f" - looking for {depth['sources']} sources across {depth['rounds']} round(s)",
        progress=0.05,
    )

    # A pass that has to make up for a failed one gets more room to look.
    rounds = depth["rounds"] + attempt

    try:
        provider = get_provider("llm", config)

        # The agent searches, looks at what it got, and searches again. A
        # single pass over a fixed query is what put four papers on
        # photosynthesis into a video about shipping containers: every index
        # here answers a keyword search and none of them fails one, so a bad
        # query comes back looking exactly like a good one. Rounds are how a
        # thin first pass turns into a full one instead of into a dead run.
        grounded: list[dict] = []
        tried: list[str] = []
        seen_urls: set[str] = set()
        searched = 0

        for round_number in range(1, rounds + 1):
            queries = _query_plan(topic, provider, tried, grounded, attempt)
            tried.extend(queries)
            runlog.report(
                f"Round {round_number}: searching {', '.join(repr(q) for q in queries[:5])}",
                progress=0.05 + 0.05 * round_number,
            )

            found = [s for s in _sweep(queries) if s["url"] not in seen_urls]
            seen_urls.update(s["url"] for s in found)
            searched += len(found)

            kept = _screened(found[:CANDIDATES_PER_ROUND], topic, provider)
            grounded.extend(kept)
            runlog.report(
                f"Round {round_number}: {len(kept)} of {len(found)} result(s) are on the subject "
                f"({len(grounded)} so far)"
            )
            if len(grounded) >= depth["sources"]:
                break

        # Only reached when three rounds of the agent's own queries turned up
        # nothing about the subject at all. A brief written from here would
        # come out of the model's memory and then be cited to sources that do
        # not support it, which is the one failure this stage exists to
        # prevent - so it says so rather than inventing a way through.
        if not grounded:
            raise ValueError(
                f"Nothing found is about {topic!r} - {searched} result(s) across "
                f"{len(tried)} searches, none of them on the subject. Name the "
                "subject in the topic and run it again."
            )

        for source in grounded:
            runlog.report(f"Source: {source['title']} - {source['url']}")
        runlog.report(f"{len(grounded)} source(s) grounded", progress=0.2)

        # Read, not skimmed: the claims in the script come from what the page
        # says, not from what a search engine chose to show of it.
        _read_in_full(grounded, depth["pages"])

        # Which provider answers is decided by whose free allowance is left,
        # and their windows are nothing like each other - Groq takes 8000
        # tokens a minute, Gemini a million. A brief that took three rounds of
        # searching to assemble should not be lost because the provider that
        # picked up has less room than the one before it, so a prompt that
        # comes back too large is sent again carrying fewer sources.
        def ask(template: str, system: str, list_key: str | None = None) -> dict:
            full = depth["grounding"]
            budgets = (full, full // 3, full // 9)
            for budget in budgets:
                prompt = template.replace("<<GROUNDING>>", _grounding_text(grounded, budget))
                try:
                    if list_key:
                        return call_llm_json(provider, prompt, system, list_key=list_key)
                    return call_llm_json(provider, prompt, system)
                except Exception as error:
                    if not _too_large(error) or budget == budgets[-1]:
                        raise
                    runlog.report(
                        "The provider that answered has a smaller window than the "
                        "brief; trimming the sources and asking again"
                    )
            return {}

        # 4 Parallel Specialist Researchers
        prompts = {
            "chronology": (
                f"Topic: {topic!r}\n<<GROUNDING>>\n"
                "Extract the precise chronological timeline of key events and causal milestones.\n"
                'Respond with JSON: {"timeline": [{"date": "...", "event": "...", "significance": "..."}]}'
            ),
            "numbers": (
                f"Topic: {topic!r}\n<<GROUNDING>>\n"
                "Extract concrete numbers, measurements, financial figures, percentages, and metrics.\n"
                'Respond with JSON: {"metrics": [{"metric": "...", "value": "...", "context": "..."}]}'
            ),
            "counter_narrative": (
                f"Topic: {topic!r}\n<<GROUNDING>>\n"
                "Identify controversies, competing explanations, criticisms, and alternative viewpoints.\n"
                'Respond with JSON: {"disputes": [{"claim": "...", "viewpoint_a": "...", "viewpoint_b": "..."}]}'
            ),
        }

        specialist_results = {}
        runlog.report(f"Dispatching {len(prompts)} specialists in parallel", progress=0.25)
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                role: pool.submit(_run_specialist_research, role, p, ask)
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

        # Synthesis pass.
        #
        # This asked for "3-5 real sources with URLs and key facts", and that
        # one clause was the ceiling on how long a video could honestly be.
        # The key facts are what become claims, claims are what survive
        # fact-checking, and the script may state nothing that did not come
        # through there - so however many pages had been fetched and read in
        # full, five of them at most ever reached the writer. Every grounded
        # source is asked about now, and how many facts each one owes scales
        # with the video being written.
        urls = [source["url"] for source in grounded]
        synthesis_prompt = (
            f"Topic: {topic!r}\n<<GROUNDING>>\n"
            f"Chronology findings: {specialist_results.get('chronology')}\n"
            f"Metrics findings: {specialist_results.get('numbers')}\n"
            f"Controversies/Disputes: {specialist_results.get('counter_narrative')}\n"
            "Synthesize an authoritative research brief.\n"
            f"research_summary: {depth['summary_sentences']} sentences or so - "
            "the story of the subject, not a description of it: what happened, "
            "in what order, what caused what, and what is still argued about.\n"
            f"sources: one entry for every one of these {len(urls)} URLs, using "
            f"the URL exactly as given, each with up to {depth['facts_per_source']} "
            "key_facts drawn only from what that source actually says. A source "
            "that supports nothing gets an empty list rather than an invented "
            f"fact.\nThe URLs: {urls}\n"
            'Respond with JSON: {"research_summary": "...", "sources": [{"title": "...", "url": "...", "key_facts": ["..."]}]}'
        )

        runlog.report("Synthesising the brief from all three tracks", progress=0.75)
        synthesized = ask(synthesis_prompt, SYSTEM)

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

