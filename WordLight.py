import subprocess
import numpy as np
import soundfile as sf
from scipy.io import wavfile
import os
import json
import torch
from whisper_timestamped import load_model, transcribe
import re
import sys
import datetime

# --- NOISEREDUCE MOD ---
import noisereduce as nr

from scipy.signal import butter, lfilter

try:
    from voicefixer import VoiceFixer
except ImportError:
    VoiceFixer = None

try:
    from df.enhance import enhance as df_enhance, init_df as df_init, load_audio as df_load_audio, save_audio as df_save_audio
    _DFN_AVAILABLE = True
except ImportError:
    _DFN_AVAILABLE = False

# ---- pyrnnoise import and check ----
try:
    import pyrnnoise
    _PYRNNOISE_AVAILABLE = True
except ImportError:
    _PYRNNOISE_AVAILABLE = False

try:
    import tkinter as tk
except ImportError:
    import Tkinter as tk
from tkinter import filedialog, messagebox, BooleanVar, Checkbutton, Button, IntVar, DoubleVar, StringVar
from tkinter import ttk
from tkinter import font as tkfont
from tkinter import colorchooser

try:
    import gradio as gr
    _GRADIO_AVAILABLE = True
except ImportError:
    _GRADIO_AVAILABLE = False

dt = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

DEMUC_MODELS = [
    "htdemucs",
    "htdemucs_ft",
    "htdemucs_6s",
    "repro_mdx_a_time_only",
    "repro_mdx_a_hybrid_only",
    "repro_mdx_a",
    "mdx_q",
    "mdx_extra_q",
    "mdx_extra",
    "mdx",
    "hdemucs_mmi"
]

VOICEFIXER_MODES = ["0", "1", "2", "all"]

def get_outputs_folder():
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Outputs")
    os.makedirs(folder, exist_ok=True)
    return folder

def timestamped_filename(basename, ext):
    dt = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{basename}_{dt}{ext}"

def list_output_files():
    outputs_dir = get_outputs_folder()
    return [os.path.join(outputs_dir, f) for f in os.listdir(outputs_dir)
            if os.path.isfile(os.path.join(outputs_dir, f))]

