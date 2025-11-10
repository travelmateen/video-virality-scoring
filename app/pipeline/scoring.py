import openai
import json
from pathlib import Path
from app.utils.logging import get_logger
from config import make_path, OPENAI_API_KEY


class VideoReport:
    def __init__(self, video_path: str, openai_api_key: str = ""):
        # ✅ Set OpenAI key (explicit or from environment)
        if openai_api_key:
            openai.api_key = openai_api_key
        else:
            import os
            openai.api_key = os.getenv("OPENAI_API_KEY", "")
        self.video_path = Path(video_path)
        self.audio_json = make_path('processed/audio-analysis', video_path, 'audio_analysis', 'json')
        self.frame_json = make_path('processed/frame-analysis', video_path, 'frame_analysis', 'json')
        self.hook_json = make_path('processed/hook-analysis', video_path, 'hook_analysis', 'json')
        self.output_json = make_path('reports', video_path, 'final_report', 'json')

        log_filename = f'{self.video_path.stem}_log.txt'
        self.logger = get_logger(name='video_report', log_file=log_filename)

        self.audio_analysis = self.load_json(self.audio_json)
        self.frame_analysis = self.load_json(self.frame_json)
        self.hook_analysis = self.load_json(self.hook_json)

    def load_json(self, path: Path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def extract_matrices(self):
        return {
            "tone": self.audio_analysis.get("tone", "unknown"),
            "emotion": self.audio_analysis.get("emotion", "unknown"),
            "pace": self.audio_analysis.get("pace", "unknown"),
            "facial_sync": self.hook_analysis.get("facial_sync", "unknown")
        }

    def prepare_prompt(self) -> str:
        prompt_sections = []
        prompt_sections.append(f"""
        You are an expert evaluator trained to assess the **virality potential and content quality** of short-form video ads (e.g., TikToks, Reels). You are provided with:

        - A sequence of scene-selected **frames**
        - A full **audio transcription**
        - Detailed **audio statistics**
        - And other meta-data of videos
                                
        Your task is to analyze the video and assign the **five scores** with weighted importance. Follow the criteria and format strictly.
                                
        ---
                                
        ### 🎯 Scores to Judge (Each 0–100)

        You must evaluate the following sub-categories:

        - `hook`: Does the video grab attention in the first 3 seconds? A good hook is **surprising, emotional, funny, or visually intense**. A poor hook is **slow, random, or bland**.
        
        - `visuals`: Are visuals high-resolution, diverse, and relevant to the message? Good visuals are **intentional and professionally framed**. Poor visuals are **static, noisy, or irrelevant**.
        
        - `audio`: Is the audio clean, engaging, and well-synced? Quality audio has **clarity, proper levels, and supports the visuals**. Poor audio is **distracting, flat, or off-sync**.
        
        - `engagement`: Does the video maintain interest? Strong pacing, emotional depth, or thought-provoking content improves this. Weak pacing or meaningless content hurts it.
        
        - `visual_diversity`: Does the video use **multiple camera angles, transitions, or visual styles**? A lack of variation makes it feel stale.

        ---
                                
        ### 📌 Scoring Enforcement Guidelines

        - Be **strict**: Low-effort content should fall well below 50  
        - Be **realistic**: Reward polish, creativity, clarity, and emotional impact  
        - Only videos with **clear intent and great execution** should reach 80+  
        - Penalize poor hooks, bland visuals, unclear audio, or meaningless structure  
        - Ensure your scores reflect meaningful differences between videos — **don't cluster everything around 60**
        
        ---
        """)

        if self.audio_analysis:
            prompt_sections.append("Audio Analysis:\n" + json.dumps(self.audio_analysis, indent=2))
        if self.frame_analysis:
            prompt_sections.append("\nFrame Analysis:\n" + json.dumps(self.frame_analysis, indent=2))
        if self.hook_analysis:
            prompt_sections.append("\nHook Alignment Analysis:\n" + json.dumps(self.hook_analysis, indent=2))

        matrices = self.extract_matrices()
        prompt_sections.append("\nHere are extracted behavioral/performance matrices:\n" + json.dumps(matrices, indent=2))

        prompt_sections.append(f"""
        ### 📤 Output Format (JSON Only — No Comments or Explanations):
        {{
        "video_name": "{self.video_path.stem}",
        "scores": {{
            "hook": 0,
            "visuals": 0,
            "audio": 0,
            "engagement": 0,
            "visual_diversity": 0
        }},
        "matrices": {{
            "tone": "",
            "emotion": "",
            "pace": "",
            "facial_sync": ""
        }},
        "summary": "",
        "suggestions": [
            "Specific improvement 1",
            "Specific improvement 2",
            "Specific improvement 3",
            ... more if required
        ]
        }}
        """)
        return "\n".join(prompt_sections)

    def query_llm(self, prompt: str) -> dict:
        try:
            response = openai.chat.completions.create(
                model='gpt-4o',
                messages=[
                    {"role": "system", "content": "You are a professional short-video quality evaluator."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4,
            )
            reply = response.choices[0].message.content.strip()
            cleaned = reply.replace('```json', '').replace('```', '')
            result = json.loads(cleaned)
            return result
        except Exception as e:
            self.logger.error(f"LLM generation failed: {e}")
            return {
                "scores": {
                    "hook": 0,
                    "visuals": 0,
                    "audio": 0,
                    "engagement": 0,
                    "visual_diversity": 0
                },
                "matrices": self.extract_matrices(),
                "summary": "Failed to generate report.",
                "suggestions": ["Try again", "Check input files", "Verify OpenAI key"]
            }
    
    def compute_virality_score(self, result):
        weights = {
            'hook': 0.18,
            'visuals': 0.20,
            'audio': 0.25,
            'engagement': 0.27,
            'visual_diversity': 0.10
        }

        sub_scores = result["scores"]
        base_score = sum(sub_scores[key] * weights[key] for key in weights)

        bonus = 0
        matrices = result.get("matrices", {})

        if matrices.get("emotion") in ["joy", "inspiration"]:
            bonus += 6
        if matrices.get("tone") in ["funny", "relatable"]:
            bonus += 6
        if matrices.get("facial_sync") in ["ok", "good"]:
            bonus += 4

        if sub_scores.get("hook", 0) <= 30:
            bonus -= 6
        if sub_scores.get("audio", 0) < 40:
            bonus -= 5
        if matrices.get("facial_sync") == "none":
            bonus -= 5

        final_score = max(0, min(100, int(base_score + bonus)))
        return final_score

    def generate(self) -> dict:
        self.logger.info("Preparing prompt for LLM...")
        prompt = self.prepare_prompt()

        self.logger.info("Querying LLM for report generation...")
        result = self.query_llm(prompt)
        total_score = self.compute_virality_score(result)
        final_output = {
            "video_name": self.video_path.stem,
            "total_score":  total_score,
            **result  
        }
        self.logger.info("Saving final report...")
        self.output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_json, 'w', encoding='utf-8') as f:
            json.dump(final_output, f, indent=2)

        self.logger.info("Report successfully generated at %s", self.output_json)
        return final_output
