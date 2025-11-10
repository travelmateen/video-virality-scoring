import os
import json
import ffmpeg
import whisper
import subprocess
import base64
from pathlib import Path
from typing import Dict, List
import google.generativeai as genai

from config import make_path, GEMINI_API_KEY
from app.utils.logging import get_logger


class AudioAnalyzer:
    def __init__(self, video_path: str, gemini_api_key: str = "", model_size: str = 'small'):
        self.model_size = model_size
        self.video_path = Path(video_path)
        self.audio_path = make_path('interim/audio', video_path, 'audio', 'wav')
        self.json_out = make_path('processed/audio-analysis', video_path, 'audio_analysis', 'json')
        self.logger = get_logger('audio_analysis', f'{self.video_path.stem}_log.txt')

        # ✅ Set Gemini key (explicit or from environment)
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
        else:
            genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))
        self.llm_model = genai.GenerativeModel('gemini-2.5-pro')

    def _extract_audio(self) -> None:
        self.audio_path.parent.mkdir(parents=True, exist_ok=True)
        (
            ffmpeg
            .input(str(self.video_path))
            .output(str(self.audio_path), ac=1, ar='16k', format='wav', loglevel='quiet')
            .overwrite_output()
            .run()
        )
        self.logger.info('Audio extracted to %s', self.audio_path)

    def _transcribe(self) -> Dict:
        model = whisper.load_model(self.model_size)
        return model.transcribe(str(self.audio_path), fp16=False)

    def _loudness_stats(self, audio_path: Path) -> Dict:
        cmd = [
            'ffmpeg', '-i', str(audio_path),
            '-af', 'volumedetect',
            '-f', 'null', 'NUL' if os.name == 'nt' else '/dev/null'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        mean = peak = None
        for line in result.stderr.splitlines():
            if 'mean_volume:' in line:
                mean = float(line.split('mean_volume:')[1].split()[0])
            if 'max_volume:' in line:
                peak = float(line.split('max_volume:')[1].split()[0])
        return {'loudness_mean': mean, 'loudness_peak': peak}

    def _load_visual_context(self) -> Dict:
        """Load nearby frames and brightness values from extracted frame data."""
        frame_json_path = make_path('processed/scene-detection', self.video_path, 'scene', 'json')
        frames_dir = make_path('interim/frames', self.video_path, '', '')

        if not frame_json_path.exists():
            self.logger.warning("Frame metadata not found: %s", frame_json_path)
            return {}

        with open(frame_json_path, 'r', encoding='utf-8') as f:
            scene_data = json.load(f)

        if not scene_data.get('scenes'):
            return {}

        scene = scene_data['scenes'][0]
        mid_time = (float(scene['start_time']) + float(scene['end_time'])) / 2
        scene_idx = 0

        def get_frame_path(tag):
            return frames_dir / f"{self.video_path.stem}_scene_{scene_idx:02}{tag}.jpg"

        def encode_image(p: Path) -> str:
            if p.exists():
                with open(p, 'rb') as f:
                    return base64.b64encode(f.read()).decode('utf-8')
            return ""

        return {
            'mid_time': mid_time,
            'frame': encode_image(get_frame_path('')),
            'prev': encode_image(get_frame_path('_prev')),
            'next': encode_image(get_frame_path('_next')),
            'brightness': float(scene.get('brightness', -1.0))
        }

    def _gemini_audio_analysis(self, text: str, loudness: Dict, wps: float, visuals: Dict) -> Dict:
        """LLM-enhanced audio analysis using audio + first scene frames + metadata"""
        prompt = f"""
        You are an expert video analyst. Based on the transcript, loudness, speaking pace,
        and the first scene's frames (prev, current, next), analyze the audio tone.

        Answer in JSON only:
        {{
        "tone": "calm|excited|angry|funny|sad|neutral",
        "emotion": "joy|sadness|anger|surprise|neutral|mixed",
        "pace": "fast|medium|slow",
        "delivery_score": 0-100,
        "is_hooking_start": true|false,
        "comment": "brief summary of audio performance",
        "is_dark_artistic": true|false,
        "brightness": 0-100
        }}

        Transcript: {text}
        Loudness: {json.dumps(loudness)}
        Words/sec: {wps}
        Frame brightness: {visuals.get('brightness')}
        """

        # ✅ Properly formatted parts for Gemini multimodal prompt
        parts = [{"text": prompt}]
        for tag in ['prev', 'frame', 'next']:
            img_b64 = visuals.get(tag)
            if img_b64:
                parts.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": base64.b64decode(img_b64),
                    }
                })

        try:
            response = self.llm_model.generate_content(
                contents=[{"role": "user", "parts": parts}],
                generation_config={'temperature': 0.3}
            )
            text = getattr(response, 'text', '').strip()
            cleaned = text.replace('```json', '').replace('```', '')
            return json.loads(cleaned)
        except Exception as e:
            error_msg = str(e)
            self.logger.error("LLM call failed: %s", e)
            
            # Check if it's an API key error - if so, raise it to stop the pipeline
            if any(keyword in error_msg.lower() for keyword in ["api_key", "invalid", "401", "403", "authentication", "unauthorized"]):
                raise ValueError(f"Invalid Gemini API key: {error_msg}") from e
            
            # For other errors, return defaults but log the issue
            return {
                "tone": "neutral",
                "emotion": "neutral",
                "pace": "medium",
                "delivery_score": 50,
                "is_hooking_start": False,
                "comment": "LLM analysis failed, using defaults",
                "is_dark_artistic": False,
                "brightness": visuals.get("brightness", -1.0)
            }

    def analyze(self) -> Dict:
        self._extract_audio()
        whisper_res = self._transcribe()
        full_text = whisper_res['text']
        duration_s = whisper_res['segments'][-1]['end'] if whisper_res['segments'] else 0
        wps = round(len(full_text.split()) / duration_s, 2) if duration_s else 0

        loudness = self._loudness_stats(self.audio_path)
        visual_context = self._load_visual_context()
        gemini_analysis = self._gemini_audio_analysis(full_text, loudness, wps, visual_context)

        result = {
            'full_transcript': full_text,
            'duration_seconds': duration_s,
            'word_count': len(full_text.split()),
            'words_per_second': wps,
            **loudness,
            **gemini_analysis
        }

        self.json_out.parent.mkdir(parents=True, exist_ok=True)
        with open(self.json_out, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)

        self.logger.info('Audio + Visual LLM analysis saved to %s', self.json_out)
        return result