def select_files_and_options():
    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo("Select Video", "Select the input video file (e.g. .mp4)")
    video_file = filedialog.askopenfilename(
        title="Select Input Video",
        filetypes=[("Video Files", "*.mp4 *.mkv *.avi *.mov *.webm"), ("All Files", "*.*")]
    )
    if not video_file:
        raise Exception("No video file selected.")
    messagebox.showinfo("Select Music", "Select the background music file (e.g. .mp3)")
    music_file = filedialog.askopenfilename(
        title="Select Background Music",
        filetypes=[("Audio Files", "*.mp3 *.wav *.aac *.flac"), ("All Files", "*.*")]
    )
    if not music_file:
        raise Exception("No background music file selected.")
    root.destroy()

    opt_root = tk.Tk()
    opt_root.title("Processing Options")
    bypass_auto_var = BooleanVar(value=False)
    edit_transcript_var = BooleanVar(value=False)
    use_demucs_var = BooleanVar(value=True)
    use_noisereduce_var = BooleanVar(value=False)
    use_lowpass_var = BooleanVar(value=False)
    use_voicefixer_var = BooleanVar(value=False)
    use_deepfilternet_var = BooleanVar(value=True)
    use_pyrnnoise_var = BooleanVar(value=False)

    fonts = sorted(set(tkfont.families(opt_root)))
    default_font = "Arial" if "Arial" in fonts else fonts[0]

    left_frame = tk.Frame(opt_root)
    left_frame.pack(side="left", fill="both", expand=True, padx=(10, 5), pady=10)
    right_frame = tk.Frame(opt_root)
    right_frame.pack(side="right", fill="y", expand=False, padx=(5, 10), pady=10)

    font_label = tk.Label(left_frame, text="Subtitle Font:")
    font_label.pack(anchor="w", pady=(0, 2))
    font_var = tk.StringVar(value=default_font)
    font_menu = ttk.Combobox(left_frame, textvariable=font_var, values=fonts, state="readonly")
    font_menu.pack(anchor="w", pady=(0, 2))

    primary_color_var = StringVar(value="#FFFFFF")
    highlight_color_var = StringVar(value="#FFFF00")

    def pick_primary_color():
        color = colorchooser.askcolor(title="Select Subtitle Color", initialcolor=primary_color_var.get())
        if color[1]:
            primary_color_var.set(color[1])
    def pick_highlight_color():
        color = colorchooser.askcolor(title="Select Highlight (Spoken Word) Color", initialcolor=highlight_color_var.get())
        if color[1]:
            highlight_color_var.set(color[1])

    color_row = tk.Frame(left_frame)
    tk.Label(color_row, text="Subtitle Color:").pack(side="left", padx=4)
    tk.Button(color_row, text="Pick...", command=pick_primary_color, bg=primary_color_var.get()).pack(side="left")
    color_row.pack(anchor="w", pady=(10, 0))
    color_row2 = tk.Frame(left_frame)
    tk.Label(color_row2, text="Highlight (Spoken Word) Color:").pack(side="left", padx=4)
    tk.Button(color_row2, text="Pick...", command=pick_highlight_color, bg=highlight_color_var.get()).pack(side="left")
    color_row2.pack(anchor="w", pady=(0, 10))

    font_size_var = IntVar(value=36)
    font_preview_label = tk.Label(left_frame, text="Sample Subtitle Text", anchor="w")
    font_preview_label.pack(anchor="w", pady=(0, 8))

    def update_font_preview(*args):
        selected_font = font_var.get()
        selected_size = font_size_var.get()
        try:
            font_preview_label.config(font=(selected_font, 30))
        except tk.TclError:
            font_preview_label.config(font=(default_font, 30))
        font_preview_label.config(text=f"Preview: {selected_font} {selected_size}")

    font_var.trace_add("write", update_font_preview)
    font_size_var.trace_add("write", update_font_preview)
    update_font_preview()

    font_size_label = tk.Label(left_frame, text="Font Size (px):")
    font_size_label.pack(anchor="w", pady=(0, 2))
    font_size_slider = tk.Scale(left_frame, from_=18, to=100, orient="horizontal", variable=font_size_var)
    font_size_slider.pack(anchor="w", pady=(0, 8))

    marginv_label = tk.Label(left_frame, text="Caption Vertical Margin (higher value = higher up):")
    marginv_label.pack(anchor="w", pady=(0, 2))
    marginv_var = IntVar(value=75)
    marginv_slider = tk.Scale(left_frame, from_=0, to=400, orient="horizontal", variable=marginv_var)
    marginv_slider.pack(anchor="w", pady=(0, 8))

    threshold_label = tk.Label(left_frame, text="Auto-Editor Silence Threshold (0.01 to 0.20):")
    threshold_label.pack(anchor="w", pady=(0, 2))
    threshold_var = DoubleVar(value=0.04)
    threshold_slider = tk.Scale(left_frame, from_=0.01, to=0.20, resolution=0.01, orient="horizontal", variable=threshold_var)
    threshold_slider.pack(anchor="w", pady=(0, 8))

    margin_label = tk.Label(left_frame, text="Auto-Editor Margin (seconds, 0.1 to 2.0):")
    margin_label.pack(anchor="w", pady=(0, 2))
    margin_var = DoubleVar(value=0.5)
    margin_slider = tk.Scale(left_frame, from_=0.1, to=2.0, resolution=0.1, orient="horizontal", variable=margin_var)
    margin_slider.pack(anchor="w", pady=(0, 8))

    max_sentences_label = tk.Label(left_frame, text="Max Sentences per Subtitle:")
    max_sentences_label.pack(anchor="w", pady=(8, 2))
    max_sentences_var = IntVar(value=1)
    max_sentences_spin = tk.Spinbox(left_frame, from_=1, to=5, increment=1, textvariable=max_sentences_var, width=5)
    max_sentences_spin.pack(anchor="w", pady=(0, 8))

    max_words_label = tk.Label(left_frame, text="Max Words per Subtitle:")
    max_words_label.pack(anchor="w", pady=(0, 2))
    max_words_var = IntVar(value=5)
    max_words_spin = tk.Spinbox(left_frame, from_=3, to=25, increment=1, textvariable=max_words_var, width=5)
    max_words_spin.pack(anchor="w", pady=(0, 8))

    Checkbutton(left_frame, text="Bypass Auto-Editor (skip silence removal)", variable=bypass_auto_var).pack(anchor="w", pady=(0, 2))
    Checkbutton(left_frame, text="Edit transcript before creating subtitles", variable=edit_transcript_var).pack(anchor="w", pady=(0, 8))
    Checkbutton(left_frame, text="Enable DeepFilterNet Denoising", variable=use_deepfilternet_var).pack(anchor="w", pady=(0, 8))
    Checkbutton(left_frame, text="Enable pyrnnoise Denoising", variable=use_pyrnnoise_var).pack(anchor="w", pady=(0, 8))

    Checkbutton(right_frame, text="Enable Demucs Denoising", variable=use_demucs_var).pack(anchor="w", pady=(0, 2))
    demucs_model_label = tk.Label(right_frame, text="Demucs Model:")
    demucs_model_label.pack(anchor="w", pady=(0, 2))
    demucs_model_var = StringVar(value="htdemucs_ft")
    demucs_model_menu = ttk.Combobox(right_frame, textvariable=demucs_model_var, values=DEMUC_MODELS, state="readonly")
    demucs_model_menu.pack(anchor="w", pady=(0, 8))

    demucs_device_label = tk.Label(right_frame, text="Demucs Device:")
    demucs_device_label.pack(anchor="w", pady=(0, 2))
    has_cuda = torch.cuda.is_available()
    default_device = "cuda" if has_cuda else "cpu"
    demucs_device_var = StringVar(value=default_device)
    demucs_device_menu = ttk.Combobox(right_frame, textvariable=demucs_device_var, values=["cuda", "cpu"], state="readonly")
    demucs_device_menu.pack(anchor="w", pady=(0, 8))

    Checkbutton(right_frame, text="Enable Noisereduce", variable=use_noisereduce_var).pack(anchor="w", pady=(0, 2))
    nr_label = tk.Label(right_frame, text="Noisereduce Options:")
    nr_label.pack(anchor="w", pady=(16, 2))

    nr_propdec_label = tk.Label(right_frame, text="prop_decrease (0.1=light, 1.0=max):")
    nr_propdec_label.pack(anchor="w", pady=(0, 2))
    nr_propdec_var = DoubleVar(value=0.75)
    nr_propdec_slider = tk.Scale(right_frame, from_=0.1, to=1.0, resolution=0.01, orient="horizontal", variable=nr_propdec_var)
    nr_propdec_slider.pack(anchor="w", pady=(0, 8))

    nr_stationary_var = BooleanVar(value=False)
    nr_stationary_chk = Checkbutton(right_frame, text="Stationary noise", variable=nr_stationary_var)
    nr_stationary_chk.pack(anchor="w", pady=(0, 2))

    nr_freqsmooth_label = tk.Label(right_frame, text="freq_mask_smooth_hz (0=off, up to 1000):")
    nr_freqsmooth_label.pack(anchor="w", pady=(0, 2))
    nr_freqsmooth_var = IntVar(value=500)
    nr_freqsmooth_slider = tk.Scale(right_frame, from_=0, to=1000, orient="horizontal", variable=nr_freqsmooth_var)
    nr_freqsmooth_slider.pack(anchor="w", pady=(0, 8))

    Checkbutton(right_frame, text="Enable VoiceFixer Enhancement", variable=use_voicefixer_var).pack(anchor="w", pady=(0, 2))
    vf_label = tk.Label(right_frame, text="VoiceFixer Mode:")
    vf_label.pack(anchor="w", pady=(8, 2))
    vf_mode_var = StringVar(value="2")
    vf_mode_menu = ttk.Combobox(right_frame, textvariable=vf_mode_var, values=VOICEFIXER_MODES, state="readonly")
    vf_mode_menu.pack(anchor="w", pady=(0, 8))

    Checkbutton(right_frame, text="Enable Low-Pass Filter", variable=use_lowpass_var).pack(anchor="w", pady=(0, 2))
    lp_label = tk.Label(right_frame, text="Low-Pass Filter Cutoff (Hz, 1000–20000):")
    lp_label.pack(anchor="w", pady=(10, 2))
    lp_cutoff_var = IntVar(value=8000)
    lp_slider = tk.Scale(right_frame, from_=100, to=20000, resolution=100, orient="horizontal", variable=lp_cutoff_var, length=220)
    lp_slider.pack(anchor="w", pady=(0, 8))

    bgm_volume_label = tk.Label(right_frame, text="Background Music Volume\n(0.00 = silent, 1.00 = full):")
    bgm_volume_label.pack(anchor="n", pady=(0, 2))
    bgm_volume_var = DoubleVar(value=0.15)
    bgm_volume_slider = tk.Scale(right_frame, from_=0.00, to=1.00, resolution=0.01, orient="horizontal", variable=bgm_volume_var, length=220)
    bgm_volume_slider.pack(anchor="n", pady=(0, 8))

    video_codec_var = tk.StringVar(value="hevc_nvenc")
    qp_var = tk.StringVar(value="30")

    codec_label = tk.Label(right_frame, text="Video Codec (e.g. hevc_nvenc, h264_nvenc, libx264):")
    codec_label.pack(anchor="w", pady=(16, 2))
    codec_entry = tk.Entry(right_frame, textvariable=video_codec_var)
    codec_entry.pack(anchor="w", pady=(0, 8))

    qp_label = tk.Label(right_frame, text="FFmpeg QP Value (Quality, 0=lossless, 30=good, 40=small file):")
    qp_label.pack(anchor="w", pady=(0, 2))
    qp_entry = tk.Entry(right_frame, textvariable=qp_var)
    qp_entry.pack(anchor="w", pady=(0, 8))

    def close_options():
        opt_root.quit()

    Button(opt_root, text="Continue", command=close_options).pack(side="bottom", pady=10)

    opt_root.mainloop()
    opt_root.destroy()

    return (video_file, music_file, bypass_auto_var.get(), edit_transcript_var.get(),
            font_var.get(), font_size_var.get(), marginv_var.get(),
            threshold_var.get(), margin_var.get(),
            demucs_model_var.get(), demucs_device_var.get(), bgm_volume_var.get(),
            max_sentences_var.get(), max_words_var.get(),
            nr_propdec_var.get(), nr_stationary_var.get(), nr_freqsmooth_var.get(),
            lp_cutoff_var.get(),
            use_demucs_var.get(), use_noisereduce_var.get(), use_lowpass_var.get(), use_voicefixer_var.get(),
            vf_mode_var.get(), use_deepfilternet_var.get(), use_pyrnnoise_var.get(),
            primary_color_var.get(), highlight_color_var.get(),
            video_codec_var.get(), qp_var.get())

