from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from config import settings
from services.cache import cache_key, cached_file_path, remember_file


HOST_RE = re.compile(
    r"^(?:\[)?(?P<speaker>HOST_A|HOST_B)(?:\])?\s*:\s*(?P<text>.+)$",
    re.IGNORECASE,
)


class PodcastGenerationError(RuntimeError):
    pass


@dataclass
class PodcastGenerationResult:
    audio_path: Path
    transcript_path: Path
    tts_backend: str
    stdout: str = ""
    stderr: str = ""


def host_transcript_to_podcastfy(script: str) -> str:
    lines: list[tuple[str, str]] = []
    current: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        if current and buffer:
            lines.append((current, " ".join(buffer).strip()))

    for raw in script.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = HOST_RE.match(line)
        if match:
            flush()
            current = match.group("speaker").upper()
            buffer = [match.group("text").strip()]
        elif current:
            buffer.append(line)
    flush()

    if not lines:
        raise PodcastGenerationError(
            "Script must contain HOST_A / HOST_B speaker lines"
        )

    merged: list[tuple[str, str]] = []
    for speaker, text in lines:
        if not text:
            continue
        if merged and merged[-1][0] == speaker:
            merged[-1] = (speaker, f"{merged[-1][1]} {text}")
        else:
            merged.append((speaker, text))

    if merged[0][0] == "HOST_B":
        merged.insert(0, ("HOST_A", "Let's get into it."))
    if merged[-1][0] == "HOST_A":
        merged.append(("HOST_B", "That's a strong place to leave it."))

    xml_parts: list[str] = []
    for speaker, text in merged:
        tag = "Person1" if speaker == "HOST_A" else "Person2"
        xml_parts.append(f"<{tag}>{text}</{tag}>")
    xml = "\n".join(xml_parts)

    errors = validate_podcastfy_transcript(xml)
    if errors:
        raise PodcastGenerationError("; ".join(errors))
    return xml


def validate_podcastfy_transcript(text: str) -> list[str]:
    errors: list[str] = []
    if text.count("<Person1>") != text.count("</Person1>"):
        errors.append("Mismatched Person1 tags")
    if text.count("<Person2>") != text.count("</Person2>"):
        errors.append("Mismatched Person2 tags")
    pairs = re.findall(
        r"<Person1>.*?</Person1>\s*<Person2>.*?</Person2>",
        text,
        re.DOTALL,
    )
    if not pairs:
        errors.append("Transcript must alternate Person1 then Person2")
    return errors


class PodcastGenerator:
    def __init__(self, tts_model: str | None = None, timeout: float | None = None) -> None:
        self.tts_model = tts_model or settings.podcastfy_tts_model
        self.timeout = timeout or settings.podcastfy_timeout_seconds

    def generate(self, script_path: str) -> Path:
        return self.generate_from_host_script(Path(script_path).read_text(encoding="utf-8")).audio_path

    def generate_from_host_script(self, script: str) -> PodcastGenerationResult:
        key = cache_key("podcastfy", script, self.tts_model)
        cached = cached_file_path("podcastfy", key, ".mp3")
        xml_path = settings.transcripts_dir / f"podcastfy_{key}.txt"
        xml = host_transcript_to_podcastfy(script)
        xml_path.write_text(xml, encoding="utf-8")

        if cached:
            return PodcastGenerationResult(
                audio_path=cached,
                transcript_path=xml_path,
                tts_backend=self.tts_model,
                stdout="cache hit",
            )

        errors: list[str] = []
        for backend in self._tts_backends():
            try:
                result = self._run_tts_direct(xml, xml_path, backend)
                break
            except Exception as exc:
                errors.append(f"{backend} TTS: {exc}")
        else:
            try:
                result = self._run_cli(xml_path)
            except PodcastGenerationError as exc:
                errors.append(str(exc))
                raise PodcastGenerationError(" | ".join(errors)) from exc

        if not result.audio_path.exists() or result.audio_path.stat().st_size < 1024:
            raise PodcastGenerationError(
                "Podcastfy produced an empty or invalid MP3. "
                "Check that the transcript uses alternating HOST_A / HOST_B lines."
            )
        remember_file("podcastfy", key, result.audio_path, ".mp3")
        return result

    def _tts_backends(self) -> list[str]:
        backends = [self.tts_model]
        if self.tts_model != "edge":
            backends.append("edge")
        return backends

    def _run_tts_direct(
        self, xml: str, transcript_path: Path, tts_model: str
    ) -> PodcastGenerationResult:
        try:
            from podcastfy.text_to_speech import TextToSpeech
        except Exception as exc:
            raise PodcastGenerationError(
                f"Podcastfy TTS module is unavailable: {exc}"
            ) from exc

        output_path = settings.audio_dir / f"podcast_{transcript_path.stem}.mp3"
        try:
            tts = TextToSpeech(
                model=tts_model,
                conversation_config={
                    "text_to_speech": {
                        "output_directories": {
                            "audio": str(settings.audio_dir),
                            "transcripts": str(settings.transcripts_dir),
                        }
                    }
                },
            )
            tts.convert_to_speech(xml, str(output_path))
        except Exception as exc:
            raise PodcastGenerationError(f"Podcastfy TTS failed ({tts_model}): {exc}") from exc

        return PodcastGenerationResult(
            audio_path=output_path,
            transcript_path=transcript_path,
            tts_backend=tts_model,
        )

    def _run_cli(self, transcript_path: Path) -> PodcastGenerationResult:
        command = [
            sys.executable,
            "-m",
            "podcastfy.client",
            "--transcript",
            str(transcript_path),
            "--tts-model",
            self.tts_model,
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise PodcastGenerationError(
                f"Podcastfy CLI timed out after {self.timeout}s"
            ) from exc
        except Exception as exc:
            raise PodcastGenerationError(f"Podcastfy CLI failed to start: {exc}") from exc

        if completed.returncode != 0:
            raise PodcastGenerationError(
                f"Podcastfy CLI exited {completed.returncode}: {completed.stderr or completed.stdout}"
            )

        audio_path = _parse_mp3_path(completed.stdout) or _newest_mp3(Path("data/audio"))
        if audio_path is None:
            raise PodcastGenerationError(
                f"Could not find Podcastfy MP3 in output: {completed.stdout}"
            )
        return PodcastGenerationResult(
            audio_path=audio_path,
            transcript_path=transcript_path,
            tts_backend=self.tts_model,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def _run_python_api(self, transcript_path: Path) -> PodcastGenerationResult:
        try:
            from podcastfy.client import generate_podcast
        except Exception as exc:
            raise PodcastGenerationError(
                f"Podcastfy Python API is unavailable: {exc}"
            ) from exc

        try:
            audio_path = generate_podcast(
                transcript_file=str(transcript_path),
                tts_model=self.tts_model,
                conversation_config={
                    "text_to_speech": {
                        "output_directories": {"audio": str(settings.audio_dir)},
                    }
                },
            )
        except Exception as exc:
            raise PodcastGenerationError(f"Podcastfy Python API failed: {exc}") from exc

        return PodcastGenerationResult(
            audio_path=Path(str(audio_path)),
            transcript_path=transcript_path,
            tts_backend=self.tts_model,
        )


def _parse_mp3_path(stdout: str) -> Path | None:
    for line in stdout.splitlines():
        if ".mp3" not in line:
            continue
        match = re.search(r"(\S+\.mp3)", line)
        if match:
            path = Path(match.group(1).strip("\"'"))
            if path.exists():
                return path
    return None


def _newest_mp3(directory: Path) -> Path | None:
    if not directory.exists():
        return None
    files = sorted(directory.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None
