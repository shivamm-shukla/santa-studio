import random


def run(input_data: dict, config: dict) -> dict:
    """Input: {niche: str, preferences: dict, user_topic: str | None}
    Output: {topics: list[str]}
    """
    user_topic = input_data.get("user_topic")
    if user_topic:
        return {"success": True, "output": {"topics": [user_topic]}, "error": None}

    niche = input_data.get("niche", "general")
    pool = [
        f"5 {niche} mistakes beginners make (and how to avoid them)",
        f"The history of {niche} in 10 minutes",
        f"Why {niche} is changing faster than you think",
        f"What nobody tells you about {niche}",
        f"{niche}: a complete beginner's guide",
    ]
    topics = random.sample(pool, k=3)
    return {"success": True, "output": {"topics": topics}, "error": None}