def run_pyrnnoise(input_wav, output_wav):
    if not _PYRNNOISE_AVAILABLE:
        print("pyrnnoise not available.")
        return
    print("Running pyrnnoise (CLI recommended)...")
    try:
        result = subprocess.run(
            ["denoise", input_wav, output_wav],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"Saved: {output_wav}")
            return
        else:
            print("pyrnnoise CLI failed, falling back to Python API...")
    except FileNotFoundError:
        print("pyrnnoise CLI not found, using Python API...")
    rate, data = sf.read(input_wav)
    denoised = pyrnnoise.RNNoise(rate).process_buffer(data)
    sf.write(output_wav, denoised, rate)
    print(f"Saved: {output_wav}")

def run_deepfilternet(input_wav, output_wav):
    if not _DFN_AVAILABLE:
        raise ImportError(
            "DeepFilterNet is not installed. Run `pip install deepfilternet`.\n"
            "See: https://github.com/Rikorose/DeepFilterNet"
        )
    print(f"Running DeepFilterNet on {input_wav} ...")
    model, df_state, _ = df_init()
    audio, _ = df_load_audio(input_wav, sr=df_state.sr())
    enhanced = df_enhance(model, df_state, audio)
    df_save_audio(output_wav, enhanced, df_state.sr())
    print(f"DeepFilterNet denoised audio saved to: {output_wav}")

