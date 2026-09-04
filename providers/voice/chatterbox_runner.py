"""Synthesis inside Chatterbox's own environment.

Chatterbox pins torch==2.6.0, numpy<2 and transformers==5.2.0. The studio runs
on torch 2.13 and numpy 2.5, which whisper, coqui-tts and moviepy all sit on,
so installing Chatterbox alongside them would downgrade the stack the rest of
the pipeline depends on. It gets an interpreter of its own instead, and this
is the only thing that runs in it.

Deliberately imports nothing from the project: this file is executed by a
different Python with a different site-packages, and the only contract between
the two is the JSON on stdin and stdout.

    stdin   {"chunks": [...], "reference": path, "language": "hi",
             "out_dir": dir, "voice": {"exaggeration": 0.45, ...}}
    stdout  {"files": [...], "sample_rate": 24000}
            {"error": "..."} on failure
    stderr  @progress {"event": "chunk", "done": 3, "total": 25}

The progress lines are the only thing here anyone reads while the work is
running. Cloning a few hundred words on a CPU takes tens of minutes, and
without them the caller - and so the room, and so you - has nothing to look
at between "starting" and "done" but a process using a lot of CPU.
"""

import contextlib
import json
import os
import sys

# How the model is asked to read, when the caller does not say.
#
# The library's own defaults (exaggeration 0.5, cfg_weight 0.5, temperature
# 0.8) are tuned for expressive one-liners, and on a paragraph of narration
# they are what makes a cloned voice sound like it is being read under
# duress: cfg_weight at 0.5 pins the delivery so hard to the reference
# clip's cadence that every sentence comes out at the same laboured pace,
# and exaggeration at 0.5 adds emphasis the sentence has not earned.
#
# Chatterbox's own guidance for a reference speaker with normal pace is to
# drop cfg_weight to about 0.3, which lets the pacing follow the sentence
# rather than the clip. Lower exaggeration reads as a narrator rather than
# an actor, and a slightly cooler temperature keeps a twenty-minute script
# from wandering off into a different voice halfway through.
NARRATION_DIALS = {
    "exaggeration": 0.4,
    "cfg_weight": 0.3,
    "temperature": 0.7,
    "repetition_penalty": 1.35,
    "min_p": 0.05,
    "top_p": 0.95,
}


def _accepted(fn) -> set:
    """The keyword names `fn` will take.

    The three model classes here do not share a signature - turbo has no
    cfg_weight, multilingual wants a language_id - and passing one an
    argument it does not know is a TypeError that fails the whole run. So
    the dials are filtered against the signature rather than assumed.
    """
    try:
        import inspect

        return set(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        try:
            return set(fn.__code__.co_varnames)
        except AttributeError:
            return set()


def _load_model(language: str, device: str):
    """The multilingual model for Hindi, the turbo one for English."""
    if language in ("hi", "hinglish"):
        try:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS

            return ChatterboxMultilingualTTS.from_pretrained(device=device)
        except (ImportError, AttributeError):
            pass
    else:
        try:
            from chatterbox.tts_turbo import ChatterboxTurboTTS

            return ChatterboxTurboTTS.from_pretrained(device=device)
        except (ImportError, AttributeError):
            pass

    from chatterbox.tts import ChatterboxTTS

    return ChatterboxTTS.from_pretrained(device=device)


def _note(payload: dict) -> None:
    """A line of progress, on stderr where the caller is already listening.

    Written straight to the real stderr and flushed: stdout is redirected
    into stderr while the model talks to itself, and a buffered line that
    arrives after the work is a line nobody saw.
    """
    sys.stderr.write("@progress " + json.dumps(payload) + "\n")
    sys.stderr.flush()


def _device() -> str:
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def main() -> int:
    request = json.load(sys.stdin)
    chunks = request["chunks"]
    reference = request["reference"]
    language = request.get("language", "en")
    out_dir = request["out_dir"]
    dials = dict(NARRATION_DIALS)
    dials.update(request.get("voice") or {})

    os.makedirs(out_dir, exist_ok=True)

    # Chatterbox and its dependencies narrate themselves on stdout - PerthNet
    # announces its checkpoint, the S3 tokeniser announces each inference.
    # stdout is the reply channel and the caller parses all of it, so a single
    # progress line corrupts a run that otherwise succeeded. Everything the
    # work prints goes to stderr, where the caller already looks when it needs
    # to know why something failed; the JSON is written to the real stdout
    # once the work is done.
    with contextlib.redirect_stdout(sys.stderr):
        files, sample_rate = _synthesise(chunks, reference, language, out_dir, dials)

    json.dump({"files": files, "sample_rate": sample_rate}, sys.stdout)
    return 0


def _prepare_once(model, reference, dials):
    """Reads the reference clip once instead of once per chunk.

    generate() re-encodes audio_prompt_path every time it is handed one, so
    a 300-chunk script ran the voice encoder 300 times on the same eight
    seconds of audio. Preparing the conditionals up front and then calling
    generate() without the path is the same synthesis for a fraction of the
    work - and, because every chunk then shares one encoding, the voice
    stops drifting between chunks.

    Returns True when it worked; the caller keeps passing the path if not.
    """
    prepare = getattr(model, "prepare_conditionals", None)
    if prepare is None:
        return False
    try:
        accepted = _accepted(prepare)
        kwargs = {k: v for k, v in dials.items() if k in accepted}
        prepare(reference, **kwargs)
        return getattr(model, "conds", None) is not None
    except Exception:
        return False


def _synthesise(chunks, reference, language, out_dir, dials):
    _note({"event": "loading", "total": len(chunks)})
    model = _load_model(language, _device())
    sample_rate = int(getattr(model, "sr", 24000))
    _note({"event": "loaded", "total": len(chunks)})

    language_id = "hi" if language in ("hi", "hinglish") else "en"
    accepted = _accepted(model.generate)
    accepts_language = "language_id" in accepted
    settings = {k: v for k, v in dials.items() if k in accepted}

    prepared = _prepare_once(model, reference, dials)
    _note({"event": "dials", "settings": settings, "prepared": prepared})

    written = []
    for index, text in enumerate(chunks):
        kwargs = dict(settings)
        if not prepared:
            kwargs["audio_prompt_path"] = reference
        if accepts_language:
            kwargs["language_id"] = language_id

        wav = model.generate(text, **kwargs)
        path = os.path.join(out_dir, f"chunk_{index:03d}.wav")

        try:
            import torchaudio

            torchaudio.save(path, wav, sample_rate)
        except Exception:
            import soundfile

            data = wav
            if hasattr(data, "detach"):
                data = data.detach().cpu().numpy()
            if hasattr(data, "ndim") and data.ndim > 1:
                data = data.squeeze()
            soundfile.write(path, data, sample_rate)

        written.append(path)
        _note({"event": "chunk", "done": index + 1, "total": len(chunks)})

    return written, sample_rate


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # reported to the caller as JSON, not a traceback
        json.dump({"error": f"{type(exc).__name__}: {exc}"}, sys.stdout)
        sys.exit(1)
