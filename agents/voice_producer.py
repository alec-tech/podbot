"""
agents/voice_producer.py — Agent 3: TTS Audio Production
Converts script to broadcast-quality podcast audio using fallback TTS chain + FFmpeg
"""

import os
import re
import json
import logging
import subprocess
from pathlib import Path

from agents.tts import FallbackTTSChain

log = logging.getLogger("voice_producer")


def _load_show_config() -> dict:
    config_path = Path("config/show_config.json")
    with open(config_path) as f:
        return json.load(f)


class VoiceProducerAgent:

    def __init__(self):
        self.config = _load_show_config()
        self.chain = FallbackTTSChain(self.config)
        self.known_hosts = set(self.config.get("voices", {}).keys())
        self.assets_dir = Path("assets")
        self.output_dir = Path("outputs/audio")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self, script_data: dict, episode_date: str, edition: str = "morning") -> str:
        script = script_data["full_script"]
        lines = self._parse_script(script)
        log.info(f"  Parsed {len(lines)} lines of dialogue across {len(set(l['host'] for l in lines))} hosts")

        # Generate audio for each line
        audio_segments = []
        for i, line in enumerate(lines):
            audio_path = self._synthesize_line(line, i, episode_date, edition)
            if audio_path:
                audio_segments.append({
                    "path": audio_path,
                    "host": line["host"],
                    "pause_after": line.get("pause_after", 0.3)
                })
            if i % 10 == 0:
                log.info(f"  Generated {i+1}/{len(lines)} lines...")

        # Assemble full episode
        final_path = self._assemble_episode(audio_segments, episode_date, edition, script_data)
        return final_path

    def _parse_script(self, script: str) -> list:
        """Parse script into structured lines with host, direction, dialogue, pauses"""
        lines = []
        # Match: [HOST - direction]: "dialogue" or [HOST]: "dialogue"
        pattern = r'\[(\w+)(?:\s*-\s*([^\]]+))?\]:\s*"([^"]+)"'
        pause_pattern = r'\[PAUSE:\s*([\d.]+)s\]'

        for match in re.finditer(pattern, script, re.IGNORECASE):
            host = match.group(1).lower()
            direction = match.group(2) or ""
            dialogue = match.group(3)

            if host not in self.known_hosts:
                continue

            # Check for pause instruction after this line
            pause_match = re.search(pause_pattern, script[match.end():match.end()+50])
            pause_after = float(pause_match.group(1)) if pause_match else 0.3

            lines.append({
                "host": host,
                "direction": direction.strip(),
                "dialogue": dialogue,
                "pause_after": pause_after
            })

        return lines

    def _synthesize_line(self, line: dict, index: int, episode_date: str, edition: str = "morning") -> str:
        """Generate TTS for a single line via the fallback chain."""
        cache_dir = Path(f"outputs/audio/segments_{episode_date}_{edition}")
        cache_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(cache_dir / f"seg_{index:04d}_{line['host']}.mp3")

        if Path(output_path).exists():
            return output_path  # Use cached segment

        result = self.chain.synthesize_line(
            text=line["dialogue"],
            host_name=line["host"],
            output_path=output_path,
            direction=line["direction"],
        )

        if not result:
            log.error(f"  Failed to synthesize line {index}: {line['dialogue'][:50]}...")
        return result

    def _assemble_episode(self, segments: list, episode_date: str, edition: str, script_data: dict) -> str:
        """Use FFmpeg to assemble all segments with music and post-processing"""
        output_path = str(self.output_dir / f"episode_{episode_date}_{edition}.mp3")

        # Build FFmpeg concat list
        concat_path = str(self.output_dir / f"concat_{episode_date}.txt")
        intro_music = str(self.assets_dir / "intro_music.mp3")
        outro_music = str(self.assets_dir / "outro_music.mp3")

        with open(concat_path, 'w') as f:
            # Intro music (first 8 seconds)
            if Path(intro_music).exists():
                f.write(f"file '{Path(intro_music).resolve()}'\n")
                f.write("duration 8\n")

            # Episode segments with pauses
            for seg in segments:
                if seg["path"] and Path(seg["path"]).exists():
                    f.write(f"file '{Path(seg['path']).resolve()}'\n")
                    if seg["pause_after"] > 0.1:
                        silence = self._generate_silence(seg["pause_after"], episode_date)
                        f.write(f"file '{Path(silence).resolve()}'\n")

            # Outro music
            if Path(outro_music).exists():
                f.write(f"file '{Path(outro_music).resolve()}'\n")

        # Concatenate + normalize audio
        temp_path = output_path.replace('.mp3', '_raw.mp3')
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_path,
            "-acodec", "libmp3lame", "-b:a", "192k",
            temp_path
        ], check=True, capture_output=True)

        # Loudness normalization to -16 LUFS (podcast standard)
        subprocess.run([
            "ffmpeg", "-y", "-i", temp_path,
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-acodec", "libmp3lame", "-b:a", "192k",
            output_path
        ], check=True, capture_output=True)

        Path(temp_path).unlink(missing_ok=True)
        log.info(f"  Episode assembled: {output_path}")
        return output_path

    def _generate_silence(self, duration: float, episode_date: str) -> str:
        """Generate a short silence file"""
        silence_dir = Path(f"outputs/audio/silence")
        silence_dir.mkdir(parents=True, exist_ok=True)
        key = str(duration).replace('.', '_')
        silence_path = str(silence_dir / f"silence_{key}s.mp3")
        if not Path(silence_path).exists():
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
                "-t", str(duration), silence_path
            ], check=True, capture_output=True)
        return silence_path

    def get_duration(self, audio_path: str) -> float:
        """Get audio duration in seconds using FFprobe"""
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", audio_path
        ], capture_output=True, text=True)
        return float(result.stdout.strip())
