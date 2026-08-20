def run(input_data: dict, config: dict) -> dict:
    """Input: {topic: str, reference_notes: dict}
    Output: {research_summary: str, sources: list[dict]}
    Each source: {title, url, key_facts: list[str]}
    """
    topic = input_data.get("topic", "the topic")
    sources = [
        {
            "title": f"[stub] Overview of {topic}",
            "url": "https://example.com/stub-source-1",
            "key_facts": [f"[stub fact 1 about {topic}]", f"[stub fact 2 about {topic}]"],
        },
        {
            "title": f"[stub] Deep dive: {topic}",
            "url": "https://example.com/stub-source-2",
            "key_facts": [f"[stub fact 3 about {topic}]"],
        },
    ]
    return {
        "success": True,
        "output": {
            "research_summary": f"[stub] Summary of research findings on {topic}, drawn from {len(sources)} sources.",
            "sources": sources,
        },
        "error": None,
    }
