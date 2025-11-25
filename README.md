---
title: "Video Virality Scoring"
emoji: "🎥"
colorFrom: "blue"
colorTo: "purple"
sdk: "streamlit"
sdk_version: "1.38.0"
app_file: "ui/streamlit_app.py"
pinned: false
---

# Video Virality Scoring

This project predicts how viral a video can become by analyzing its visuals, hooks, pacing, and overall content quality. It combines computer vision, scene detection, and LLM-based scoring to provide creators with fast and actionable insights.

## Features

### Scene Detection (Computer Vision)

* Automatically detects scene boundaries.
* Identifies visual changes, pacing, and transitions.
* Helps evaluate whether the video maintains viewer attention.

### LLM-Powered Scoring

* Rates the video across multiple virality factors such as:

  * Hook strength
  * Retention potential
  * Emotional impact
  * Narrative clarity
* Produces an overall Virality Score (0–100).

### Hook Analysis

* Analyzes the opening seconds of the video.
* Detects whether the hook can capture attention quickly.
* Suggests improvements for strengthening the introduction.

### Trend Prediction

* Estimates how well the video's content aligns with current online trends.
* Analyzes topics, pacing, and style compared to trending patterns.
* Provides a category-specific virality likelihood.

### Actionable Suggestions

* Offers practical recommendations:

  * What to cut
  * What to highlight
  * What to restructure
* Helps improve retention, shareability, and engagement.

## Tech Stack

* Streamlit for the user interface
* Python backend
* OpenCV for frame extraction and video processing
* Scene detection methods for boundary analysis
* Large Language Models for contextual scoring and suggestions
* Deployed on Hugging Face Spaces

## Project Structure

```
ui/
 └── streamlit_app.py       # Main UI script
core/
 ├── scene_detection.py     # Keyframe and boundary detection
 ├── scoring.py             # LLM evaluation pipeline
 └── hooks.py               # Hook extraction and scoring
models/
 └── ...                    # Model wrappers and utilities
assets/
 └── ...                    # Thumbnails, sample content
```

## How It Works

1. Upload a video.
2. The system extracts frames and detects scene boundaries.
3. The hook and key pacing segments are isolated.
4. Extracted information is passed to the LLM for scoring.
5. The system outputs:

   * Virality score
   * Hook score
   * Trend alignment
   * Detailed suggestions

## Supported Formats

* MP4
* MOV
* WEBM
* Other common social-media formats

## Roadmap

* Multi-platform scoring (TikTok, YouTube Shorts and Reels)
* Thumbnail scoring and generation
* Automatic highlight suggestions with timestamps
* Audio-based hook evaluation

## Contributing

Contributions are welcome.
Open an issue or submit a pull request with improvements or suggestions.

