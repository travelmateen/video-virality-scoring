import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent

LOG_DIR = ROOT_DIR / 'logs'
DATA_DIR = ROOT_DIR / 'data'

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
SIEVE_API_KEY = os.getenv('SIEVE_API_KEY', '')
WHISPER_MODEL = os.getenv('WHISPER_MODEL', 'base')


def make_name(video_path: str, suffix: str, ext: str) -> str:
    """
    Returns: myvideo_transcript.json (etc.)
    """
    stem = Path(video_path).stem
    return f'{stem}_{suffix}.{ext}'


def make_path(subdir: str, video_path: str, suffix: str, ext: str) -> Path:
    """
    Returns: full path inside subfolder (e.g. data/processed/myvideo_scene.json)
    """
    filename = make_name(video_path, suffix, ext)
    return DATA_DIR / subdir / filename
