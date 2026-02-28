"""
agents/voice_producer.py v5 — Multi-Show TTS Audio Production
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


class VoiceProducerAgent:

    def __init__(self, show=None):
        if show is None:
            from agents.show_loader import load_show
            show = load_show("the-signal")
        self.show = show
        self.chain = FallbackTTSChain(show.config)
        self.known_hosts = set(show.voices.keys())
        self.assets_dir = Path("assets")

    def run(self, script_data: dict, episode_date: str, edition: str = "morning") -> str:
        output_dir = self.show.output_dir("audio")
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
        pattern = r'\[(\w+)(?:\s*-\s*([^\]]+))?\]:\s*"([^"]+)"'
        pause_pattern = r'\[PAUSE:\s*([\d.]+)s\]'

        for match in re.finditer(pattern, script, re.IGNORECASE):
            host = match.group(1).lower()
            direction = match.group(2) or ""
            dialogue = match.group(3)

            if host not in self.known_hosts:
                continue

            pause_match = re.search(pause_pattern, script[match.end():match.end()+50])
            pause_after = float(pause_match.group(1)) if pause_match else 0.3

            is_sponsor = "sponsor" in direction.lower()
            cleaned = dialogue if is_sponsor else self._clean_dialogue(dialogue)
            if not cleaned.strip():
                continue

            lines.append({
                "host": host,
                "direction": direction.strip(),
                "dialogue": cleaned,
                "pause_after": pause_after
            })

        return lines

    @staticmethod
    def _clean_dialogue(text: str) -> str:
        # Strip marked directions: (laughs), [beat], *sighs*
        text = re.sub(r'\([^)]*\)', '', text)
        text = re.sub(r'\[[^\]]*\]', '', text)
        text = re.sub(r'\*[^*]*\*', '', text)
        # Strip bare direction words that leaked at the start of dialogue
        text = re.sub(
            r'^(laughs|chuckles|sighs|pauses|smiles|nods|shrugs|grins|scoffs|gasps|groans)\s+',
            '', text, flags=re.IGNORECASE,
        )
        text = re.sub(r'  +', ' ', text).strip()
        return text

    def _synthesize_line(self, line: dict, index: int, episode_date: str, edition: str = "morning") -> str:
        cache_dir = self.show.output_dir("audio") / f"segments_{episode_date}_{edition}"
        cache_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(cache_dir / f"seg_{index:04d}_{line['host']}.mp3")

        if Path(output_path).exists():
            return output_path

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
        output_dir = self.show.output_dir("audio")
        output_path = str(output_dir / f"episode_{episode_date}_{edition}.mp3")

        concat_path = str(output_dir / f"concat_{episode_date}.txt")
        intro_music = str(self.assets_dir / "intro_music.mp3")
        outro_music = str(self.assets_dir / "outro_music.mp3")

        audio_cfg = self.show.audio_config
        bitrate = audio_cfg.get("bitrate", "192k")
        target_lufs = audio_cfg.get("target_lufs", -16)
        true_peak = audio_cfg.get("true_peak_dbtp", -1.5)
        intro_dur = audio_cfg.get("intro_music_duration_seconds", 8)

        with open(concat_path, 'w') as f:
            if Path(intro_music).exists():
                f.write(f"file '{Path(intro_music).resolve()}'\n")
                f.write(f"duration {intro_dur}\n")

            for seg in segments:
                if seg["path"] and Path(seg["path"]).exists():
                    f.write(f"file '{Path(seg['path']).resolve()}'\n")
                    if seg["pause_after"] > 0.1:
                        silence = self._generate_silence(seg["pause_after"], episode_date)
                        f.write(f"file '{Path(silence).resolve()}'\n")

            if Path(outro_music).exists():
                f.write(f"file '{Path(outro_music).resolve()}'\n")

        temp_path = output_path.replace('.mp3', '_raw.mp3')
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_path,
            "-acodec", "libmp3lame", "-b:a", bitrate,
            temp_path
        ], check=True, capture_output=True)

        subprocess.run([
            "ffmpeg", "-y", "-i", temp_path,
            "-af", f"loudnorm=I={target_lufs}:TP={true_peak}:LRA=11",
            "-acodec", "libmp3lame", "-b:a", bitrate,
            output_path
        ], check=True, capture_output=True)

        Path(temp_path).unlink(missing_ok=True)
        log.info(f"  Episode assembled: {output_path}")
        return output_path

    def _generate_silence(self, duration: float, episode_date: str) -> str:
        silence_dir = self.show.output_dir("audio") / "silence"
        silence_dir.mkdir(parents=True, exist_ok=True)
        key = str(duration).replace('.', '_')
        silence_path = str(silence_dir / f"silence_{key}s.mp3")
        sample_rate = self.show.audio_config.get("sample_rate", 44100)
        if not Path(silence_path).exists():
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r={sample_rate}:cl=stereo",
                "-t", str(duration), silence_path
            ], check=True, capture_output=True)
        return silence_path

    def get_duration(self, audio_path: str) -> float:
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", audio_path
        ], capture_output=True, text=True)
        return float(result.stdout.strip())
