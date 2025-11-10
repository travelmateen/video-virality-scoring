import re
import sys
import json
import time
import signal
import traceback
import threading
import unicodedata
import hashlib
from pathlib import Path
import plotly.express as px
import yt_dlp
import streamlit as st

# -----------------------------
# Safe signal handling for non-main thread environments (yt_dlp)
# -----------------------------
if threading.current_thread() is not threading.main_thread():
    _orig_signal = signal.signal

    def _safe(sig, handler):
        if sig in (signal.SIGTERM, signal.SIGINT):
            return
        return _orig_signal(sig, handler)

    signal.signal = _safe

# -----------------------------
# Project paths & imports
# -----------------------------
ROOT = Path(__file__).resolve().parents[1]
ROOT_STR = str(ROOT.resolve())  # Ensure absolute path
# Insert at beginning for higher priority
if ROOT_STR not in sys.path:
    sys.path.insert(0, ROOT_STR)

# Verify app package exists
app_dir = ROOT / "app"
if not app_dir.exists():
    raise ImportError(f"Cannot find 'app' package at {app_dir}. ROOT={ROOT}")

from config import make_path
from app.pipeline.scene_detect import SceneDetector
from app.pipeline.frame_extract import FrameExtractor

# -----------------------------
# Storage layout
# -----------------------------
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

for name in ["raw", "interim", "processed", "reports"]:
    (DATA_DIR / name).mkdir(parents=True, exist_ok=True)

RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
REPORTS_DIR = DATA_DIR / "reports"

