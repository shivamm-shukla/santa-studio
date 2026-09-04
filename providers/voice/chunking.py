"""Long-script chunking and audio stitching for voice synthesis.

Long voice generations suffer from repetition, drift, and memory exhaustion
when passed as one giant block of text to neural TTS models. Splitting on
natural sentence boundaries (respecting both English punctuation and Hindi
purna viram) keeps prosody natural and allows synthesizing arbitrary length
scripts reliably.
"""

from __future__ import annotations

import os
import re
import tempfile
from typing import List, Tuple

from providers._ffmpeg_setup import ensure_ffmpeg_on_path

# Sentence terminators: English . ! ? \n and Hindi purna viram (।)
SENTENCE_SPLIT_REGEX = re.compile(r'([.!?।\n]+)')
CLAUSE_SPLIT_REGEX = re.compile(r'([,;:\-—]+|\s+(?:aur|lekin|par|ki|and|but|or|so)\s+)', re.IGNORECASE)


def chunk_script(text: str, max_chars: int = 240, max_words: int = 42) -> List[str]:
    """Splits text into coherent chunks suitable for TTS synthesis.

    1. Splits on sentence terminators (. ! ? । \n).
    2. If any single sentence is longer than `max_chars` or `max_words`,
       further splits on clause boundaries (commas, semicolons, conjunctions).
    3. Recombines short phrases so we don't synthesize tiny fragments in isolation.

    A piece that ended a paragraph keeps its trailing newline, because that is
    the only thing left downstream that says "this was a section break" -
    stitching reads it and holds the pause a beat longer there.
    """
    cleaned = text.strip()
    if not cleaned:
        return []

    raw_tokens = SENTENCE_SPLIT_REGEX.split(cleaned)
    sentences: List[str] = []
    current_sentence = ""

    for token in raw_tokens:
        if not token:
            continue
        if SENTENCE_SPLIT_REGEX.match(token):
            current_sentence += token
            s_clean = current_sentence.strip()
            if s_clean:
                sentences.append(s_clean + ("\n" if "\n" in token else ""))
            current_sentence = ""
        else:
            current_sentence += token

    if current_sentence.strip():
        sentences.append(current_sentence.strip())

    chunks: List[str] = []
    for sentence in sentences:
        words = sentence.split()
        if len(sentence.strip()) <= max_chars and len(words) <= max_words:
            chunks.append(sentence)
        else:
            # Sentence is too long; split on clauses
            clause_tokens = CLAUSE_SPLIT_REGEX.split(sentence)
            accum = ""
            for ct in clause_tokens:
                if not ct:
                    continue
                if len(accum) + len(ct) <= max_chars and len((accum + " " + ct).split()) <= max_words:
                    accum += ct
                else:
                    if accum.strip():
                        chunks.append(accum.strip())
                    accum = ct
            if accum.strip():
                chunks.append(accum.strip() + ("\n" if sentence.endswith("\n") else ""))

    # Pack very short adjacent chunks together to avoid fragment overhead
    packed: List[str] = []
    buffer = ""
    for ch in chunks:
        ch = ch.rstrip(" \t")
        if not ch.strip():
            continue
        if not buffer:
            buffer = ch
        elif (
            not buffer.endswith("\n")  # never pack across a section break
            and len(buffer) + len(ch) + 1 <= max_chars
            and (len(buffer.split()) + len(ch.split())) <= max_words
        ):
            buffer = buffer + " " + ch
        else:
            packed.append(buffer)
            buffer = ch

    if buffer:
        packed.append(buffer)

    return packed


# How much room to leave after a piece, by what it ends on.
#
# A narrator does not pause the same length after a comma as after a full
# stop, and the fixed 250ms this replaces did. The chunker splits on clause
# boundaries as well as sentence ones, so a long sentence could get a
# sentence-length gap dropped into the middle of it.
#
# Worth being accurate about the size of this, because the first version of
# these comments was not. Measured on a 77-word Hinglish script: the change
# moves the track's length by about twenty milliseconds. It is a correctness
# fix about where the pauses fall, not a fix for a slow-sounding read - that
# is the generation dials, in chatterbox_runner.py.
PAUSE_MS = {
    "paragraph": 520,   # a blank line in the script - a real beat
    "sentence": 300,    # . ! ? |
    "clause": 110,      # , ; : - and anything that ends mid-thought
}

