#!/usr/bin/env python3
"""
F5-TTS Voice Cloning CLI & Library for Apple Silicon (M1/M2/M3/M4)
Usage:
    # 1. Clone voice and generate speech from text
    python f5_voice_cloner.py --ref TahmidVoice.mp3 --text "Your text to generate here" --out output.wav

    # 2. Specify custom reference time segment (e.g. 0 to 10 seconds)
    python f5_voice_cloner.py --ref TahmidVoice.mp3 --start 0 --duration 10 --text "Hello world!" --out hello.wav

    # 3. Launch interactive Gradio Web UI
    python f5_voice_cloner.py --webui
"""

import os
import sys
import argparse
import subprocess
import tempfile
import torch

# Ensure cache directories are local and writable
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(WORKSPACE_DIR, ".cache")
os.environ["MPLCONFIGDIR"] = os.path.join(CACHE_DIR, "matplotlib")
os.environ["HF_HOME"] = os.path.join(CACHE_DIR, "huggingface")
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)
os.makedirs(os.environ["HF_HOME"], exist_ok=True)


def get_device():
    if torch.backends.mps.is_available():
        return "mps"
    elif torch.cuda.is_available():
        return "cuda"
    return "cpu"


def extract_audio_segment(input_path, start_sec=0, duration_sec=10, target_sr=24000):
    """Extract a clean mono 24kHz WAV segment for optimal F5-TTS reference."""
    temp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_sec),
        "-t", str(duration_sec),
        "-i", input_path,
        "-c:a", "pcm_s16le",
        "-ar", str(target_sr),
        "-ac", "1",
        temp_wav
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return temp_wav


def transcribe_audio(audio_path, model_name="base"):
    """Auto-transcribe reference audio using OpenAI Whisper."""
    import whisper
    print(f"[*] Transcribing reference sample using Whisper ({model_name})...")
    model = whisper.load_model(model_name)
    result = model.transcribe(audio_path)
    text = result["text"].strip()
    print(f"[+] Detected Language: {result.get('language', 'unknown')}")
    print(f"[+] Reference Text: \"{text}\"")
    return text


def clone_voice(ref_audio, gen_text, ref_text=None, start_sec=0, duration_sec=10, output_file="cloned_voice.wav", device=None):
    from f5_tts.api import F5TTS

    if device is None:
        device = get_device()
    print(f"[*] Initializing F5-TTS on device: {device.upper()}...")
    f5tts = F5TTS(device=device)

    # Extract clean reference audio segment
    print(f"[*] Preparing reference audio ({start_sec}s - {start_sec + duration_sec}s)...")
    clean_ref_wav = extract_audio_segment(ref_audio, start_sec, duration_sec)

    # Auto-transcribe if reference text not provided
    if not ref_text:
        ref_text = transcribe_audio(clean_ref_wav)

    print(f"[*] Generating speech for target text: \"{gen_text}\"...")
    wav, sr, _ = f5tts.infer(
        ref_file=clean_ref_wav,
        ref_text=ref_text,
        gen_text=gen_text,
        file_wave=output_file
    )

    if os.path.exists(clean_ref_wav):
        os.remove(clean_ref_wav)

    print(f"[✓] Voice clone speech saved to: {output_file} (Sample Rate: {sr} Hz)")
    return output_file


def main():
    parser = argparse.ArgumentParser(description="F5-TTS Voice Cloning CLI (Apple Silicon M1/M2/M3/M4 Optimized)")
    parser.add_argument("--ref", type=str, default="TahmidVoice.mp3", help="Reference audio file (default: TahmidVoice.mp3)")
    parser.add_argument("--text", type=str, help="Target text to speak with cloned voice")
    parser.add_argument("--ref_text", type=str, default=None, help="Reference audio transcript (auto-detected with Whisper if omitted)")
    parser.add_argument("--start", type=float, default=0.0, help="Start time in seconds for reference clip (default: 0)")
    parser.add_argument("--duration", type=float, default=10.0, help="Duration in seconds for reference clip (default: 10)")
    parser.add_argument("--out", type=str, default="cloned_voice.wav", help="Output audio file path (default: cloned_voice.wav)")
    parser.add_argument("--device", type=str, default=None, choices=["mps", "cpu", "cuda"], help="Compute device (default: mps for Apple Silicon)")
    parser.add_argument("--webui", action="store_true", help="Launch interactive Gradio Web UI")

    args = parser.parse_args()

    if args.webui:
        print("[*] Launching F5-TTS Gradio Web Interface...")
        venv_gradio = os.path.join(WORKSPACE_DIR, ".venv_f5tts", "bin", "f5-tts_infer-gradio")
        if os.path.exists(venv_gradio):
            os.execv(venv_gradio, [venv_gradio])
        else:
            subprocess.run(["f5-tts_infer-gradio"])
        return

    if not args.text:
        print("Error: Please provide target text with --text \"...\" or launch with --webui")
        parser.print_help()
        sys.exit(1)

    ref_path = os.path.abspath(args.ref)
    if not os.path.exists(ref_path):
        print(f"Error: Reference audio file not found: {ref_path}")
        sys.exit(1)

    clone_voice(
        ref_audio=ref_path,
        gen_text=args.text,
        ref_text=args.ref_text,
        start_sec=args.start,
        duration_sec=args.duration,
        output_file=args.out,
        device=args.device
    )


if __name__ == "__main__":
    main()
