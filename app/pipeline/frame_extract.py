import json
import subprocess
from pathlib import Path
from config import make_path
from app.utils.logging import get_logger


class FrameExtractor:
    def __init__(self, video_path: str, min_scene_len: float = 0.2):
        self.min_scene_len = min_scene_len
        self.video_path = Path(video_path)
        self.scene_json_path = self.frame_json = make_path('processed/scene-detection', video_path, 'scene', 'json')
        self.output_dir = make_path('interim/frames', video_path, '', '')
        self.output_dir.mkdir(parents=True, exist_ok=True)

        log_file = f'{self.video_path.stem}_log.txt'
        self.logger = get_logger('frame_extract', log_file)

    def _ffmpeg_extract(self, timestamp: float, out_path: Path):
        cmd = [
            'ffmpeg',
            '-loglevel', 'error',
            '-y',
            '-ss', f'{timestamp:.3f}',
            '-t', '1',
            '-i', str(self.video_path),
            '-frames:v', '1',
            '-q:v', '2',
            '-pix_fmt', 'yuvj420p',
            str(out_path)
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            self.logger.error('ffmpeg failed: %s', result.stderr.decode('utf-8', 'ignore').strip())

    def _get_brightness(self, timestamp: float) -> float:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-read_intervals', f'%{timestamp}+1',
            '-select_streams', 'v:0',
            '-show_frames',
            '-show_entries', 'frame_tags=lavfi.signalstats.YAVG',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(self.video_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        try:
            yavg_values = [float(line.strip()) for line in result.stdout.strip().split('\n') if line.strip()]
            if yavg_values:
                return yavg_values[0]
        except Exception:
            pass
        self.logger.warning('Could not get brightness at %.2fs', timestamp)
        return -1.0

    def extract(self) -> list[dict]:
        with open(self.scene_json_path, encoding='utf-8') as f:
            scenes = json.load(f).get('scenes', [])
        if not scenes:
            self.logger.warning('No scenes found in %s', self.scene_json_path)
            return []

        delta = 0.5
        results = []

        for i, sc in enumerate(scenes):
            start = float(sc['start_time'])
            end = float(sc['end_time'])
            dur = end - start
            if dur < self.min_scene_len:
                self.logger.warning('Scene %s too short (%.2fs), skipping', i, dur)
                continue

            mid = (start + end) / 2

            frame_path = self.output_dir / f'{self.video_path.stem}_scene_{i:02}.jpg'
            prev_path = self.output_dir / f'{self.video_path.stem}_scene_{i:02}_prev.jpg'
            next_path = self.output_dir / f'{self.video_path.stem}_scene_{i:02}_next.jpg'

            self._ffmpeg_extract(mid, frame_path)
            self._ffmpeg_extract(mid - delta, prev_path)
            self._ffmpeg_extract(mid + delta, next_path)

            brightness = self._get_brightness(mid)

            self.logger.info('[Scene %s] %.2fs → %s | Brightness: %.2f', i, mid, frame_path.name, brightness)

            results.append({
                'scene_index': i,
                'timestamp': mid,
                'frame_path': str(frame_path),
                'prev_frame_path': str(prev_path),
                'next_frame_path': str(next_path),
                'brightness': brightness
            })

        self.logger.info('%s frames (with context) extracted to %s', len(results), self.output_dir)
        return results
