import os
import json
from pathlib import Path
from scenedetect import VideoManager, SceneManager
from scenedetect.detectors import ContentDetector
from app.utils.logging import get_logger
from config import make_path


class SceneDetector:
    def __init__(self, video_path: str, backend='base', return_scenes=False,
                 min_scene_duration=0.1, threshold=30.0, transition_merge_gap=0.1):
        self.video_path = video_path
        self.backend = backend
        self.return_scenes = return_scenes
        self.min_scene_duration = min_scene_duration
        self.threshold = threshold
        self.transition_merge_gap = transition_merge_gap

        log_filename = f'{Path(video_path).stem}_log.txt'
        self.logger = get_logger(name='scene_detect', log_file=log_filename)

    def detect(self, start_time: float = 0, end_time: float = -1) -> list:
        try:
            self.logger.info(f'Detecting scenes for: {self.video_path}')

            video_manager = VideoManager([self.video_path])
            scene_manager = SceneManager()
            scene_manager.add_detector(ContentDetector(threshold=self.threshold))

            video_manager.set_downscale_factor()
            video_manager.start()
            scene_manager.detect_scenes(frame_source=video_manager)
            scene_list = scene_manager.get_scene_list()

            # Format output to match Sieve style
            scenes = []
            for start, end in scene_list:
                scenes.append({
                    "start": round(start.get_seconds(), 2),
                    "end": round(end.get_seconds(), 2)
                })

            self.logger.info(f"{len(scenes)} scenes detected.")
            return [{"scenes": scenes}]

        except Exception as e:
            self.logger.error(f'Scene detection failed: {e}')
            return []

    def detect_and_save(self) -> list:
        scenes = self.detect()
        if not scenes:
            self.logger.warning('No scenes detected. Skipping save.')
            return []

        out_path = make_path('processed/scene-detection', self.video_path, 'scene', 'json')
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump({'scenes': scenes[0]['scenes']}, f, indent=2)

        self.logger.info(f'Scene data saved to: {out_path}')
        return scenes