# Silence the model leaves at the edges of what it generates, which lands on
# top of whatever pause we then add.
#
# Measured rather than assumed, after an earlier version of this comment
# guessed high: on a three-piece Hinglish script it was 140ms before the
# first piece and 20ms before each of the others, with no tail at all. Small
# - but it is silence nobody asked for, and it is the difference between the
# pause below being the pause you hear and being a lower bound on it.
EDGE_SILENCE_DBFS = -42.0
KEEP_LEAD_MS = 20
KEEP_TAIL_MS = 60

# The level every piece is brought to before stitching. Pieces are synthesised
# independently, so their levels wander - about 2 dB across three pieces on
# the script this was measured on, more as a script gets longer - and an
# unmatched join is audible as a step even when the voice either side of it
# is identical.
TARGET_DBFS = -20.0
# Only the boost is capped. Turning a piece down to the target is always
# safe; turning one up without limit is how a chunk that came out near-silent
# gets amplified into a burst of noise.
MAX_MATCH_BOOST_DB = 8.0


def pause_after(text: str) -> int:
    """How long to hold after a piece ending in `text`."""
    raw = text or ""
    if raw.endswith("\n"):
        return PAUSE_MS["paragraph"]
    stripped = raw.rstrip()
    if stripped[-1:] in ".!?\u0964":
        return PAUSE_MS["sentence"]
    return PAUSE_MS["clause"]


def _trim_edges(segment):
    """The piece with the model's own padding taken off both ends."""
    from pydub.silence import detect_leading_silence

    lead = detect_leading_silence(segment, silence_threshold=EDGE_SILENCE_DBFS)
    tail = detect_leading_silence(segment.reverse(), silence_threshold=EDGE_SILENCE_DBFS)

    start = max(0, lead - KEEP_LEAD_MS)
    end = len(segment) - max(0, tail - KEEP_TAIL_MS)
    if end - start < 50:
        return segment  # all quiet, or a very short piece; leave it alone
    return segment[start:end]


def _match_level(segment):
    """The piece brought to the common level, without crushing its dynamics.

    Gain, not normalisation: normalising each piece to its own peak makes a
    quiet sentence as loud as a shouted one, which is a worse artefact than
    the drift it fixes. The correction is also capped, so a piece that came
    out near-silent is left near-silent rather than amplified into noise.
    """
    if segment.dBFS == float("-inf"):
        return segment
    return segment.apply_gain(min(MAX_MATCH_BOOST_DB, TARGET_DBFS - segment.dBFS))


def stitch_audio_chunks(
    audio_paths: List[str],
    output_path: str = "",
    pause_ms: int = 0,
    sample_rate: int = 24000,
    texts: List[str] | None = None,
) -> Tuple[str, List[dict]]:
    """Concatenates synthesised pieces into one narration track.

    Each piece is trimmed of the padding the model leaves on it and brought
    to a common level, then held for a pause chosen by what its text ends on.
    Passing `pause_ms` overrides that with one fixed gap, which is what the
    old behaviour was and is kept for callers that want a metronome.

    Returns (output_audio_path, chunk_time_spans) where chunk_time_spans
    records the exact {"start": float, "end": float} offset for each piece
    in the finished file.
    """
    ensure_ffmpeg_on_path()
    from pydub import AudioSegment

    if not audio_paths:
        raise ValueError("No audio chunks provided to stitch.")

    if not output_path:
        handle, output_path = tempfile.mkstemp(suffix=".wav")
        os.close(handle)

    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    texts = texts or []
    combined = AudioSegment.silent(duration=0, frame_rate=sample_rate)
    time_spans = []

    current_ms = 0
    for idx, path in enumerate(audio_paths):
        segment = AudioSegment.from_file(path).set_frame_rate(sample_rate).set_channels(1)
        segment = _match_level(_trim_edges(segment))

        start_sec = current_ms / 1000.0
        dur_ms = len(segment)
        end_sec = (current_ms + dur_ms) / 1000.0

        time_spans.append({"start": round(start_sec, 3), "end": round(end_sec, 3), "duration": round(dur_ms / 1000.0, 3)})

        combined += segment
        current_ms += dur_ms

        if idx < len(audio_paths) - 1:
            gap = pause_ms if pause_ms else pause_after(texts[idx] if idx < len(texts) else "")
            if gap > 0:
                combined += AudioSegment.silent(duration=gap, frame_rate=sample_rate)
                current_ms += gap

    combined.export(output_path, format="wav")
    return output_path, time_spans
