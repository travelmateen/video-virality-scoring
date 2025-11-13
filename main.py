from pathlib import Path
from files.pipeline.scoring import VideoReport
from files.pipeline.scene_detect import SceneDetector
from files.pipeline.frame_extract import FrameExtractor
from files.pipeline.audio_analysis import AudioAnalyzer
from files.pipeline.frame_analysis import FrameAnalyzer, HookAnalyzer


def run_pipeline(video_path: str):
    """
    Run the full virality analysis pipeline on a given video file.
    """
    video_path = Path(video_path)
    print(f'Analyzing video: {video_path.name}')

    SceneDetector(video_path).detect_and_save()
    print('Scene detection complete.')

    FrameExtractor(video_path).extract()
    print('Frame extraction complete.')

    FrameAnalyzer(video_path).analyze()
    print('Frame analysis complete.')

    AudioAnalyzer(video_path).analyze()
    print('Audio analysis complete.')

    HookAnalyzer(video_path).analyze()
    print('Hook analysis complete.')

    VideoReport(video_path).generate()
    print('Final scoring and GPT feedback complete.')

    print('Virality analysis pipeline completed successfully!')


if __name__ == '__main__':
    video_path = './data/raw/such_a_happy_reminder_every_time_i_look_at_it_couplewidgetapp_long.mp4'
    run_pipeline(video_path)
