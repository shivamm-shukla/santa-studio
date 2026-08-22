"""Turning a Timeline into a video file.

Agents produce a Timeline; something in here consumes it. Keeping the two apart
is what lets the renderer be replaced - MoviePy today, a direct FFmpeg
filtergraph when render time starts to matter - without a single agent
changing, and what makes re-rendering an edit cost no LLM calls.
"""