def get_framerate(video_path):
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate",
        "-of", "json", video_path
    ], capture_output=True, text=True)
    rate_info = json.loads(probe.stdout)
    rate_str = rate_info["streams"][0]["r_frame_rate"]
    num, den = map(float, rate_str.split('/'))
    return num / den if den != 0 else 30.0

def get_video_resolution(video_path):
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json", video_path
    ], capture_output=True, text=True)
    info = json.loads(probe.stdout)
    width = info["streams"][0]["width"]
    height = info["streams"][0]["height"]
    return width, height

def write_words_txt(words, txt_path):
    with open(txt_path, "w", encoding="utf-8") as f:
        for w in words:
            f.write(f"{w['start']:.2f} - {w['end']:.2f}: {w['word']}\n")

def open_and_edit_txt(txt_path):
    print(f"Opening transcript for editing: {txt_path}")
    if os.name == "nt":
        os.startfile(txt_path)
    else:
        subprocess.run(['open' if sys.platform == 'darwin' else 'xdg-open', txt_path])
    input("Edit the file and save. Press Enter when done...")

def update_words_from_txt(words, txt_path):
    with open(txt_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    if len(lines) != len(words):
        print(f"⚠️ Warning: Line count changed. {len(words)} original, {len(lines)} in edited file.")
    min_len = min(len(words), len(lines))
    for i in range(min_len):
        if ':' in lines[i]:
            new_word = lines[i].split(":", 1)[1].strip()
        else:
            new_word = lines[i].strip()
        words[i]['word'] = new_word
    return words[:min_len]

def run_demucs_denoise(input_wav, output_wav, demucs_model="htdemucs_ft", demucs_device="cuda"):
    print(f"Running Demucs for denoising: {input_wav}")
    output_folder = "demucs_outputs"
    if os.path.exists(output_folder):
        import shutil
        shutil.rmtree(output_folder, ignore_errors=True)
    demucs_cmd = [
        "demucs",
        "-n", demucs_model,
        "-d", demucs_device,
        "--two-stems", "vocals",
        "--shifts", "20",
        "-o", output_folder,
        input_wav
    ]
    print("Running Demucs command:", " ".join(demucs_cmd))
    process = subprocess.Popen(
        demucs_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    while True:
        line = process.stdout.readline()
        if line == '' and process.poll() is not None:
            break
        if line:
            print(line, end='')
    process.wait()
    if process.returncode != 0:
        raise Exception("Demucs failed, see output above.")
    base = os.path.splitext(os.path.basename(input_wav))[0]
    vocals_path = os.path.join(output_folder, demucs_model, base, "vocals.wav")
    if not os.path.exists(vocals_path):
        raise Exception("Demucs did not produce the expected vocals file. Check demucs output above.")
    wav, sr = sf.read(vocals_path)
    sf.write(output_wav, wav, sr)
    import shutil
    shutil.rmtree(output_folder, ignore_errors=True)
    print(f"Demucs denoised audio saved to: {output_wav}")

def get_video_duration(video_path):
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path
    ], capture_output=True, text=True)
    try:
        duration = float(probe.stdout.strip())
    except Exception:
        duration = None
    return duration

def apply_lowpass_filter(data, sr, cutoff_hz):
    nyq = 0.5 * sr
    norm_cutoff = cutoff_hz / nyq
    if norm_cutoff >= 1:
        return data
    b, a = butter(N=4, Wn=norm_cutoff, btype='low', analog=False)
    if data.ndim == 1:
        return lfilter(b, a, data)
    else:
        return np.array([lfilter(b, a, channel) for channel in data.T]).T

