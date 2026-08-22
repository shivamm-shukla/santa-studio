"""Streamlit studio: a run dashboard (start/resume a run, watch it advance,
approve/edit/regenerate at gates) plus the voice-studio tab (upload a
sample, apply an Instagram-style filter preset, preview the result).

Drives the pipeline through PipelineManager.step() rather than run() -
Streamlit reruns this whole script on every interaction, so nothing here
can block on input() or long-polling the way the CLI/Telegram interfaces
do. `streamlit run studio_app.py` to launch.
"""

import glob
import os

import streamlit as st

import config
from manager import PipelineHalted, PipelineManager
from providers.voice.filters import PRESETS, apply_filter
from state import PipelineState, load_state

st.set_page_config(page_title="Santa Studio", layout="wide")
st.title("Santa Studio")

tab_pipeline, tab_voice = st.tabs(["Pipeline", "Voice Studio"])

# ---- Pipeline tab ----------------------------------------------------

with tab_pipeline:
    if "manager" not in st.session_state:
        st.session_state.manager = None

    if st.session_state.manager is None:
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Start a new run")
            niche = st.text_input("Niche", key="niche_input")
            user_topic = st.text_input("Specific topic (optional)", key="topic_input")
            voice_sample_path = st.text_input(
                "Voice sample path (blank = generic voice, no cloning)",
                value="",
                key="sample_input",
            )
            review_mode = st.selectbox("Review mode", ["autonomous", "checkpoints"])
            if st.button("Start", disabled=not niche):
                cfg = config.build_config()
                cfg["REVIEW_MODE"] = review_mode
                if not voice_sample_path:
                    # Nothing to clone from - the default voice provider
                    # needs a sample, so fall back rather than halt at
                    # VOICE_GENERATION.
                    cfg["ACTIVE_PROVIDERS"]["voice"] = "gtts"
                state = PipelineState(
                    niche=niche,
                    user_topic=user_topic or None,
                    voice_sample_path=voice_sample_path,
                )
                st.session_state.manager = PipelineManager(state, cfg, approval_handler=None)
                st.rerun()

        with col2:
            st.subheader("Resume an existing run")
            run_files = sorted(glob.glob("runs/*.json"))
            selected = st.selectbox("Run file", ["-"] + run_files)
            if st.button("Resume", disabled=selected == "-"):
                state = load_state(selected)
                st.session_state.manager = PipelineManager(state, config.build_config(), approval_handler=None)
                st.rerun()

    else:
        mgr = st.session_state.manager
        state = mgr.state
        st.write(f"**Run:** `{state.run_id}` — **State:** `{state.current_state}`")

        if state.current_state == "DONE":
            st.success("Pipeline complete.")
            video_path = (state.video_output or {}).get("video_path", "")
            st.write(f"`video_path`: {video_path}")
            if video_path and os.path.exists(video_path):
                st.video(video_path)
            if st.button("Start another run"):
                st.session_state.manager = None
                st.rerun()
        else:
            try:
                result = mgr.step()
            except PipelineHalted as e:
                st.error(f"Pipeline halted: {e}")
                if st.button("Back to start"):
                    st.session_state.manager = None
                    st.rerun()
            except Exception as e:
                st.error(f"Pipeline error: {e}")
                if st.button("Back to start"):
                    st.session_state.manager = None
                    st.rerun()
            else:
                if result["type"] in ("advanced", "done"):
                    st.rerun()
                elif result["type"] == "awaiting_approval":
                    st.subheader(f"Approval checkpoint: {result['checkpoint']}")
                    st.json(result["payload"])

                    c1, c2 = st.columns(2)
                    if c1.button("Approve"):
                        mgr.step(decision="approve")
                        st.rerun()
                    if c2.button("Regenerate"):
                        mgr.step(decision="regenerate")
                        st.rerun()

                    edited_text = st.text_area("Replacement text (for Edit)")
                    if st.button("Submit edit", disabled=not edited_text):
                        mgr.step(decision="edit", edited_payload={"edited_text": edited_text})
                        st.rerun()

# ---- Voice Studio tab --------------------------------------------------

with tab_voice:
    st.subheader("Clone + filter your voice")
    uploaded = st.file_uploader("Voice sample (~6s of clean speech)", type=["wav", "mp3"])

    if uploaded:
        os.makedirs("runs/voice_samples", exist_ok=True)
        sample_path = os.path.join("runs/voice_samples", uploaded.name)
        with open(sample_path, "wb") as f:
            f.write(uploaded.getvalue())

        st.audio(sample_path)

        preset = st.selectbox("Filter preset", list(PRESETS.keys()))
        if st.button("Apply filter"):
            try:
                st.session_state.filtered_path = apply_filter(sample_path, preset)
                st.session_state.filtered_preset = preset
            except Exception as e:
                st.error(f"Filter failed: {e}")

        if st.session_state.get("filtered_path"):
            st.write(f"Filtered ({st.session_state.get('filtered_preset')}):")
            st.audio(st.session_state.filtered_path)