# -----------------------------
# Utilities
# -----------------------------
def sanitize_title(title: str, max_length: int = 150) -> str:
    title = unicodedata.normalize("NFKD", title)
    title = title.encode("ascii", "ignore").decode("ascii")
    title = re.sub(r"#\w+", "", title)
    title = re.sub(r"[^\w\s]", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    title = title.lower()
    return title[:max_length]


def sanitize_filename(filename: str) -> str:
    filename = filename.lower().replace(" ", "_")
    filename = unicodedata.normalize("NFKD", filename)
    filename = filename.encode("ascii", "ignore").decode("ascii")
    filename = re.sub(r"[^a-z0-9._-]", "", filename)
    return filename.strip()


def create_short_path(video_path: Path) -> str:
    """Create a short identifier for frame directories to avoid Windows path limits"""
    path_str = str(video_path)
    # Create a short hash of the full path
    path_hash = hashlib.md5(path_str.encode()).hexdigest()[:12]
    return f"frames_{path_hash}"


def get_frames_directory(video_path: Path) -> Path:
    """Get the frames directory path using short naming to avoid Windows path limits"""
    short_id = create_short_path(video_path)
    return INTERIM_DIR / "frames" / short_id


def download_video(url: str) -> tuple[Path, str]:
    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        info = ydl.extract_info(url, download=False)
        original_title = info.get("title", "video")
        ext = info.get("ext", "mp4")

    clean_title = sanitize_title(original_title)
    sanitized_name = sanitize_filename(clean_title) or "video"
    filename = f"{sanitized_name}.{ext}"
    file_path = RAW_DIR / filename

    if not file_path.exists():
        ydl_opts = {
            "outtmpl": str(file_path),
            "restrictfilenames": True,
            "quiet": True,
            "noplaylist": True,
            "no_color": True,
            "format": "bv*+ba/b",
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    return file_path, clean_title


def get_paths(video_path: Path):
    vp_str = str(video_path)
    audio_json = make_path("processed/audio-analysis", vp_str, "audio_analysis", "json")
    report_json = make_path("reports", vp_str, "final_report", "json")
    scene_json = make_path("processed/scene-detection", vp_str, "scene", "json")
    frame_json = make_path("processed/frame-analysis", vp_str, "frame_analysis", "json")
    hook_json = make_path("processed/hook-analysis", vp_str, "hook_analysis", "json")
    return scene_json, frame_json, audio_json, hook_json, report_json


def safe_load_json(path: Path | str):
    p = Path(path)
    if p.exists():
        try:
            with p.open(encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def remove_artifacts(video_path: Path):
    try:
        if video_path and video_path.exists():
            video_path.unlink(missing_ok=True)
    except Exception:
        pass

# -----------------------------
# Streamlit page config & styles
# -----------------------------
st.set_page_config(page_title="Virality Coach", layout="wide")

st.markdown(
    """
    <style>
      footer{display:none}
      .block-container{padding-top:1rem;padding-bottom:2rem;max-width:1100px}
      .title-center{text-align:center;margin-bottom:0.2rem}
      .desc-center{text-align:center;margin-bottom:1.2rem;color:#dbdbdb}
      .metric-card{background:#1f2937;border-radius:12px;padding:1.25rem;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.08);height:100%}
      .metric-card h4{margin:0;font-size:0.95rem;color:#d1d5db}
      .metric-card p{margin:0;font-size:1.8rem;font-weight:700;color:#ffffff}
      video{max-height:240px;border-radius:10px;margin-bottom:0.5rem}
      .status-msg{font-size:0.9rem;margin:0}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<h1 class="title-center">Video Virality Coach</h1>', unsafe_allow_html=True)
st.markdown('<p class="desc-center">An AI-powered system that analyzes and scores the virality potential of short-form videos (TikTok, Reels, Shorts) and delivers clear, actionable feedback to creators and marketers.</p>', unsafe_allow_html=True)

# -----------------------------
# Session state
# -----------------------------
DEFAULT_STATE = {
    "mode": None,
    "url": "",
    "uploaded_name": None,
    "video_path": None,
    "clean_title": None,
    "stage": None,
    "progress": 0,
    "status": [],
    "cancel": False,
    "error_msg": None,
    "_ready_to_run": False,
}

for k, v in DEFAULT_STATE.items():
    if k not in st.session_state:
        st.session_state[k] = v


def reset_state(clear_video: bool = True):
    keep = st.session_state.get("video_path") if not clear_video else None
    st.session_state.update(DEFAULT_STATE | {"video_path": keep})


def push_status(msg: str):
    st.session_state.status.append(msg)


# -----------------------------
# Pipeline step executor
# -----------------------------
STAGES = ["download video", "scene detection", "frames extraction", "frame analysis", "audio analysis", "hook analysis", "report"]

PROGRESS_MAP = {
    "download video": 10,
    "scene detection": 25,
    "frames extraction": 40,
    "frame analysis": 55,
    "audio analysis": 70,
    "hook analysis": 85,
    "report": 100,
}


def _run_current_stage():
    """
    Run the heavy work for the current stage.
    This is called only when _ready_to_run is True,
    so the UI has already rendered progress/cancel.
    """
    stage = st.session_state.stage
    if not stage or stage in ("done", "error"):
        return

    if st.session_state.cancel:
        push_status("⚠️ Process canceled by user.")
        print("[INFO] Processing canceled by user.")
        st.session_state.stage = None
        st.session_state.progress = 0
        try:
            vp = st.session_state.video_path
            if vp:
                remove_artifacts(Path(vp))
        except Exception:
            pass
        st.session_state._ready_to_run = False
        st.rerun()

    try:
        vp = Path(st.session_state.video_path) if st.session_state.video_path else None

        if stage == "download video":
            push_status("Starting download…")
            print(f"[INFO] Stage: Downloading video from {st.session_state.url}")
            path, title = download_video(st.session_state.url)
            st.session_state.video_path = str(path)
            st.session_state.clean_title = title

            # Skip full pipeline if a report already exists
            _, _, _, _, report_json = get_paths(path)
            if Path(report_json).exists():
                push_status("📄 Report already exists. Skipping analysis.")
                print("[INFO] Report already exists, skipping pipeline.")
                st.session_state.progress = 100
                st.session_state.stage = "done"
                st.session_state._ready_to_run = False
                st.rerun()

            st.session_state.progress = PROGRESS_MAP[stage]
            push_status("✅ Download complete.")
            print("[INFO] Download complete.")
            st.session_state.stage = "scene detection"
            st.session_state._ready_to_run = False
            st.rerun()

        elif stage == "scene detection":
            push_status("Detecting scenes…")
            print("[INFO] Stage: Scene detection started.")
            try:
                scene_detector = SceneDetector(str(vp))
                scene_detector.detect_and_save()
                
                # Verify the scene detection file was created
                scene_json, _, _, _, _ = get_paths(vp)
                if not Path(scene_json).exists():
                    raise FileNotFoundError("Scene detection failed - no output file")
                
                # Verify the scene file has the expected structure
                scene_data = safe_load_json(scene_json)
                if not scene_data or 'scenes' not in scene_data:
                    raise ValueError("Scene detection produced invalid results - no 'scenes' key")
                
                # Check if scenes have the required 'start_time' field
                if scene_data['scenes'] and 'start_time' not in scene_data['scenes'][0]:
                    print("[WARNING] Scene data missing 'start_time' field, adding compatible structure")
                    # Convert the scene data to the expected format
                    fixed_scenes = []
                    for i, scene in enumerate(scene_data['scenes']):
                        fixed_scene = {
                            'start_time': scene.get('start', 0),  # Use 'start' if available, else 0
                            'end_time': scene.get('end', 0),      # Use 'end' if available, else 0
                            'duration': scene.get('duration', 0), # Use 'duration' if available, else 0
                            'scene_number': i
                        }
                        fixed_scenes.append(fixed_scene)
                    
                    scene_data['scenes'] = fixed_scenes
                    
                    # Save the fixed scene data
                    with open(scene_json, 'w', encoding='utf-8') as f:
                        json.dump(scene_data, f, indent=2)
                    
                st.session_state.progress = PROGRESS_MAP[stage]
                push_status("✅ Scene detection done.")
                print("[INFO] Scene detection complete.")
                st.session_state.stage = "frames extraction"
                st.session_state._ready_to_run = False
                st.rerun()
                
            except Exception as e:
                # If scene detection fails, create a compatible scene file
                print(f"[WARNING] Scene detection failed: {e}. Creating fallback scene data.")
                push_status("⚠️ Scene detection failed. Using fallback scene data.")
                
                scene_json, _, _, _, _ = get_paths(vp)
                
                # Create compatible scene data with required 'start_time' field
                fallback_scene_data = {
                    "scenes": [{
                        "start_time": 0,
                        "end_time": 30,  # Assume 30 second scenes
                        "duration": 30,
                        "scene_number": 0
                    }]
                }
                
                # Ensure directory exists
                Path(scene_json).parent.mkdir(parents=True, exist_ok=True)
                
                with open(scene_json, 'w', encoding='utf-8') as f:
                    json.dump(fallback_scene_data, f, indent=2)
                
                st.session_state.progress = PROGRESS_MAP[stage]
                push_status("✅ Using fallback scene detection.")
                st.session_state.stage = "frames extraction"
                st.session_state._ready_to_run = False
                st.rerun()

        elif stage == "frames extraction":
            push_status("Extracting frames…")
            print("[INFO] Stage: Frame extraction started.")
            # Use the original FrameExtractor without modification
            FrameExtractor(str(vp)).extract()
            st.session_state.progress = PROGRESS_MAP[stage]
            push_status("✅ Frame extraction done.")
            print("[INFO] Frame extraction complete.")
            st.session_state.stage = "frame analysis"
            st.session_state._ready_to_run = False
            st.rerun()

        elif stage == "frame analysis":
            push_status("Analyzing frames…")
            if st.session_state.openai_key and st.session_state.openai_key.strip():
                from app.pipeline.frame_analysis import FrameAnalyzer
                try:
                    FrameAnalyzer(str(vp), openai_api_key=st.session_state.openai_key.strip()).analyze()
                except Exception as api_error:
                    error_msg = str(api_error)
                    if "invalid" in error_msg.lower() or "401" in error_msg or "authentication" in error_msg.lower():
                        st.session_state.stage = "error"
                        st.session_state.error_msg = f"OPENAI API KEY FAILED: Invalid OpenAI API Key provided. Please verify your API key is correct."
                        st.session_state._ready_to_run = False
                        st.rerun()
                    else:
                        raise
            else:
                st.session_state.stage = "error"
                st.session_state.error_msg = "OPENAI API KEY FAILED: OpenAI API Key is required for frame analysis but was not provided."
                st.session_state._ready_to_run = False
                st.rerun()
            st.session_state.progress = PROGRESS_MAP[stage]
            push_status("✅ Frame analysis done.")
            st.session_state.stage = "audio analysis"
            st.session_state._ready_to_run = False
            st.rerun()

        elif stage == "audio analysis":
            push_status("Analyzing audio…")
            if st.session_state.gemini_key and st.session_state.gemini_key.strip():
                from app.pipeline.audio_analysis import AudioAnalyzer
                try:
                    AudioAnalyzer(str(vp), gemini_api_key=st.session_state.gemini_key.strip()).analyze()
                except (ValueError, Exception) as api_error:
                    error_msg = str(api_error)
                    if "invalid" in error_msg.lower() or "401" in error_msg or "403" in error_msg or "api_key" in error_msg.lower() or "authentication" in error_msg.lower():
                        st.session_state.stage = "error"
                        st.session_state.error_msg = f"GEMINI API KEY FAILED: Invalid Gemini API Key provided. Error: {error_msg}"
                        st.session_state._ready_to_run = False
                        st.rerun()
                    else:
                        raise
            else:
                st.session_state.stage = "error"
                st.session_state.error_msg = "GEMINI API KEY FAILED: Gemini API Key is required for audio analysis but was not provided."
                st.session_state._ready_to_run = False
                st.rerun()
            st.session_state.progress = PROGRESS_MAP[stage]
            push_status("✅ Audio analysis done.")
            st.session_state.stage = "hook analysis"
            st.session_state._ready_to_run = False
            st.rerun()

        elif stage == "hook analysis":
            push_status("Evaluating hook…")
            if st.session_state.gemini_key and st.session_state.gemini_key.strip():
                from app.pipeline.frame_analysis import HookAnalyzer
                try:
                    HookAnalyzer(str(vp), gemini_api_key=st.session_state.gemini_key.strip()).analyze()
                except (ValueError, Exception) as api_error:
                    error_msg = str(api_error)
                    if "invalid" in error_msg.lower() or "401" in error_msg or "403" in error_msg or "api_key" in error_msg.lower() or "authentication" in error_msg.lower():
                        st.session_state.stage = "error"
                        st.session_state.error_msg = f"GEMINI API KEY FAILED: Invalid Gemini API Key provided. Error: {error_msg}"
                        st.session_state._ready_to_run = False
                        st.rerun()
                    else:
                        raise
            else:
                st.session_state.stage = "error"
                st.session_state.error_msg = "GEMINI API KEY FAILED: Gemini API Key is required for hook analysis but was not provided."
                st.session_state._ready_to_run = False
                st.rerun()
            st.session_state.progress = PROGRESS_MAP[stage]
            push_status("✅ Hook analysis done.")
            st.session_state.stage = "report"
            st.session_state._ready_to_run = False
            st.rerun()

        elif stage == "report":
            push_status("Generating final report…")
            if st.session_state.openai_key and st.session_state.openai_key.strip():
                from app.pipeline.scoring import VideoReport
                try:
                    VideoReport(str(vp), openai_api_key=st.session_state.openai_key.strip()).generate()
                except Exception as api_error:
                    error_msg = str(api_error)
                    if "invalid" in error_msg.lower() or "401" in error_msg or "authentication" in error_msg.lower():
                        st.session_state.stage = "error"
                        st.session_state.error_msg = f"OPENAI API KEY FAILED: Invalid OpenAI API Key provided. Error: {error_msg}"
                        st.session_state._ready_to_run = False
                        st.rerun()
                    else:
                        raise
            else:
                st.session_state.stage = "error"
                st.session_state.error_msg = "OPENAI API KEY FAILED: OpenAI API Key is required for report generation but was not provided."
                st.session_state._ready_to_run = False
                st.rerun()
            st.session_state.progress = PROGRESS_MAP[stage]
            push_status("🎉 Video report ready!")
            st.session_state.stage = "done"
            st.session_state._ready_to_run = False
            st.rerun()

    except Exception as e:
        err_type = type(e).__name__
        err_msg = str(e).strip()
        tb_last = traceback.format_exc(limit=1).strip() 
        st.session_state.stage = "error"
        st.session_state.error_msg = f"{err_type}: {err_msg}\n➡️ {tb_last}"
        st.session_state.progress = 0
        st.session_state._ready_to_run = False
        push_status(f"❌ {err_type}: {err_msg}")
        st.rerun()


def run_next_stage_if_needed():
    if not st.session_state.stage or st.session_state.stage in ("done", "error"):
        return
    if not st.session_state._ready_to_run:
        st.session_state._ready_to_run = True
        time.sleep(0.01)
        st.rerun()
    else:
        _run_current_stage()


# -----------------------------
# Input section
# -----------------------------

report, api_tab = st.tabs(["Upload Video", "🔑 API Configuration"])

with api_tab:
    st.markdown("### Configure Your API Keys")
    st.markdown("Enter your API keys below. Keys will be validated during analysis. If a key is invalid, you'll see an error message during the analysis stage.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.session_state.openai_key = st.text_input(
            "OpenAI API Key",
            type="password",
            placeholder="sk-...",
            help="Required for frame analysis and report generation",
            value=st.session_state.get("openai_key", "")
        )
    
    with col2:
        st.session_state.gemini_key = st.text_input(
            "Gemini API Key", 
            type="password",
            placeholder="AIza...",
            help="Required for audio analysis and hook analysis",
            value=st.session_state.get("gemini_key", "")
        )
    
    st.markdown("---")
    st.info("💡 Add your API keys and return to the Upload Video tab to start analysis. Invalid keys will show error messages during the analysis process.")

if 'openai_key' not in st.session_state:
    st.session_state.openai_key = ""
if 'gemini_key' not in st.session_state:
    st.session_state.gemini_key = ""

with report:
    method = st.radio("Choose Upload Method", ["Paste Video URL", "Upload MP4 File"], horizontal=True)

    col_in_1, col_in_2 = st.columns([1, 1])

    if method == "Paste Video URL":
        st.session_state.mode = "url"
        url = st.text_input(
            "Paste direct video URL [insta / tiktok / yt-shorts]",
            placeholder="https://example.com/@username/video/123",
            value=st.session_state.url,
        )
        st.session_state.url = url
        run_from_url = col_in_1.button("Run Analysis", key="run_url")

        if run_from_url:
            if not url:
                st.error("❌ Please enter a video URL.")
            else:
                st.session_state.cancel = False
                st.session_state.stage = "download video"
                st.session_state.status = []
                st.session_state.progress = 0
                st.session_state._ready_to_run = False 
                st.rerun()

    else:
        st.session_state.mode = "file"
        uploaded = st.file_uploader("Upload MP4 File", type=["mp4"])
        run_from_file = col_in_1.button("Run Analysis", key="run_file")

        if uploaded and run_from_file:
            clean_name = sanitize_filename(Path(uploaded.name).stem) + ".mp4"
            dest = RAW_DIR / clean_name
            with dest.open("wb") as f:
                f.write(uploaded.getbuffer())
            st.session_state.video_path = str(dest)
            st.session_state.clean_title = Path(clean_name).stem

            # Skip if a report is already present
            _, _, _, _, report_json = get_paths(dest)
            if Path(report_json).exists():
                st.session_state.stage = "done"
                st.session_state.status = ["📄 Report already exists. Skipping analysis."]
                st.session_state.progress = 100
                st.rerun()

            st.session_state.cancel = False
            st.session_state.status = ["✅ Upload complete."]
            st.session_state.progress = 0
            st.session_state.stage = "scene detection"
            st.session_state._ready_to_run = False  
            st.rerun()

# -----------------------------
# Progress & Status
# -----------------------------
if st.session_state.stage and st.session_state.stage not in ("done", "error"):
    percent = st.session_state.progress
    stage = st.session_state.stage.replace("_", " ").title()
    
    st.markdown(f"##### {stage}: {percent}%")
    st.progress(percent)

    if st.button("Cancel Processing"):
        st.session_state.cancel = True
        st.rerun()

run_next_stage_if_needed()

# -----------------------------
# Error state
# -----------------------------
if st.session_state.stage == "error":
    error_msg = st.session_state.error_msg or "An unknown error occurred."
    
    # Detect which API key failed and display prominently
    if "openai" in error_msg.lower() or "openai" in str(st.session_state.error_msg).lower():
        st.error("🚨 **API KEY ERROR: OpenAI Key Failed**")
        st.markdown("""
        <div style='background-color: #fee2e2; border-left: 4px solid #ef4444; padding: 1rem; margin: 1rem 0; border-radius: 4px;'>
            <h4 style='color: #991b1b; margin-top: 0;'>❌ OpenAI API Key Invalid or Missing</h4>
            <p style='color: #7f1d1d; margin-bottom: 0;'><strong>Error Details:</strong> {}</p>
            <p style='color: #7f1d1d; margin-top: 0.5rem;'>Please go to the <strong>🔑 API Configuration</strong> tab and update your OpenAI API key.</p>
        </div>
        """.format(error_msg), unsafe_allow_html=True)
    elif "gemini" in error_msg.lower() or "gemini" in str(st.session_state.error_msg).lower():
        st.error("🚨 **API KEY ERROR: Gemini Key Failed**")
        st.markdown("""
        <div style='background-color: #fee2e2; border-left: 4px solid #ef4444; padding: 1rem; margin: 1rem 0; border-radius: 4px;'>
            <h4 style='color: #991b1b; margin-top: 0;'>❌ Gemini API Key Invalid or Missing</h4>
            <p style='color: #7f1d1d; margin-bottom: 0;'><strong>Error Details:</strong> {}</p>
            <p style='color: #7f1d1d; margin-top: 0.5rem;'>Please go to the <strong>🔑 API Configuration</strong> tab and update your Gemini API key.</p>
        </div>
        """.format(error_msg), unsafe_allow_html=True)
    else:
        # Generic error display
        st.error("🚨 **ANALYSIS FAILED**")
        st.markdown(f"""
        <div style='background-color: #fee2e2; border-left: 4px solid #ef4444; padding: 1rem; margin: 1rem 0; border-radius: 4px;'>
            <h4 style='color: #991b1b; margin-top: 0;'>❌ Error Occurred</h4>
            <p style='color: #7f1d1d; margin-bottom: 0;'><strong>Error Details:</strong> {error_msg}</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.warning("⚠️ **Report Not Generated**: The analysis pipeline stopped due to the error above. No report was created.")
    
    if st.button("🔄 Reset & Try Again", type="primary", use_container_width=True):
        reset_state(clear_video=True)
        st.rerun()

# -----------------------------
# Results section
# -----------------------------
if st.session_state.stage == "done" and st.session_state.video_path:
    vp = Path(st.session_state.video_path)
    scene_json, frame_json, audio_json, hook_json, report_json = get_paths(vp)

    st.success("Analysis complete.")

    with st.expander("Preview Video", expanded=False):
        if vp.exists():
            st.video(str(vp), format="video/mp4")

    report = safe_load_json(report_json)
    audio_data = safe_load_json(audio_json)
    hook_data = safe_load_json(hook_json)

    if not report:
        st.warning("No report found. You can rerun the analysis.")
    else:
        results_tab, json_tab = st.tabs(["Results", "JSON Reports"])

        with results_tab:
            st.markdown(
                "<h2 style='text-align: center;'>📝 Video Virality Report</h2>",
                unsafe_allow_html=True
            )

            # --- Main Score Cards ---
            total = report.get("total_score", 0)
            st.markdown(f"""
                <div style="text-align:center; margin-bottom:1rem;">
                    <div style="font-size:2rem; font-weight:bold; color:#10b981;">Total Score: {total}</div>
                    <p style="color:#9ca3af;">Overall Virality Potential</p>
                </div>
            """, unsafe_allow_html=True)

            scores = report.get("scores", {})
            if scores:
                cols = st.columns(len(scores))
                for col, (cat, val) in zip(cols, scores.items()):
                    color = "#10b981" if val >= 70 else "#fbbf24" if val >= 50 else "#ef4444"
                    with col:
                        st.markdown(
                            f"""
                            <div style="background:{color}22;
                                        border-radius:12px;
                                        padding:1rem;
                                        text-align:center;
                                        box-shadow:0 2px 8px rgba(0,0,0,.08);height:100%">
                                <h4 style="margin:0; font-size:0.9rem; color:#d1d5db">{cat.title()}</h4>
                                <p style="margin:0; font-size:1.5rem; font-weight:700; color:{color}">{val}</p>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

            # --- Matrices (tone, emotion, pace, facial_sync) ---
            st.markdown(
                """
                <div style="text-align:center; margin-bottom:1rem; margin-top:1rem;">
                    <p style="color:#9ca3af;">Video Attributes</p>
                </div>
                """,
                unsafe_allow_html=True
            )
            matrices = report.get("matrices", {})
            if matrices:
                attr_cols = st.columns(len(matrices))
                for col, (k, v) in zip(attr_cols, matrices.items()):
                    color = "#10b981" if str(v).lower() in ["high", "positive", "fast", "good", "funny", "joy"] else "#fbbf24" if str(v).lower() in ["medium", "neutral", "mixed"] else "#ef4444"

                    with col:
                        st.markdown(f"""
                            <div style="background:{color}22;
                                        border-radius:12px;
                                        padding:1rem;
                                        text-align:center;
                                        box-shadow:0 2px 6px rgba(0,0,0,0.1)">
                                <h4 style="margin:0; font-size:0.9rem; color:#d1d5db">{k.title()}</h4>
                                <p style="margin:0; font-size:1.3rem; font-weight:700; color:{color}">{v}</p>
                            </div>
                        """, unsafe_allow_html=True)

            # --- Summary ---
            if "summary" in report:
                st.markdown(
                    """
                    <h2 style='text-align: center; font-size:1.4rem; margin-top:1.3rem;'>
                        Report Summary
                    </h2>
                    """,
                    unsafe_allow_html=True
                )
                st.markdown(
                    f"""
                    <div style='background-color:#1e3a8a20;
                                border-left: 0.25rem solid #3b82f6;
                                border-radius: 8px;
                                padding: 1rem;
                                text-align: center;
                                color: #d1d5db;'>
                        {report["summary"]}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            # --- Suggestions ---
            st.markdown(
                """
                <h2 style='text-align: center; font-size:1.4rem; margin-top:1.3rem;'>
                    Suggestions
                </h2>
                """,
                unsafe_allow_html=True
            )

            suggestions = report.get("suggestions", [])
            if suggestions:
                for i, s in enumerate(suggestions, start=1):
                    st.markdown(
                        f"<p style='text-align:center; font-size:1rem;'> {s}</p>",
                        unsafe_allow_html=True
                    )
            else:
                st.markdown(
                    "<p style='text-align:center; color:gray;'>No improvement suggestions provided.</p>",
                    unsafe_allow_html=True
                )

            # --- Audio Analysis ---
            if audio_data:
                st.markdown(
                    """
                    <h2 style='text-align: center; font-size:1.4rem; margin-top:1.5rem;'>
                        Audio Analysis
                    </h2>
                    """,
                    unsafe_allow_html=True
                )

                # --- Audio Score Cards ---
                metrics = {
                    "Delivery Score": audio_data.get("delivery_score", ""),
                    "Duration (s)": round(audio_data.get("duration_seconds", 0), 2),
                    "Words/Sec": audio_data.get("words_per_second", 0),
                    "Tone": audio_data.get("tone", ""),
                    "Emotion": audio_data.get("emotion", ""),
                    "Pace": audio_data.get("pace", ""),
                }

                cols = st.columns(len(metrics))
                for col, (title, value) in zip(cols, metrics.items()):
                    color = "#10b981"  

                    if title in ["Delivery Score", "Tone", "Emotion", "Pace"]:
                        if title == "Delivery Score" and isinstance(value, (int, float)):
                            color = "#10b981" if value >= 70 else "#fbbf24" if value >= 50 else "#ef4444"
                        else:
                            val = str(value).lower()
                            if val in ["high", "positive", "fast", "good", "funny", "clear", "joy"]:
                                color = "#10b981"
                            elif val in ["medium", "neutral", "mixed", "average"]:
                                color = "#fbbf24"
                            elif val in ["low", "negative", "slow", "bad", "sad"]:
                                color = "#ef4444"
                            else:
                                color = "#d1d5db" 

                    with col:
                        st.markdown(
                            f"""
                            <div style="background:{color}22;
                                        border-radius:12px;
                                        padding:1rem;
                                        text-align:center;
                                        box-shadow:0 2px 6px rgba(0,0,0,0.15);
                                        margin-bottom:0.8rem;">
                                <h4 style="margin:0; font-size:0.85rem; color:#d1d5db">{title}</h4>
                                <p style="margin:0; font-size:1.3rem; font-weight:700; color:{color}">{value}</p>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                # Transcript box
                st.markdown(
                    f"""
                    <div style='background:#111827;
                                border-left: 4px solid #3b82f6;
                                padding:1rem;
                                margin-top:1rem;
                                border-radius:8px;
                                text-align:left;
                                color:#e5e7eb;'>
                        <b>Transcript:</b><br>
                        <i>{audio_data.get("full_transcript","")}</i>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                # Comment box
                st.markdown(
                    f"""
                    <div style='background:#1e293b;
                                border-radius:8px;
                                padding:0.8rem;
                                margin-top:0.5rem;
                                text-align:center;
                                font-size:0.95rem;
                                color:#d1d5db;'>
                        {audio_data.get("comment","")}
                    </div>
                    """,
                    unsafe_allow_html=True
                )


            # --- Hook Analysis ---
            if hook_data:
                st.markdown(
                    """
                    <h2 style='text-align: center; font-size:1.4rem; margin-top:1.5rem;'>
                        Hook Analysis
                    </h2>
                    """,
                    unsafe_allow_html=True
                )

                # --- Hook Score Card ---
                score = hook_data.get("hook_alignment_score", 0)
                color = "#10b981" if score >= 70 else "#fbbf24" if score >= 50 else "#ef4444"

                st.markdown(
                    f"""
                    <div style="background:{color}22;
                                border-radius:12px;
                                padding:1.2rem;
                                text-align:center;
                                box-shadow:0 2px 6px rgba(0,0,0,0.1);
                                margin:0 auto;
                                width:50%;">
                        <h4 style="margin:0; font-size:1rem; color:#d1d5db;">Hook Alignment Score</h4>
                        <p style="margin:0; font-size:2rem; font-weight:700; color:{color};">{score}</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                # --- Comment Box ---
                st.markdown(
                    f"""
                    <div style='background:#1e293b;
                                border-radius:8px;
                                padding:0.8rem;
                                margin-top:0.5rem;
                                text-align:center;
                                font-size:0.95rem;
                                color:#d1d5db;'>
                        {audio_data.get("comment","")}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            # --- Download Report ---
            st.markdown("<br>", unsafe_allow_html=True) 
            st.download_button(
                "Download Final Report",
                json.dumps(report, indent=2),
                file_name="final_report.json",
            )

        with json_tab:
            with st.expander("Scene Detection", expanded=False):
                st.json(safe_load_json(scene_json))
            with st.expander("Extracted Frames", expanded=False):
                frames_dir = INTERIM_DIR / "frames" / f"{vp.stem}_"
                if frames_dir.exists():
                    imgs = sorted(frames_dir.glob("*.jpg"))
                    if imgs:
                        cols = st.columns(4)
                        for i, img in enumerate(imgs):
                            with cols[i % 4]:
                                st.image(str(img), use_container_width=True)
                    else:
                        st.info("No frames found.")
                else:
                    st.info("No frames directory found.")
            with st.expander("Frame Analysis", expanded=False):
                st.json(safe_load_json(frame_json))
            with st.expander("Audio Analysis", expanded=False):
                st.json(audio_data)
            with st.expander("Hook Analysis", expanded=False):
                st.json(hook_data)
            with st.expander("Final Report", expanded=False):
                st.json(report)

    # Reset button only after analysis is done
    if st.button("Reset Session"):
        reset_state(clear_video=True)
        st.rerun()