def run_voicefixer(input_wav, output_wav, mode="2", disable_cuda=False, silent=False):
    if VoiceFixer is None:
        raise ImportError("VoiceFixer is not installed. Run `pip install voicefixer`.")
    if str(mode) not in ["0", "1", "2", "all"]:
        raise ValueError(f"VoiceFixer mode must be 0, 1, 2, or 'all', got: {mode}")
    print(f"Running VoiceFixer (mode={mode}, {'no GPU' if disable_cuda else 'GPU if available'}) on {input_wav}...")
    voicefixer = VoiceFixer()
    voicefixer.restore(
        input=input_wav,
        output=output_wav,
        mode=mode,
        cuda=not disable_cuda,
    )
    print(f"VoiceFixer output audio saved to: {output_wav}")

def hex_to_ass_bgr(hex_color):
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return "&H00FFFFFF&"
    r = hex_color[0:2]
    g = hex_color[2:4]
    b = hex_color[4:6]
    return f"&H00{b}{g}{r}&"

def main(input_video, background_audio, bypass_auto, edit_transcript,
         subtitle_font, font_size, marginv,
         threshold, margin,
         demucs_model, demucs_device, bgm_volume,
         max_sentences, max_words,
         nr_propdec, nr_stationary, nr_freqsmooth,
         lp_cutoff,
         use_demucs, use_noisereduce, use_lowpass, use_voicefixer,
         vf_mode, use_deepfilternet, use_pyrnnoise,
         primary_color_hex, highlight_color_hex,
         video_codec="hevc_nvenc", qp="30",
         outputs_folder=None, output_basename=None):
    extracted_wav = "extracted_audio.wav"
    processed_wav = extracted_wav
    step_outputs = {}

    denoised_wav = "demucs_denoised.wav"
    nr_wav = "nr_denoised.wav"
    vf_wav = "voicefixer_enhanced.wav"
    lp_wav = "lowpass_nr_denoised.wav"
    dfn_wav = "deepfilternet_denoised.wav"
    rnnoise_wav = "rnnoise_denoised.wav"
    output_video = "output_video_cleaned.mp4"
    final_video = "final_output_no_silence.mp4"
    final_with_music = "final_with_music.mp4"

    subprocess.run([
        "ffmpeg", "-y", "-i", input_video,
        "-vn", "-acodec", "pcm_s16le", "-ar", "48000", extracted_wav
    ], check=True)



    processed_wav = extracted_wav

    if use_demucs:
        run_demucs_denoise(processed_wav, denoised_wav, demucs_model=demucs_model, demucs_device=demucs_device)
        processed_wav = denoised_wav
        step_outputs['demucs'] = processed_wav

    if use_noisereduce:
        print(f"Running noisereduce on previous output...")
        data, rate = sf.read(processed_wav)
        if data.dtype != np.float32:
            data = data.astype(np.float32)
        prop_dec = max(0.01, min(float(nr_propdec), 1.0))
        freq_mask = int(nr_freqsmooth)
        try:
            data_nr = nr.reduce_noise(
                y=data,
                sr=rate,
                stationary=nr_stationary,
                prop_decrease=prop_dec,
                freq_mask_smooth_hz=freq_mask if freq_mask > 0 else None,
            )
        except Exception as e:
            print("⚠️ Noisereduce failed:", e)
            data_nr = data
        sf.write(nr_wav, data_nr, rate)
        processed_wav = nr_wav
        step_outputs['noisereduce'] = processed_wav

    if use_deepfilternet:
        try:
            run_deepfilternet(processed_wav, dfn_wav)
            processed_wav = dfn_wav
            step_outputs['deepfilternet'] = processed_wav
        except Exception as e:
            print("⚠️ DeepFilterNet failed or not installed:", e)

    if use_pyrnnoise:
        try:
            print("Running PYRNNOISE on audio")
            run_pyrnnoise(processed_wav, rnnoise_wav)
            processed_wav = rnnoise_wav
            step_outputs['pyrnnoise'] = processed_wav
        except Exception as e:
            print("⚠️ pyrnnoise failed or not installed:", e)

    if use_voicefixer:
        run_voicefixer(processed_wav, vf_wav, mode=vf_mode)
        processed_wav = vf_wav
        step_outputs['voicefixer'] = processed_wav

    if use_lowpass:
        print(f"Applying low-pass filter at {lp_cutoff} Hz...")
        data_lp, rate_lp = sf.read(processed_wav)
        if data_lp.dtype != np.float32:
            data_lp = data_lp.astype(np.float32)
        try:
            data_lp_filt = apply_lowpass_filter(data_lp, rate_lp, cutoff_hz=lp_cutoff)
        except Exception as e:
            print("⚠️ Low-pass filter failed:", e)
            data_lp_filt = data_lp
        sf.write(lp_wav, data_lp_filt, rate_lp)
        processed_wav = lp_wav
        step_outputs['lowpass'] = processed_wav

    print(f"Final processed audio for video is: {processed_wav}")

    framerate = get_framerate(input_video)
    video_codec = video_codec.strip() if video_codec else "hevc_nvenc"
    qp = str(qp).strip() if str(qp).strip().isdigit() else "30"
    try:
        qp_int = int(qp)
    except Exception:
        qp_int = 30
        qp = "30"

    subprocess.run([
        "ffmpeg", "-y",
        "-i", input_video,
        "-i", processed_wav,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", video_codec,
        "-rc", "constqp", "-qp", qp,
        "-r", str(framerate),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "320k",
        "-shortest",
        output_video
    ], check=True)

    if not bypass_auto:
        threshold_str = f"{threshold:.2f}"
        margin_str = f"{margin:.1f}s"
        subprocess.run([
            "auto-editor", output_video,
            "--edit", f"audio:threshold={threshold_str}", "--margin", margin_str,
            "-c:v", video_codec, "-b:v", "50M", "--no-open", "-b:a", "320k",
            "-o", final_video
        ], check=True)
        video_for_music = final_video
    else:
        video_for_music = output_video

    duration = get_video_duration(video_for_music)
    if duration is None or duration < 7:
        fade_start = max(0, duration - 2) if duration else 0
        fade_dur = min(2, duration) if duration else 2
    else:
        fade_start = duration - 5
        fade_dur = 5

    filter_complex = (
        f"[0:a]dynaudnorm=f=500:g=15:m=10:r=0.95[main];"
        f"[1:a]afade=t=out:st={fade_start:.2f}:d={fade_dur:.2f},dynaudnorm=f=500:g=15:m=10:r=0.95[pbg];"
        f"[main]asplit=2[maina][mainb];"
        f"[pbg]volume={bgm_volume:.2f}[bg];"
        f"[bg][maina]sidechaincompress=threshold=0.01:ratio=15:attack=1:release=20[compr];"
        f"[compr][mainb]amerge[mixout]"
    )

    result = subprocess.run([
        "ffmpeg", "-y",
        "-i", video_for_music,
        "-stream_loop", "-1", "-i", background_audio,
        "-filter_complex", filter_complex,
        "-map", "0:v:0",
        "-map", "[mixout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-ac", "2",
        final_with_music
    ], check=True, capture_output=True, text=True)
    print(result.stdout)
    print(result.stderr)

    video_path = final_video if not bypass_auto else output_video
    ass_path = "captions.ass"
    out_video = input_video + "Completed_" + dt + "_.mkv"
    txt_path = "transcript_edit.txt"

    print("Transcribing...")
    words = transcribe_video(video_path)
    if edit_transcript:
        write_words_txt(words, txt_path)
        open_and_edit_txt(txt_path)
        words = update_words_from_txt(words, txt_path)

    print("Generating ASS subtitles...")

    primary_color_ass = hex_to_ass_bgr(primary_color_hex)
    highlight_color_ass = hex_to_ass_bgr(highlight_color_hex)

    make_ass_subtitle_stable(words, ass_path, input_video,
                             fontsize=font_size, fontname=subtitle_font, marginv=marginv,
                             max_sentences=max_sentences, max_words=max_words,
                             primary_color=primary_color_ass,
                             highlight_color=highlight_color_ass)
    print("Burning captions into video...")
    burn_subtitles_ffmpeg(final_with_music, ass_path, out_video, video_codec, qp)
    print("Done! Output saved as:", out_video)

    output_file_path = out_video
    if outputs_folder is not None and output_basename is not None:
        ext = os.path.splitext(out_video)[-1]
        target_path = os.path.join(outputs_folder, output_basename + ext)
        try:
            os.rename(out_video, target_path)
            output_file_path = target_path
        except Exception:
            import shutil
            shutil.copy(out_video, target_path)
            output_file_path = target_path

    for f in [extracted_wav, denoised_wav, nr_wav, vf_wav, lp_wav, dfn_wav, rnnoise_wav, txt_path, ass_path]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass
    print("✅ All done. Final output with background music and ducking saved as:", output_file_path)
    return output_file_path

