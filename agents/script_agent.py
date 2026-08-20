def run(input_data: dict, config: dict) -> dict:
    """Input: {research_summary: str, verified_claims: list[str]}
    Output: {script_text: str, scenes: list[dict]}
    Each scene: {timestamp_estimate, text, visual_hint}
    """
    claims = input_data.get("verified_claims", ["[stub claim]"])

    scenes = [
        {"timestamp_estimate": "0:00-0:15", "text": "[stub] Hook: a surprising question about the topic.", "visual_hint": "close-up, high energy b-roll"},
    ]
    for i, claim in enumerate(claims):
        start = 15 + i * 20
        scenes.append(
            {
                "timestamp_estimate": f"0:{start:02d}-0:{start + 20:02d}",
                "text": f"[stub] Explaining: {claim}",
                "visual_hint": "supporting b-roll matching the claim",
            }
        )
    scenes.append(
        {
            "timestamp_estimate": "end",
            "text": "[stub] Recap and call to action.",
            "visual_hint": "presenter-style closing shot",
        }
    )

    script_text = "\n".join(scene["text"] for scene in scenes)
    return {
        "success": True,
        "output": {"script_text": script_text, "scenes": scenes},
        "error": None,
    }
