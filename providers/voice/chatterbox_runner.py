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
             "out_dir": dir}
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

    os.makedirs(out_dir, exist_ok=True)

    # Chatterbox and its dependencies narrate themselves on stdout - PerthNet
    # announces its checkpoint, the S3 tokeniser announces each inference.
    # stdout is the reply channel and the caller parses all of it, so a single
    # progress line corrupts a run that otherwise succeeded. Everything the
    # work prints goes to stderr, where the caller already looks when it needs
    # to know why something failed; the JSON is written to the real stdout
    # once the work is done.
    with contextlib.redirect_stdout(sys.stderr):
        files, sample_rate = _synthesise(chunks, reference, language, out_dir)

    json.dump({"files": files, "sample_rate": sample_rate}, sys.stdout)
    return 0


def _synthesise(chunks, reference, language, out_dir):
    _note({"event": "loading", "total": len(chunks)})
    model = _load_model(language, _device())
    sample_rate = int(getattr(model, "sr", 24000))
    _note({"event": "loaded", "total": len(chunks)})

    language_id = "hi" if language in ("hi", "hinglish") else "en"
    accepts_language = False
    try:
        accepts_language = "language_id" in model.generate.__code__.co_varnames
    except Exception:
        pass

    written = []
    for index, text in enumerate(chunks):
        kwargs = {"audio_prompt_path": reference}
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