def transcribe_video(video_path, model_size="base"):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")
    model = load_model(model_size, device=device)
    results = transcribe(model, video_path, language="en", beam_size=25, vad=False, verbose=True, best_of=1, temperature=0.2)
    words = []
    for segment in results["segments"]:
        for word in segment["words"]:
            words.append({
                "start": word["start"],
                "end": word["end"],
                "word": word["text"],
            })
    return words

def make_ass_subtitle_stable(
    words, out_ass_path, input_video, highlight_color="&H00FFFF&", max_sentences=1, max_words=10,
    fontsize=36, fontname="Arial", marginv=75, primary_color="&H00FFFFFF&"
):
    width, height = get_video_resolution(input_video)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{fontname},{fontsize},{primary_color},&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,3,1,2,10,10,{marginv},1
Style: Highlight,{fontname},{fontsize},{highlight_color},&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,3,1,2,10,10,{marginv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = ""
    i = 0
    while i < len(words):
        current = words[i]
        line_words = [current["word"]]
        start = current["start"]
        end = current["end"]
        for j in range(i+1, min(i+max_words, len(words))):
            if len(line_words) < max_words:
                line_words.append(words[j]["word"])
                end = words[j]["end"]
            else:
                break
        highlighted = []
        for idx, w in enumerate(line_words):
            if idx == 0:
                highlighted.append(f"{{\\rHighlight}}{w}{{\\r}}")
            else:
                highlighted.append(w)
        text = " ".join(highlighted)
        start_ts = ass_time(start)
        end_ts = ass_time(end)
        events += f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{text}\n"
        i += len(line_words)
    with open(out_ass_path, "w", encoding="utf-8") as f:
        f.write(header + events)

def ass_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 100)
    return f"{h:d}:{m:02d}:{s:02d}.{ms:02d}"

