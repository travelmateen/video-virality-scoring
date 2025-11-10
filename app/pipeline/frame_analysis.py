import os
import re
import json
import base64
import openai
from pathlib import Path
import google.generativeai as genai
from app.utils.logging import get_logger
from config import make_path, OPENAI_API_KEY, GEMINI_API_KEY, DATA_DIR


class FrameAnalyzer:
    def __init__(self, video_path: str, openai_api_key: str = "", save_dir: str = 'processed/frame-analysis'):
        # ✅ Set OpenAI key (explicit or from environment)
        
        # print(openai_api_key)

        if openai_api_key:
            openai.api_key = openai_api_key
        else:
            import os
            openai.api_key = os.getenv("OPENAI_API_KEY")

        self.video_path = Path(video_path)
        self.frames_dir = DATA_DIR / 'interim' / 'frames' / f'{self.video_path.stem}_'
        self.save_path = make_path(save_dir, video_path, 'frame_analysis', 'json')
        self.save_path.parent.mkdir(parents=True, exist_ok=True)

        log_file = f'{self.video_path.stem}_log.txt'
        self.logger = get_logger('frame_analysis', log_file)

    @staticmethod
    def encode_image(path: Path) -> str:
        with open(path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')

    @staticmethod
    def extract_json(text: str) -> dict:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match:
            return json.loads(match.group(1))

        match = re.search(r'(\{.*?\})', text, re.DOTALL)
        if match:
            return json.loads(match.group(1))

        raise ValueError('No valid JSON found in GPT response')

    def gpt_analyze(self, frame_path: Path, prev_path: Path, next_path: Path) -> dict:
        prompt = """
        You are an expert video content strategist. Analyze this video frame and surrounding context. 
        Determine if the lighting is poor or intentionally low for creative reasons. 

        Output JSON only:
        {
          lighting: 0-100,
          is_artistic_dark: true|false,
          composition: 0-100,
          has_text: true|false,
          text: "string",
          hook_strength: 0-100
        }
        """

        images = [
            {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{self.encode_image(p)}'}}
            for p in [prev_path, frame_path, next_path] if p.exists()
        ]

        response = openai.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role': 'user', 'content': [{'type': 'text', 'text': prompt}] + images}
            ],
            temperature=0.2,
            max_tokens=400,
        )
        return self.extract_json(response.choices[0].message.content)

    def analyze(self) -> dict:
        results = {}
        all_frames = sorted(self.frames_dir.glob('*_scene_*.jpg'))
        center_frames = [f for f in all_frames if '_prev' not in f.name and '_next' not in f.name]

        for frame in center_frames:
            prev = frame.with_name(frame.name.replace('.jpg', '_prev.jpg'))
            next_ = frame.with_name(frame.name.replace('.jpg', '_next.jpg'))

            self.logger.info('Analyzing frame: %s', frame.name)
            try:
                result = self.gpt_analyze(frame, prev, next_)
                results[frame.name] = result
            except Exception as e:
                self.logger.error('LLM analysis failed on %s: %s', frame.name, e)
                results[frame.name] = {'error': str(e)}

        with open(self.save_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)

        self.logger.info('Frame analysis saved to %s', self.save_path)
        return results

class HookAnalyzer:
    def __init__(self, video_path: str, gemini_api_key: str = ""):
        self.video_path = Path(video_path)
        self.frames_dir = Path('data/interim/frames') / f'{self.video_path.stem}_'
        self.audio_json = make_path('processed/audio-analysis', video_path, 'audio_analysis', 'json')
        self.output_json = make_path('processed/hook-analysis', video_path, 'hook_analysis', 'json')
        self.logger = get_logger('hook_analysis', f'{self.video_path.stem}_log.txt')

        # ✅ Set Gemini key (explicit or from environment)
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
        else:
            genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))
        self.model = genai.GenerativeModel('gemini-2.5-pro')

    def _encode_image(self, path: Path) -> bytes:
        with open(path, 'rb') as f:
            return f.read()

    def _load_audio_summary(self) -> dict:
        with open(self.audio_json, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _gemini_hook_alignment(self, audio_summary: dict, frames: list[Path]) -> dict:
        parts = [{'mime_type': 'image/jpeg', 'data': self._encode_image(f)} for f in frames if f.exists()]
        text = f"""You are a virality analyst. Analyze the opening visuals and tone:
        - Does the audio mood match the expressions and visuals?
        - Are viewers likely to be hooked in the first few seconds?

        Audio Summary: {json.dumps(audio_summary)}

        Give JSON only:
        {{
        "hook_alignment_score": 0-100,
        "facial_sync": "good|ok|poor|none",
        "comment": "short summary"
        }}"""

        try:
            response = self.model.generate_content([text] + parts)
            raw_text = getattr(response, 'text', '').strip()
            self.logger.debug("Gemini raw response: %s", raw_text)
            if not raw_text:
                raise ValueError("Gemini response was empty.")
            
            raw_text = (
                raw_text
                .replace('```json\n', '')
                .replace('\n```', '')
                .replace('```json', '')
                .replace('```', '')
            )

            return json.loads(raw_text)
        except json.JSONDecodeError as e:
            self.logger.error("❌ Failed to parse Gemini response as JSON: %s", e)
            self.logger.debug("Gemini response was: %r", getattr(response, 'text', '<<NO TEXT>>'))
            return {
                "hook_alignment_score": -1,
                "facial_sync": "none",
                "comment": "Invalid JSON response from Gemini"
            }
        except Exception as e:
            error_msg = str(e)
            self.logger.error("❌ Gemini API call failed: %s", e)
            
            # Check if it's an API key error - if so, raise it to stop the pipeline
            if any(keyword in error_msg.lower() for keyword in ["api_key", "invalid", "401", "403", "authentication", "unauthorized"]):
                raise ValueError(f"Invalid Gemini API key: {error_msg}") from e
            
            # For other errors, return defaults
            return {
                "hook_alignment_score": -1,
                "facial_sync": "none",
                "comment": f"Gemini API error: {error_msg}"
            }

    def analyze(self) -> dict:
        audio_summary = self._load_audio_summary()
        frames = sorted(self.frames_dir.glob('*_scene_*.jpg'))[:3]
        result = self._gemini_hook_alignment(audio_summary, frames)

        self.output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_json, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)

        self.logger.info('Hook analysis saved to %s', self.output_json)
        return result
