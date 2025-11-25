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

This project evaluates how viral a video is likely to become by analyzing scenes, hooks, pacing, content quality, and trend alignment. It uses Computer Vision for scene detection and Large Language Models (LLMs) for scoring and content recommendations.

## Overview

The system processes a user-uploaded video through four core stages:

1. Scene Detection using Computer Vision
2. Hook and Frame-Level Analysis
3. LLM-Based Virality Scoring
4. Trend Alignment and Performance Prediction

The output includes a final Virality Score and actionable suggestions.

## Features

### Scene Detection

* Extracts keyframes and identifies scene boundaries.
* Measures pacing, cuts, transitions, and visual variation.
* Determines whether the video maintains viewer attention.

### LLM-Based Scoring

* Rates narrative clarity, emotional impact, pacing, and retention.
* Generates a 0–100 Virality Score.
* Provides strengths, weaknesses, and recommendations.

### Hook Analysis

* Focuses on the opening moments of the video.
* Evaluates whether the introduction can stop scrolling.
* Highlights issues in timing, structure, or visual appeal.

### Trend Prediction

* Evaluates video styles against current social-media trends.
* Checks pacing, topic relevance, and engagement patterns.
* Predicts potential performance on TikTok, Reels, and YouTube Shorts.

### Recommendations

* Identifies scenes to cut, extend, or enhance.
* Suggests improvements to strengthen retention and shareability.
* Provides guidance for boosting engagement and performance.

## Tech Stack

* Python
* Streamlit for UI
* OpenCV for frame and video processing
* Scene detection algorithms
* LLMs for scoring and content analysis
* Docker deployment on Hugging Face Spaces

## Project Structure

```
video-virality-scoring/
│
├── ui/
│   ├── __init__.py
│   └── streamlit_app.py
│
├── files/
│   └── pipeline/
│       ├── __init__.py
│       ├── audio_analysis.py
│       ├── frame_analysis.py
│       ├── frame_extract.py
│       ├── scene_detect.py
│       └── scoring.py
│
├── .github/workflows/
├── __pycache__/
│
├── .env
├── .huggingface.yml
├── .python-version
├── Dockerfile
├── README.md
├── START HERE.txt
├── __init__.py
├── config.py
├── demo.mp4
├── demo.txt
├── entrypoint.sh
├── main.py
├── packages.txt
└── pyproject.toml
```

## How It Works

1. User uploads a video.
2. Frames are extracted, and scenes are detected.
3. Audio, hooks, and key segments are analyzed.
4. Extracted descriptors and metadata are passed to the LLM.
5. Final output includes:

   * Virality Score
   * Hook Score
   * Trend Alignment
   * Improvement Suggestions

## Supported Formats

* MP4
* MOV
* WEBM
* Other social-media-friendly formats

## Roadmap

* Platform-specific scoring
* Thumbnail quality evaluation
* Timestamp-based auto-cut suggestions
* Audio-only hook quality analysis

## Contributing

Contributions are welcome. Open an issue or submit a pull request to suggest improvements or add new features.

---

For more tools and projects, visit:
[https://techtics.ai](https://techtics.ai)