def burn_subtitles_ffmpeg(input_video, ass_path, output_video, video_codec="hevc_nvenc", qp="30"):
    subprocess.run([
        "ffmpeg", "-y", "-i", input_video,
        "-vf", f"ass={ass_path}",
        "-c:v", video_codec,
        "-rc", "constqp", "-qp", qp,
        "-c:a", "copy",
        output_video
    ], check=True)

def save_gradio_file(fileobj, out_path):
    # If it's a file path string
    if isinstance(fileobj, str):
        import shutil
        shutil.copyfile(fileobj, out_path)
    # If it's a file-like object with read()
    elif hasattr(fileobj, "read"):
        # Try to reset to start if possible, but ignore if not supported
        try:
            fileobj.seek(0)
        except Exception:
            pass
        with open(out_path, "wb") as f:
            f.write(fileobj.read())
    else:
        raise Exception(f"Invalid file object type: {type(fileobj)}")


def gradio_main(
    input_video, background_audio, bypass_auto, edit_transcript,
    subtitle_font, font_size, marginv, threshold, margin,
    demucs_model, demucs_device, bgm_volume,
    max_sentences, max_words,
    nr_propdec, nr_stationary, nr_freqsmooth,
    lp_cutoff,
    use_demucs, use_noisereduce, use_lowpass, use_voicefixer,
    vf_mode, use_deepfilternet, use_pyrnnoise,
    primary_color_hex, highlight_color_hex,
    video_codec="hevc_nvenc", qp="30"
):
    outputs_folder = get_outputs_folder()
    base_name = f"Processed_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    input_video_path = os.path.join(outputs_folder, base_name + "_video" + (os.path.splitext(getattr(input_video, 'name', ''))[-1] or ".mp4"))
    background_audio_path = os.path.join(outputs_folder, base_name + "_bgm" + (os.path.splitext(getattr(background_audio, 'name', ''))[-1] or ".mp3"))
    save_gradio_file(input_video, input_video_path)
    save_gradio_file(background_audio, background_audio_path)
    output_file = main(
        input_video_path, background_audio_path, bypass_auto, edit_transcript,
        subtitle_font, int(font_size), int(marginv), float(threshold), float(margin),
        demucs_model, demucs_device, float(bgm_volume),
        int(max_sentences), int(max_words),
        float(nr_propdec), nr_stationary, int(nr_freqsmooth),
        int(lp_cutoff),
        use_demucs, use_noisereduce, use_lowpass, use_voicefixer,
        vf_mode, use_deepfilternet, use_pyrnnoise,
        primary_color_hex, highlight_color_hex,
        video_codec, qp,
        outputs_folder=outputs_folder,
        output_basename=base_name
    )
    return output_file

