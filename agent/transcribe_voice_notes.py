"""Transcribe and translate the six Project Sankalp voice notes on your own laptop.

Uses faster-whisper (open-source Whisper; runs on the CPU, no API key). The first
run downloads the model once (medium: about 1.5 GB). Indian languages are
detected automatically; each file gets the original-language transcript and an
English translation, with timestamps.

    pip install faster-whisper "av<19"
    python transcribe_voice_notes.py                      # medium model, ~10-20 min on a laptop CPU
    python transcribe_voice_notes.py --model large-v3     # best for Indian languages, slower
    python transcribe_voice_notes.py --folder "path\\to\\voice-notes"

Writes voice_notes_transcripts.md next to this script. Nothing is uploaded anywhere.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_FOLDER = HERE.parent / "data" / "voice-notes"
AUDIO = (".ogg", ".m4a", ".mp3", ".wav", ".opus")


def fmt(t: float) -> str:
    return f"{int(t // 60):02d}:{int(t % 60):02d}"


def run(model, path: Path, task: str, language: str | None):
    segments, info = model.transcribe(str(path), task=task, language=language, beam_size=5,
                                      vad_filter=True, condition_on_previous_text=False)
    lines = [f"[{fmt(s.start)}-{fmt(s.end)}] {s.text.strip()}" for s in segments]
    return info, lines


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--folder", type=Path, default=DEFAULT_FOLDER, help="folder with the voice notes")
    p.add_argument("--model", default="medium", help="tiny | base | small | medium | large-v3")
    p.add_argument("--out", type=Path, default=HERE / "voice_notes_transcripts.md")
    a = p.parse_args(argv)

    from faster_whisper import WhisperModel   # imported here so --help works without it

    files = sorted(f for f in a.folder.iterdir() if f.suffix.lower() in AUDIO)
    if not files:
        print(f"No audio files in {a.folder}")
        return 1
    print(f"Loading model '{a.model}' (first run downloads it) ...")
    model = WhisperModel(a.model, device="cpu", compute_type="int8")

    out = ["# Project Sankalp: voice-note transcripts", "",
           f"Model: faster-whisper {a.model}. Machine transcription: check names, numbers, batch and "
           f"invoice codes against the audio before quoting them.", ""]
    for f in files:
        t0 = time.time()
        print(f"{f.name}: transcribing ...", flush=True)
        info, original = run(model, f, "transcribe", None)
        lang = info.language
        print(f"  language {lang} ({info.language_probability:.0%}); translating ...", flush=True)
        _, english = run(model, f, "translate", lang) if lang != "en" else (info, original)
        out += [f"## {f.name}", "",
                f"- Duration: {fmt(info.duration)}  ·  detected language: **{lang}** "
                f"({info.language_probability:.0%})  ·  processed in {time.time() - t0:.0f} s", "",
                "**Original**", "", *[f"    {ln}" for ln in original], "",
                "**English**", "", *[f"    {ln}" for ln in english], ""]
        a.out.write_text("\n".join(out), encoding="utf-8")      # save after every file
    print(f"\nDone: {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