def launch_gradio():
    if not _GRADIO_AVAILABLE:
        print("Gradio is not installed. Run `pip install gradio`.")
        return
    with gr.Blocks() as demo:
        gr.Markdown("""
        # Word Light - auto caption word-highlighting with background music, noise removal and vocal enhancement

        [[View on GitHub](https://github.com/petermg/WordLight)]  [[Join Discord Server](https://discord.gg/PPgbApG)]  Made by Peter [@ OPEN PC Reviews](https://www.youtube.com/openpcreviews)
        """)
        with gr.Accordion("Download Completed Outputs", open=False):
            output_files = gr.Files(label=None, value=list_output_files())
            refresh_btn = gr.Button("Refresh Output File List")
            def refresh_outputs():
                return list_output_files()
            refresh_btn.click(fn=refresh_outputs, outputs=output_files)

        input_video = gr.File(label="Input Video (mp4/mkv/avi...)")
        background_audio = gr.File(label="Background Music (mp3/wav...)")
        bypass_auto = gr.Checkbox(label="Bypass Auto-Editor (skip silence removal)", value=False)
        edit_transcript = gr.Checkbox(label="Edit transcript before creating subtitles", value=False)
        subtitle_font = gr.Textbox(label="Subtitle Font", value="Arial")
        font_size = gr.Slider(18, 100, value=36, label="Font Size")
        marginv = gr.Slider(0, 400, value=75, label="Caption Vertical Margin")
        threshold = gr.Slider(0.01, 0.20, value=0.04, step=0.01, label="Auto-Editor Silence Threshold")
        margin = gr.Slider(0.1, 2.0, value=0.5, step=0.1, label="Auto-Editor Margin (seconds)")
        demucs_model = gr.Dropdown(choices=DEMUC_MODELS, value="htdemucs_ft", label="Demucs Model")
        demucs_device = gr.Dropdown(choices=["cuda", "cpu"], value="cuda", label="Demucs Device")
        bgm_volume = gr.Slider(0.0, 1.0, value=0.15, step=0.01, label="Background Music Volume")
        max_sentences = gr.Slider(1, 5, value=1, step=1, label="Max Sentences per Subtitle")
        max_words = gr.Slider(3, 25, value=5, step=1, label="Max Words per Subtitle")
        nr_propdec = gr.Slider(0.1, 1.0, value=0.75, step=0.01, label="Noisereduce prop_decrease")
        nr_stationary = gr.Checkbox(label="Noisereduce stationary", value=False)
        nr_freqsmooth = gr.Slider(0, 1000, value=500, step=1, label="Noisereduce freq_mask_smooth_hz")
        lp_cutoff = gr.Slider(100, 20000, value=8000, step=100, label="Low-Pass Filter Cutoff (Hz)")
        use_demucs = gr.Checkbox(label="Enable Demucs Denoising", value=True)
        use_noisereduce = gr.Checkbox(label="Enable Noisereduce", value=False)
        use_lowpass = gr.Checkbox(label="Enable Low-Pass Filter", value=False)
        use_voicefixer = gr.Checkbox(label="Enable VoiceFixer Enhancement", value=False)
        vf_mode = gr.Dropdown(choices=VOICEFIXER_MODES, value="2", label="VoiceFixer Mode")
        use_deepfilternet = gr.Checkbox(label="Enable DeepFilterNet Denoising", value=True)
        use_pyrnnoise = gr.Checkbox(label="Enable pyrnnoise Denoising", value=False)
        primary_color_hex = gr.ColorPicker(label="Subtitle Color", value="#FFFFFF")
        highlight_color_hex = gr.ColorPicker(label="Highlight (Spoken Word) Color", value="#FFFF00")
        video_codec = gr.Textbox(label="Video Codec (e.g. hevc_nvenc, h264_nvenc, libx264)", value="hevc_nvenc")
        qp = gr.Textbox(label="FFmpeg QP Value (e.g. 0, 23, 30, 40)", value="30")
        submit = gr.Button("Process Video")
        output_video = gr.File(label="Processed Video")
        submit.click(
            gradio_main,
            inputs=[input_video, background_audio, bypass_auto, edit_transcript, subtitle_font, font_size, marginv, threshold, margin,
                    demucs_model, demucs_device, bgm_volume, max_sentences, max_words, nr_propdec, nr_stationary, nr_freqsmooth,
                    lp_cutoff, use_demucs, use_noisereduce, use_lowpass, use_voicefixer, vf_mode, use_deepfilternet, use_pyrnnoise,
                    primary_color_hex, highlight_color_hex, video_codec, qp],
            outputs=output_video
        )
    demo.launch(server_name='0.0.0.0', share=True)

if __name__ == "__main__":
    mode = None
    if _GRADIO_AVAILABLE:
        print("Select launch mode:")
        print("1) Tkinter GUI (Desktop window, recommended for advanced control)")
        print("2) Gradio Web UI (Accessible from browser, easy to share on LAN)")
        try:
            mode = input("Enter 1 for Tkinter or 2 for Gradio [1/2]: ").strip()
        except Exception:
            mode = "1"
    else:
        mode = "1"

    if mode == "2" and _GRADIO_AVAILABLE:
        launch_gradio()
    else:
        try:
            (input_video, background_audio, bypass_auto, edit_transcript,
             subtitle_font, font_size, marginv, threshold, margin,
             demucs_model, demucs_device, bgm_volume,
             max_sentences, max_words,
             nr_propdec, nr_stationary, nr_freqsmooth,
             lp_cutoff,
             use_demucs, use_noisereduce, use_lowpass, use_voicefixer,
             vf_mode, use_deepfilternet, use_pyrnnoise,
             primary_color_hex, highlight_color_hex,
             video_codec, qp) = select_files_and_options()
            main(input_video, background_audio, bypass_auto, edit_transcript,
                 subtitle_font, font_size, marginv,
                 threshold, margin,
                 demucs_model, demucs_device, bgm_volume,
                 max_sentences, max_words,
                 nr_propdec, nr_stationary, nr_freqsmooth,
                 lp_cutoff,
                 use_demucs, use_noisereduce, use_lowpass, use_voicefixer,
                 vf_mode, use_deepfilternet, use_pyrnnoise,
                 primary_color_hex, highlight_color_hex,
                 video_codec, qp)
        except Exception as e:
            print("❌ Error:", e)
            input("Press Enter to exit.")
