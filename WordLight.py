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
from PIL import Image, ImageDraw, ImageFont
import io
import winreg
import traceback
import tempfile


def get_windows_font_map():
    font_dir = os.path.join(os.environ['WINDIR'], 'Fonts')
    font_map = {}
    try:
        reg = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
        key = winreg.OpenKey(reg, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
        for i in range(0, winreg.QueryInfoKey(key)[1]):
            name, fontfile, _ = winreg.EnumValue(key, i)
            # Clean up name, remove style
            clean_name = name.split(" (")[0].strip()
            font_path = fontfile
            if not os.path.isabs(fontfile):
                font_path = os.path.join(font_dir, fontfile)
            font_map[clean_name] = font_path
        winreg.CloseKey(key)
    except Exception as e:
        print("Font registry read error:", e)
    return font_map

font_name_to_path = get_windows_font_map()
FONT_CHOICES = sorted(font_name_to_path.keys())


def render_font_preview(fontname, fontsize, color="#000000"):
    PREVIEW_FONT_SIZE = 50  # Set your desired preview font size here
    PREVIEW_FONT_COLOR = "#FFFFFF"
    text = f"Preview: {fontname} {PREVIEW_FONT_SIZE}"
    font_path = get_font_path_by_name(fontname)
    warning = ""
    font_loaded = False
    ffmpeg_fallback_used = False

    # Dynamically determine required height
    try:
        if font_path:
            font = ImageFont.truetype(font_path, PREVIEW_FONT_SIZE)
        else:
            font = ImageFont.load_default()
        # Use textbbox (preferred), fallback to getsize
        if hasattr(font, "getbbox"):
            bbox = font.getbbox(text)
            text_height = bbox[3] - bbox[1]
        else:
            text_height = font.getsize(text)[1]
        img_height = text_height + 32  # add padding for descenders/ascenders
    except Exception:
        img_height = 70  # fallback
    img = Image.new("RGBA", (1200, img_height), (50, 50, 50, 255))
    draw = ImageDraw.Draw(img)
    try:
        if font_path:
            font = ImageFont.truetype(font_path, PREVIEW_FONT_SIZE)
            font_loaded = True
            print(f"[FontPreview] Loaded font at path: {font_path}")
        else:
            raise Exception("Font not found")
    except Exception as e:
        print(f"[FontPreview] WARNING: {e}\n{traceback.format_exc()}")
        # --- FFmpeg fallback starts here ---
        try:
            # Write a temporary ASS subtitle file
            with tempfile.TemporaryDirectory() as tmpdir:
                ass_path = os.path.join(tmpdir, "preview.ass")
                jpg_path = os.path.join(tmpdir, "preview.jpg")
                # Write a simple ASS with the requested font, color, and size
                color = PREVIEW_FONT_COLOR  # Override UI color with fixed preview color
                color_ass = "&H" + color[5:7] + color[3:5] + color[1:3] + "&" if color.startswith("#") and len(color) == 7 else "&H00FFFF&"
                with open(ass_path, "w", encoding="utf-8") as f:
                    f.write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: 700
PlayResY: 70

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{fontname},{PREVIEW_FONT_SIZE},{color_ass},0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:04.00,Default,,0,0,0,,{text}
""")
                # Use ffmpeg to render the preview
                # Fix ass_path for Windows: escape backslashes AND the colon
                # Use the SAME escaping logic as your working subtitle/preview generation!
                ass_path_escaped = ass_path.replace("\\", "\\\\").replace(":", "\\:")
                ass_filter = f"ass='{ass_path_escaped}'"

                ffmpeg_cmd = [
                    "ffmpeg", "-hide_banner", "-y", "-f", "lavfi", "-i", "color=s=1200x70:color=gray",
                    "-vf", ass_filter, "-frames:v", "1", jpg_path
                ]
                print(f"[FontPreview] FFmpeg fallback: {' '.join(ffmpeg_cmd)}")
                subprocess.run(ffmpeg_cmd, check=True)
                with Image.open(jpg_path) as im:
                    preview_img = im.copy()
                ffmpeg_fallback_used = True
                return preview_img
        except Exception as ff:
            print(f"[FontPreview] FFmpeg fallback failed: {ff}\n{traceback.format_exc()}")
            warning = "(Font preview not available. Video will use correct font.)"
        # --- End FFmpeg fallback ---

        font = ImageFont.load_default()
        warning = "(Font preview not available. Video will use correct font.)"
    # Draw a border for debug
    draw.rectangle([0, 0, img.width - 1, img.height - 1], outline=(0, 0, 0, 255), width=2)
    # Draw preview text
    try:
        # Center text both horizontally and vertically using the bounding box
        if hasattr(font, "getbbox"):
            bbox = font.getbbox(text)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = (img.width - text_width) // 2 - bbox[0]
            text_y = (img.height - text_height) // 2 - bbox[1]
        else:
            # fallback for older Pillow
            text_width, text_height = font.getsize(text)
            text_x = (img.width - text_width) // 2
            text_y = (img.height - text_height) // 2

        draw.text((text_x, text_y), text, font=font, fill=PREVIEW_FONT_COLOR)
    except Exception as e:
        print(f"[FontPreview] ERROR drawing text: {e}\n{traceback.format_exc()}")
        warning = "(Font drawing failed)"
    # Draw warning if needed
    if warning and not ffmpeg_fallback_used:
        draw.text((10, 48), warning, font=ImageFont.load_default(), fill="red")
    if font_loaded:
        print(f"[FontPreview] Drew preview for '{fontname}' size {fontsize} color {color}")
    return img



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
    messagebox.showinfo("Select Videos", "Select one or more input video files (e.g. .mp4)")
    video_files = filedialog.askopenfilenames(
        title="Select Input Videos",
        filetypes=[("Video Files", "*.mp4 *.mkv *.avi *.mov *.webm"), ("All Files", "*.*")]
    )
    if not video_files:
        raise Exception("No video file selected.")
    messagebox.showinfo("Select Music", "Select the background music file (e.g. .mp3)")
    music_file = filedialog.askopenfilename(
        title="Select Background Music",
        filetypes=[("Audio Files", "*.mp3 *.wav *.aac *.flac"), ("All Files", "*.*")]
    )
    if not music_file:
        raise Exception("No background music file selected.")
    root.destroy()

    # Additional UI for merge/concat option
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
    merge_videos_var = BooleanVar(value=True if len(video_files) > 1 else False)

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

    # --- ASS subtitle extra style variables ---
    secondary_color_var = StringVar(value="#FF0000")
    outline_color_var = StringVar(value="#000000")
    back_color_var = StringVar(value="#000000")
    def pick_secondary_color():
        color = colorchooser.askcolor(title="Select Secondary Color", initialcolor=secondary_color_var.get())
        if color[1]:
            secondary_color_var.set(color[1])

    def pick_outline_color():
        color = colorchooser.askcolor(title="Select Outline Color", initialcolor=outline_color_var.get())
        if color[1]:
            outline_color_var.set(color[1])

    def pick_back_color():
        color = colorchooser.askcolor(title="Select Back Color", initialcolor=back_color_var.get())
        if color[1]:
            back_color_var.set(color[1])

    # The button widgets get defined just below, so these will work
    def update_secondary_btn(*args):
        try: sec_btn.config(bg=secondary_color_var.get())
        except: pass
    def update_outline_btn(*args):
        try: out_btn.config(bg=outline_color_var.get())
        except: pass
    def update_back_btn(*args):
        try: back_btn.config(bg=back_color_var.get())
        except: pass

    secondary_color_var.trace_add("write", update_secondary_btn)
    outline_color_var.trace_add("write", update_outline_btn)
    back_color_var.trace_add("write", update_back_btn)    
    bold_var = IntVar(value=0)
    italic_var = IntVar(value=0)
    underline_var = IntVar(value=0)
    strikeout_var = IntVar(value=0)
    scale_x_var = IntVar(value=100)
    scale_y_var = IntVar(value=100)
    spacing_var = IntVar(value=0)
    angle_var = IntVar(value=0)
    border_style_var = IntVar(value=1)
    outline_var = IntVar(value=3)
    shadow_var = IntVar(value=1)
    alignment_var = IntVar(value=2)
    marginl_var = IntVar(value=10)
    marginr_var = IntVar(value=10)

    extra_style_frame = tk.LabelFrame(left_frame, text="Advanced Subtitle Style Options")
    extra_style_frame.pack(anchor="w", fill="x", pady=(12,8))

    # Secondary Color Picker
    tk.Label(extra_style_frame, text="Secondary Color:").grid(row=0, column=0, sticky="w")
    sec_btn = tk.Button(extra_style_frame, text="Pick...", command=pick_secondary_color, bg=secondary_color_var.get(), width=8)
    sec_btn.grid(row=0, column=1)
    tk.Label(extra_style_frame, textvariable=secondary_color_var, width=10, relief="groove", anchor="w").grid(row=0, column=2, sticky="w")

    # Outline Color Picker
    tk.Label(extra_style_frame, text="Outline Color:").grid(row=1, column=0, sticky="w")
    out_btn = tk.Button(extra_style_frame, text="Pick...", command=pick_outline_color, bg=outline_color_var.get(), width=8)
    out_btn.grid(row=1, column=1)
    tk.Label(extra_style_frame, textvariable=outline_color_var, width=10, relief="groove", anchor="w").grid(row=1, column=2, sticky="w")

    # Back Color Picker
    tk.Label(extra_style_frame, text="Back Color:").grid(row=2, column=0, sticky="w")
    back_btn = tk.Button(extra_style_frame, text="Pick...", command=pick_back_color, bg=back_color_var.get(), width=8)
    back_btn.grid(row=2, column=1)
    tk.Label(extra_style_frame, textvariable=back_color_var, width=10, relief="groove", anchor="w").grid(row=2, column=2, sticky="w")

    tk.Label(extra_style_frame, text="Bold:").grid(row=0, column=2, sticky="w")
    tk.Checkbutton(extra_style_frame, variable=bold_var).grid(row=0, column=3)
    tk.Label(extra_style_frame, text="Italic:").grid(row=1, column=2, sticky="w")
    tk.Checkbutton(extra_style_frame, variable=italic_var).grid(row=1, column=3)
    tk.Label(extra_style_frame, text="Underline:").grid(row=2, column=2, sticky="w")
    tk.Checkbutton(extra_style_frame, variable=underline_var).grid(row=2, column=3)
    tk.Label(extra_style_frame, text="Strikeout:").grid(row=3, column=2, sticky="w")
    tk.Checkbutton(extra_style_frame, variable=strikeout_var).grid(row=3, column=3)

    tk.Label(extra_style_frame, text="Scale X:").grid(row=3, column=0, sticky="w")
    tk.Entry(extra_style_frame, textvariable=scale_x_var, width=6).grid(row=3, column=1)
    tk.Label(extra_style_frame, text="Scale Y:").grid(row=4, column=0, sticky="w")
    tk.Entry(extra_style_frame, textvariable=scale_y_var, width=6).grid(row=4, column=1)
    tk.Label(extra_style_frame, text="Spacing:").grid(row=5, column=0, sticky="w")
    tk.Entry(extra_style_frame, textvariable=spacing_var, width=6).grid(row=5, column=1)
    tk.Label(extra_style_frame, text="Angle:").grid(row=6, column=0, sticky="w")
    tk.Entry(extra_style_frame, textvariable=angle_var, width=6).grid(row=6, column=1)
    tk.Label(extra_style_frame, text="BorderStyle:").grid(row=7, column=0, sticky="w")
    tk.Entry(extra_style_frame, textvariable=border_style_var, width=6).grid(row=7, column=1)
    tk.Label(extra_style_frame, text="Outline:").grid(row=8, column=0, sticky="w")
    tk.Entry(extra_style_frame, textvariable=outline_var, width=6).grid(row=8, column=1)
    tk.Label(extra_style_frame, text="Shadow:").grid(row=9, column=0, sticky="w")
    tk.Entry(extra_style_frame, textvariable=shadow_var, width=6).grid(row=9, column=1)
    tk.Label(extra_style_frame, text="Alignment:").grid(row=10, column=0, sticky="w")
    tk.Entry(extra_style_frame, textvariable=alignment_var, width=6).grid(row=10, column=1)
    tk.Label(extra_style_frame, text="MarginL:").grid(row=11, column=0, sticky="w")
    tk.Entry(extra_style_frame, textvariable=marginl_var, width=6).grid(row=11, column=1)
    tk.Label(extra_style_frame, text="MarginR:").grid(row=12, column=0, sticky="w")
    tk.Entry(extra_style_frame, textvariable=marginr_var, width=6).grid(row=12, column=1)


    # --- Preview Caption Button ---
    def show_tkinter_caption_preview():
        # Use the first selected video as the frame source
        video_path = video_files[0]
        duration = get_video_duration(video_path)
        preview_time = 0 if not duration or duration < 2 else min(duration * 0.5, duration - 0.2)

        outputs_dir = get_outputs_folder()
        preview_img_path = os.path.join(outputs_dir, "tk_ffmpeg_preview.jpg")
        preview_ass_path = os.path.join(outputs_dir, "tk_preview_caption.ass")

        # Generate preview caption .ass file using the same style as your video
        width, height = get_video_resolution(video_path)
        fontname = font_var.get()
        fontsize = int(font_size_var.get())
        marginv = int(marginv_var.get())
        color = primary_color_var.get() or "#FFFFFF"
        highlight_color = highlight_color_var.get() or "#FFFF00"
        primary_color_ass = hex_to_ass_bgr(color)
        highlight_color_ass = hex_to_ass_bgr(highlight_color)

        # Use a minimal sample with highlight
        words = [
            {'start': 0.0, 'end': 2.0, 'word': 'This'},
            {'start': 2.0, 'end': 3.0, 'word': 'is'},
            {'start': 3.0, 'end': 4.0, 'word': 'a'},
            {'start': 4.0, 'end': 6.0, 'word': 'preview!'},
        ]
        make_ass_subtitle_stable(
            words, preview_ass_path, video_path,
            fontsize=fontsize, fontname=fontname, marginv=marginv,
            max_sentences=1, max_words=10,
            primary_color=primary_color_ass,
            highlight_color=highlight_color_ass,
            secondary_color=hex_to_ass_bgr(secondary_color_var.get()),
            outline_color=hex_to_ass_bgr(outline_color_var.get()),
            back_color=hex_to_ass_bgr(back_color_var.get()),
            bold=bold_var.get(), italic=italic_var.get(), underline=underline_var.get(), strikeout=strikeout_var.get(),
            scale_x=scale_x_var.get(), scale_y=scale_y_var.get(), spacing=spacing_var.get(), angle=angle_var.get(),
            border_style=border_style_var.get(), outline=outline_var.get(), shadow=shadow_var.get(), alignment=alignment_var.get(),
            marginl=marginl_var.get(), marginr=marginr_var.get()
        )

        # Burn the .ass onto a single frame, using the **exact same logic as video**
        # NO path escaping, NO quotes, just the plain path
        ass_path = os.path.abspath(preview_ass_path)
        # Escape for ffmpeg ASS filter on Windows:
        ass_path_escaped = ass_path.replace("\\", "\\\\").replace(":", "\\:")
        ass_filter = f"ass='{ass_path_escaped}'"

        print("ASS path for ffmpeg:", ass_path_escaped)
        print("Does .ass file exist?", os.path.exists(ass_path), ass_path_escaped)

        cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(preview_time),
            "-i", video_path,
            "-frames:v", "1",
            "-vf", ass_filter,
            preview_img_path
        ]
        print("Running ffmpeg preview command:", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 or not os.path.exists(preview_img_path):
            print("FFmpeg preview failed:", result.stderr)
            tk.messagebox.showerror("Preview Error", f"Could not generate preview image with ffmpeg.\n\nFFmpeg error:\n{result.stderr}")
            return

        # Display image in a popup
        preview_window = tk.Toplevel(opt_root)
        preview_window.title("Caption Style Preview")
        from PIL import Image, ImageTk
        img = Image.open(preview_img_path)
        preview_img = ImageTk.PhotoImage(img)
        img_label = tk.Label(preview_window, image=preview_img)
        img_label.image = preview_img  # keep reference
        img_label.pack()
        preview_window.grab_set()

    preview_btn = tk.Button(left_frame, text="Preview Caption Style", command=show_tkinter_caption_preview)
    preview_btn.pack(anchor="w", pady=(4, 12))


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



    # Subtitle Color Row
    color_row = tk.Frame(left_frame)
    tk.Label(color_row, text="Subtitle Color:").pack(side="left", padx=4)
    primary_btn = tk.Button(color_row, text="Pick...", command=pick_primary_color, bg=primary_color_var.get(), width=8)
    primary_btn.pack(side="left")
    tk.Label(color_row, textvariable=primary_color_var, width=10, relief="groove", anchor="w").pack(side="left", padx=(4, 0))
    color_row.pack(anchor="w", pady=(10, 0))

    # Highlight Color Row
    color_row2 = tk.Frame(left_frame)
    tk.Label(color_row2, text="Highlight (Spoken Word) Color:").pack(side="left", padx=4)
    highlight_btn = tk.Button(color_row2, text="Pick...", command=pick_highlight_color, bg=highlight_color_var.get(), width=8)
    highlight_btn.pack(side="left")
    tk.Label(color_row2, textvariable=highlight_color_var, width=10, relief="groove", anchor="w").pack(side="left", padx=(4, 0))
    color_row2.pack(anchor="w", pady=(0, 10))

    def update_primary_btn(*args):
        try: primary_btn.config(bg=primary_color_var.get())
        except: pass

    def update_highlight_btn(*args):
        try: highlight_btn.config(bg=highlight_color_var.get())
        except: pass

    primary_color_var.trace_add("write", update_primary_btn)
    highlight_color_var.trace_add("write", update_highlight_btn)

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
    update_font_preview()

    font_size_label = tk.Label(left_frame, text="Font Size (px):")
    font_size_label.pack(anchor="w", pady=(0, 2))
    font_size_slider = tk.Scale(left_frame, from_=18, to=200, orient="horizontal", variable=font_size_var)
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

    # ---- NEW: Merge videos option ----
    Checkbutton(left_frame, text="Merge/Concatenate selected videos into one", variable=merge_videos_var).pack(anchor="w", pady=(0, 8))

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


    return (video_files, music_file, bypass_auto_var.get(), edit_transcript_var.get(),
            font_var.get(), font_size_var.get(), marginv_var.get(),
            threshold_var.get(), margin_var.get(),
            demucs_model_var.get(), demucs_device_var.get(), bgm_volume_var.get(),
            max_sentences_var.get(), max_words_var.get(),
            nr_propdec_var.get(), nr_stationary_var.get(), nr_freqsmooth_var.get(),
            lp_cutoff_var.get(),
            use_demucs_var.get(), use_noisereduce_var.get(), use_lowpass_var.get(), use_voicefixer_var.get(),
            vf_mode_var.get(), use_deepfilternet_var.get(), use_pyrnnoise_var.get(),
            primary_color_var.get(), highlight_color_var.get(),
            video_codec_var.get(), qp_var.get(), merge_videos_var.get(),
            secondary_color_var.get(), outline_color_var.get(), back_color_var.get(),
            bold_var.get(), italic_var.get(), underline_var.get(), strikeout_var.get(),
            scale_x_var.get(), scale_y_var.get(), spacing_var.get(), angle_var.get(),
            border_style_var.get(), outline_var.get(), shadow_var.get(), alignment_var.get(),
            marginl_var.get(), marginr_var.get())


def merge_videos_ffmpeg(video_files, merged_filename):
    # Use concat demuxer for robust merge
    with open("inputs_to_concat.txt", "w", encoding="utf-8") as f:
        for vf in video_files:
            f.write(f"file '{os.path.abspath(vf)}'\n")
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", "inputs_to_concat.txt",
        "-c", "copy",
        merged_filename
    ]
    print("Merging videos:", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True)
    finally:
        if os.path.exists("inputs_to_concat.txt"):
            os.remove("inputs_to_concat.txt")

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

def run_deepfilternet(input_wav, output_wav, chunk_duration=300, batch_size=1):
    if not _DFN_AVAILABLE:
        print("DeepFilterNet not available.")
        return
    print("Running DeepFilterNet with chunking on CPU...")
    model, df_state, _ = df_init()
    model = model  # Force CPU
    audio, _ = df_load_audio(input_wav, sr=df_state.sr())  # audio is already a Tensor

    # Ensure audio is contiguous and on CPU
    audio = audio.contiguous()

    # Calculate chunk size in samples
    chunk_samples = int(chunk_duration * df_state.sr())
    audio_length = audio.shape[-1]
    enhanced_chunks = []

    for start in range(0, audio_length, chunk_samples):
        end = min(start + chunk_samples, audio_length)
        chunk = audio[:, start:end].contiguous()  # Ensure chunk is contiguous
        if chunk.dim() == 1:
            chunk = chunk.unsqueeze(0)  # Add channel dimension if needed

        print(f"Processing chunk: {start//df_state.sr()} to {end//df_state.sr()} seconds")
        with torch.no_grad():
            if hasattr(model, "reset_h0"):
                model.reset_h0(batch_size=batch_size, device="cpu")
            enhanced_chunk = df_enhance(model, df_state, chunk, pad=True)
        enhanced_chunks.append(enhanced_chunk.cpu())

    # Concatenate chunks
    enhanced = torch.cat(enhanced_chunks, dim=-1)

    # Save output
    df_save_audio(output_wav, enhanced, df_state.sr())
    print(f"Saved: {output_wav}")

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
    print(f"hex_to_ass_bgr input: {hex_color}")
    # Handle RGBA tuple from Gradio
    if isinstance(hex_color, str) and hex_color.startswith("rgba("):
        try:
            # Extract RGBA values (e.g., "rgba(0, 206.53213524215656, 255, 1)" -> [0, 206.53213524215656, 255, 1])
            rgba = [float(x) for x in hex_color[5:-1].split(",")]
            # Convert to integers (0-255) and clamp non-integer values
            r, g, b = [max(0, min(255, int(round(x)))) for x in rgba[:3]]
            # Convert to 6-digit hex
            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            print(f"Converted RGBA to hex: {hex_color}")
        except Exception as e:
            print(f"Error converting RGBA to hex: {e}")
            return "&H00FFFFFF&"
    # Only proceed if string type
    if not isinstance(hex_color, str):
        print(f"Invalid type for hex_color: {type(hex_color)}. Returning white.")
        return "&H00FFFFFF&"
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        print(f"Invalid hex length after processing: {hex_color}")
        return "&H00FFFFFF&"
    r = hex_color[0:2]
    g = hex_color[2:4]
    b = hex_color[4:6]
    result = f"&H00{b}{g}{r}&"
    print(f"hex_to_ass_bgr output: {result}")
    return result

def main(
    input_video, background_audio, bypass_auto, edit_transcript,
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
    outputs_folder=None, output_basename=None,
    secondary_color="#FF0000", outline_color="#000000", back_color="#000000",
    bold=0, italic=0, underline=0, strikeout=0,
    scale_x=100, scale_y=100, spacing=0, angle=0,
    border_style=1, outline=3, shadow=1, alignment=2,
    marginl=10, marginr=10):

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

    if use_deepfilternet:
        try:
            run_deepfilternet(processed_wav, dfn_wav)
            processed_wav = dfn_wav
            step_outputs['deepfilternet'] = processed_wav
        except Exception as e:
            print("⚠️ DeepFilterNet failed or not installed:", e)

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
    if not words:
        print("⚠️ Transcription failed: No words detected.")
        return

    if edit_transcript:
        write_words_txt(words, txt_path)
        open_and_edit_txt(txt_path)
        words = update_words_from_txt(words, txt_path)
        if not words:
            print("⚠️ Transcript editing failed: No words after editing.")
            return

    print("Generating ASS subtitles...")
    print(f"Main highlight_color_hex: {highlight_color_hex}")
    primary_color_ass = hex_to_ass_bgr(primary_color_hex)
    highlight_color_ass = hex_to_ass_bgr(highlight_color_hex)
    print(f"Main highlight_color_ass: {highlight_color_ass}")

    make_ass_subtitle_stable(
        words, ass_path, input_video,
        fontsize=font_size, fontname=subtitle_font, marginv=marginv,
        max_sentences=max_sentences, max_words=max_words,
        primary_color=primary_color_ass,
        highlight_color=highlight_color_ass,
        secondary_color=hex_to_ass_bgr(secondary_color),
        outline_color=hex_to_ass_bgr(outline_color),
        back_color=hex_to_ass_bgr(back_color),
        bold=int(bold), italic=int(italic), underline=int(underline), strikeout=int(strikeout),
        scale_x=int(scale_x), scale_y=int(scale_y), spacing=int(spacing), angle=int(angle),
        border_style=int(border_style), outline=int(outline), shadow=int(shadow), alignment=int(alignment),
        marginl=int(marginl), marginr=int(marginr)
    )

    if not os.path.exists(ass_path):
        print(f"⚠️ Subtitle file not generated: {ass_path}")
        return

    print("Burning captions into video...")
    try:
        burn_subtitles_ffmpeg(final_with_music, ass_path, out_video, video_codec, qp)
        if not os.path.exists(out_video):
            print(f"⚠️ Subtitle burning failed: Output video {out_video} not created.")
            return
    except subprocess.CalledProcessError as e:
        print(f"⚠️ FFmpeg subtitle burning failed: {e}")
        return

    print("Done! Output saved as:", out_video)

    output_file_path = out_video
    if outputs_folder is not None and output_basename is not None:
        ext = os.path.splitext(out_video)[-1]
        target_path = os.path.join(outputs_folder, output_basename + ext)
        try:
            os.rename(out_video, target_path)
            output_file_path = target_path
        except Exception as e:
            print(f"⚠️ Failed to rename output file to {target_path}: {e}")
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
    results = transcribe(model, video_path, language="en", beam_size=25, vad=False, verbose=True, best_of=1, temperature=0)
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
    words, out_ass_path, input_video,
    highlight_color="&H00FFFF&", max_sentences=1, max_words=10,
    fontsize=36, fontname="Arial", marginv=75, primary_color="&H00FFFFFF&",
    secondary_color="&H000000FF&", outline_color="&H00000000&", back_color="&H00000000&",
    bold=0, italic=0, underline=0, strikeout=0,
    scale_x=100, scale_y=100, spacing=0, angle=0,
    border_style=1, outline=3, shadow=1, alignment=2,
    marginl=10, marginr=10,
):
    print(f"ASS highlight_color: {highlight_color}")
    width, height = get_video_resolution(input_video)
    header = f"""[Script Info]
    ScriptType: v4.00+
    PlayResX: {width}
    PlayResY: {height}

    [V4+ Styles]
    Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
    Style: Default,{fontname},{fontsize},{primary_color},{secondary_color},{outline_color},{back_color},{bold},{italic},{underline},{strikeout},{scale_x},{scale_y},{spacing},{angle},{border_style},{outline},{shadow},{alignment},{marginl},{marginr},{marginv},1
    Style: Highlight,{fontname},{fontsize},{highlight_color},{secondary_color},{outline_color},{back_color},{bold},{italic},{underline},{strikeout},{scale_x},{scale_y},{spacing},{angle},{border_style},{outline},{shadow},{alignment},{marginl},{marginr},{marginv},1

    [Events]
    Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
    """
    events = ""
    segments = []
    cur_segment = []
    sentence_count = 0
    word_count = 0
    last_end = 0
    max_gap = 1.5

    sentence_enders = re.compile(r'[\.\?\!]+$')

    for i, w in enumerate(words):
        cur_segment.append(w)
        word_count += 1
        if sentence_enders.search(w['word']):
            sentence_count += 1
        end_segment = False
        if (sentence_count >= max_sentences) or (word_count >= max_words):
            end_segment = True
        elif i < len(words)-1 and words[i+1]['start'] - w['end'] > max_gap:
            end_segment = True
        if end_segment or i == len(words)-1:
            segments.append(cur_segment)
            cur_segment = []
            sentence_count = 0
            word_count = 0

    for seg in segments:
        seg_start = seg[0]['start']
        seg_end = seg[-1]['end']
        seg_text = " ".join(w['word'] for w in seg)
        times = []
        prev_end = seg_start
        for w in seg:
            if prev_end < w['start']:
                times.append((prev_end, w['start']))
            prev_end = w['end']
        if prev_end < seg_end:
            times.append((prev_end, seg_end))
        for (t0, t1) in times:
            if t1 - t0 > 0.02:
                events += f"Dialogue: 0,{format_time(t0)},{format_time(t1)},Default,,0,0,0,," + seg_text + "\n"
        for i, w in enumerate(seg):
            text = ""
            for j, ww in enumerate(seg):
                if j == i:
                    text += r"{\rHighlight}" + ww['word'] + r"{\r}"
                else:
                    text += ww['word']
                if j != len(seg)-1:
                    text += " "
            events += f"Dialogue: 0,{format_time(w['start'])},{format_time(w['end'])},Default,,0,0,0,," + text + "\n"

    with open(out_ass_path, "w", encoding="utf-8") as f:
        f.write(header + events)

def format_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"

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
    input_videos, background_audio, bypass_auto, edit_transcript,
    subtitle_font, font_size, marginv, threshold, margin,
    demucs_model, demucs_device, bgm_volume,
    max_sentences, max_words,
    nr_propdec, nr_stationary, nr_freqsmooth,
    lp_cutoff,
    use_demucs, use_noisereduce, use_lowpass, use_voicefixer,
    vf_mode, use_deepfilternet, use_pyrnnoise,
    primary_color_hex, highlight_color_hex,
    video_codec="hevc_nvenc", qp="30", merge_videos=True,
    secondary_color_hex="#FF0000", outline_color_hex="#000000", back_color_hex="#000000",
    bold=False, italic=False, underline=False, strikeout=False,
    scale_x=100, scale_y=100, spacing=0, angle=0,
    border_style=1, outline=3, shadow=1, alignment=2,
    marginl=10, marginr=10
):
    print(f"Gradio highlight_color_hex: {highlight_color_hex}")
    outputs_folder = get_outputs_folder()
    base_name = f"Processed_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    # Accepts single or multiple files from gradio
    if isinstance(input_videos, list):
        video_paths = []
        for idx, vid in enumerate(input_videos):
            out_path = os.path.join(outputs_folder, f"{base_name}_video{idx}" + (os.path.splitext(getattr(vid, 'name', ''))[-1] or ".mp4"))
            save_gradio_file(vid, out_path)
            video_paths.append(out_path)
    else:
        # Just one file
        out_path = os.path.join(outputs_folder, base_name + "_video" + (os.path.splitext(getattr(input_videos, 'name', ''))[-1] or ".mp4"))
        save_gradio_file(input_videos, out_path)
        video_paths = [out_path]

    background_audio_path = os.path.join(outputs_folder, base_name + "_bgm" + (os.path.splitext(getattr(background_audio, 'name', ''))[-1] or ".mp3"))
    save_gradio_file(background_audio, background_audio_path)

    # Merge if selected
    if merge_videos and len(video_paths) > 1:
        merged_path = os.path.join(outputs_folder, base_name + "_merged.mp4")
        merge_videos_ffmpeg(video_paths, merged_path)
        video_input_for_main = merged_path
    else:
        video_input_for_main = video_paths[0]

    output_file = main(
        video_input_for_main, background_audio_path, bypass_auto, edit_transcript,
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
        output_basename=base_name,
        secondary_color=secondary_color_hex,
        outline_color=outline_color_hex,
        back_color=back_color_hex,
        bold=int(bold), italic=int(italic), underline=int(underline), strikeout=int(strikeout),
        scale_x=int(scale_x), scale_y=int(scale_y), spacing=int(spacing), angle=int(angle),
        border_style=int(border_style), outline=int(outline), shadow=int(shadow), alignment=int(alignment),
        marginl=int(marginl), marginr=int(marginr)
    )
    return output_file

def extract_frame(video_path, time=10, out_path="preview_frame.jpg"):
    cmd = [
        "ffmpeg", "-y", "-ss", str(time), "-i", video_path,
        "-frames:v", "1", "-q:v", "2", out_path
    ]
    print("Extracting frame with:", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not os.path.exists(out_path):
        print("FFmpeg frame extraction failed or wrote no file:", result.stderr)
    return out_path


def get_font_path_by_name(font_name):
    # Try direct match first (Windows font registry)
    if font_name in font_name_to_path:
        return font_name_to_path[font_name]
    # Try case-insensitive fuzzy match
    for name in font_name_to_path:
        if font_name.lower() == name.lower():
            return font_name_to_path[name]
    for name in font_name_to_path:
        if font_name.lower() in name.lower():
            return font_name_to_path[name]
    return None


def gradio_color_to_hex(color):
    """Converts a Gradio ColorPicker value (hex or rgba(...)) to #RRGGBB hex for Pillow."""
    if isinstance(color, str) and color.startswith("rgba("):
        try:
            rgba = [float(x.strip()) for x in color[5:-1].split(",")]
            r, g, b = [max(0, min(255, int(round(x)))) for x in rgba[:3]]
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception as e:
            print(f"Color conversion error: {e}")
            return "#ffffff"
    if isinstance(color, str) and color.startswith("#") and len(color) == 7:
        return color
    # Fallback
    return "#ffffff"


def render_caption_on_image(image_path, caption, fontname, fontsize, color, highlight_color, marginv, highlight_word=None):
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    font_path = get_font_path_by_name(fontname)
    if not font_path:
        font = ImageFont.truetype("arial.ttf", fontsize)
    else:
        font = ImageFont.truetype(font_path, fontsize)
    # --- Convert Gradio color picker values to #RRGGBB hex for Pillow ---
    color = gradio_color_to_hex(color)
    highlight_color = gradio_color_to_hex(highlight_color)
    # Text position: bottom, centered, with vertical margin
    W, H = img.size
    try:
        bbox = draw.textbbox((0, 0), caption, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    except AttributeError:
        # Fallback for older Pillow
        try:
            text_bbox = font.getbbox(caption)
            text_w = text_bbox[2] - text_bbox[0]
            text_h = text_bbox[3] - text_bbox[1]
        except AttributeError:
            text_w, text_h = font.getsize(caption)
    x = (W - text_w) // 2
    y = H - text_h - int(marginv)
    # Highlight logic
    if highlight_word and highlight_word in caption:
        parts = caption.split(highlight_word)
        x_cursor = x
        for part in parts[:-1]:
            # Get width for part
            try:
                part_bbox = font.getbbox(part)
                part_w = part_bbox[2] - part_bbox[0]
            except AttributeError:
                part_w = font.getsize(part)[0]
            draw.text((x_cursor, y), part, font=font, fill=color)
            x_cursor += part_w
            # Highlighted word box
            try:
                hw_bbox = font.getbbox(highlight_word)
                hw_w = hw_bbox[2] - hw_bbox[0]
                hw_h = hw_bbox[3] - hw_bbox[1]
            except AttributeError:
                hw_w, hw_h = font.getsize(highlight_word)
            draw.text((x_cursor, y), highlight_word, font=font, fill=highlight_color)
            x_cursor += hw_w
        draw.text((x_cursor, y), parts[-1], font=font, fill=color)
    else:
        draw.text((x, y), caption, font=font, fill=color)
    return img


def preview_caption_gradio(
    input_videos, subtitle_font, font_size, primary_color_hex, highlight_color_hex, marginv,
    secondary_color_hex="#FF0000", outline_color_hex="#000000", back_color_hex="#000000",
    bold=False, italic=False, underline=False, strikeout=False,
    scale_x=100, scale_y=100, spacing=0, angle=0,
    border_style=1, outline=3, shadow=1, alignment=2,
    marginl=10, marginr=10
):
    # Select the video path exactly as before
    if isinstance(input_videos, list) and len(input_videos) > 0:
        video_path = input_videos[0].name if hasattr(input_videos[0], "name") else input_videos[0]
    elif hasattr(input_videos, "name"):
        video_path = input_videos.name
    else:
        video_path = input_videos
    if not os.path.exists(video_path):
        return None

    # Pick the preview frame the same way as Tkinter (middle or zero)
    duration = get_video_duration(video_path)
    preview_time = 0 if not duration or duration < 2 else min(duration * 0.5, duration - 0.2)

    outputs_dir = get_outputs_folder()
    preview_img_path = os.path.join(outputs_dir, "gradio_ffmpeg_preview.jpg")
    preview_ass_path = os.path.join(outputs_dir, "gradio_preview_caption.ass")

    # Generate preview .ass using the same logic as video
    width, height = get_video_resolution(video_path)
    preview_caption = "This is a preview caption!"
    words = [
        {'start': 0.0, 'end': 2.0, 'word': 'This'},
        {'start': 2.0, 'end': 3.0, 'word': 'is'},
        {'start': 3.0, 'end': 4.0, 'word': 'a'},
        {'start': 4.0, 'end': 6.0, 'word': 'preview!'},
    ]
    # Convert color values to ASS BGR
    primary_color_ass = hex_to_ass_bgr(primary_color_hex)
    highlight_color_ass = hex_to_ass_bgr(highlight_color_hex)

    make_ass_subtitle_stable(
        words, preview_ass_path, video_path,
        fontsize=int(font_size), fontname=subtitle_font, marginv=int(marginv),
        max_sentences=1, max_words=10,
        primary_color=primary_color_ass,
        highlight_color=highlight_color_ass,
        secondary_color=hex_to_ass_bgr(secondary_color_hex),
        outline_color=hex_to_ass_bgr(outline_color_hex),
        back_color=hex_to_ass_bgr(back_color_hex),
        bold=int(bold), italic=int(italic), underline=int(underline), strikeout=int(strikeout),
        scale_x=int(scale_x), scale_y=int(scale_y), spacing=int(spacing), angle=int(angle),
        border_style=int(border_style), outline=int(outline), shadow=int(shadow), alignment=int(alignment),
        marginl=int(marginl), marginr=int(marginr)
    )

    # Use FFmpeg with ASS (with correct Windows escaping)
    ass_path = os.path.abspath(preview_ass_path)
    ass_path_escaped = ass_path.replace("\\", "\\\\").replace(":", "\\:")
    ass_filter = f"ass='{ass_path_escaped}'"

    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(preview_time),
        "-i", video_path,
        "-frames:v", "1",
        "-vf", ass_filter,
        preview_img_path
    ]
    print("Running ffmpeg for Gradio preview:", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not os.path.exists(preview_img_path):
        print("FFmpeg preview failed:", result.stderr)
        return None

    return preview_img_path

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

        input_videos = gr.Files(label="Input Video(s) (mp4/mkv/avi...)", file_count="multiple")
        background_audio = gr.File(label="Background Music (mp3/wav...)")
        try:
            from tkinter import font as tkfont
            import tkinter as tk
            def get_system_fonts():
                root = tk.Tk()
                root.withdraw()
                fonts = sorted(set(tkfont.families()))
                root.destroy()
                return fonts
        except Exception:
            from matplotlib import font_manager
            def get_system_fonts():
                font_list = font_manager.findSystemFonts(fontpaths=None, fontext='ttf')
                font_names = set()
                for fpath in font_list:
                    try:
                        font_prop = font_manager.FontProperties(fname=fpath)
                        name = font_prop.get_name()
                        if name:
                            font_names.add(name)
                    except Exception:
                        pass
                return sorted(font_names)


        font_preview_img = gr.Image(label="Font Preview", type="pil")
        def update_font_preview(font, PREVIEW_FONT_SIZE, PREVIEW_FONT_COLOR):
            return render_font_preview(font, PREVIEW_FONT_SIZE, PREVIEW_FONT_COLOR)



        FONT_CHOICES = get_system_fonts()
        subtitle_font = gr.Dropdown(
            choices=FONT_CHOICES,
            value="Arial" if "Arial" in FONT_CHOICES else (FONT_CHOICES[0] if FONT_CHOICES else ""),
            label="Subtitle Font"
        )
#        font_size.change(update_font_preview, [subtitle_font, font_size, primary_color_hex], font_preview_img)        
        with gr.Accordion("Denoise Options", open=False):
            use_demucs = gr.Checkbox(label="Enable Demucs Denoising", value=False)
            demucs_model = gr.Dropdown(choices=DEMUC_MODELS, value="htdemucs_ft", label="Demucs Model")
            demucs_device = gr.Dropdown(choices=["cuda", "cpu"], value="cuda", label="Demucs Device")      
            use_noisereduce = gr.Checkbox(label="Enable Noisereduce", value=False)
            nr_stationary = gr.Checkbox(label="Noisereduce stationary", value=False)
            nr_propdec = gr.Slider(0.1, 1.0, value=0.75, step=0.01, label="Noisereduce prop_decrease")
            nr_freqsmooth = gr.Slider(0, 1000, value=500, step=1, label="Noisereduce freq_mask_smooth_hz")
            use_lowpass = gr.Checkbox(label="Enable Low-Pass Filter", value=False)
            lp_cutoff = gr.Slider(100, 20000, value=8000, step=100, label="Low-Pass Filter Cutoff (Hz)")
            use_voicefixer = gr.Checkbox(label="Enable VoiceFixer Enhancement", value=False)
            vf_mode = gr.Dropdown(choices=VOICEFIXER_MODES, value="2", label="VoiceFixer Mode")
            use_deepfilternet = gr.Checkbox(label="Enable DeepFilterNet Denoising", value=True)
            use_pyrnnoise = gr.Checkbox(label="Enable pyrnnoise Denoising", value=True)

        

        with gr.Accordion("Subtitle Options", open=False):
            font_size = gr.Slider(18, 200, value=36, label="Font Size")
            primary_color_hex = gr.ColorPicker(label="Subtitle Color", value="#FFFFFF")
            #primary_color_hex.change(update_font_preview, [subtitle_font, font_size, primary_color_hex], font_preview_img)
            subtitle_font.change(update_font_preview, [subtitle_font, font_size, primary_color_hex], font_preview_img)        
            highlight_color_hex = gr.ColorPicker(label="Highlight (Spoken Word) Color", value="#FFFF00")        
            marginv = gr.Slider(0, 400, value=75, label="Caption Vertical Margin")
            outline_color_hex = gr.ColorPicker(label="Outline Color", value="#000000")
            back_color_hex = gr.ColorPicker(label="Back Color", value="#000000")
            bold = gr.Checkbox(label="Bold", value=False)
            italic = gr.Checkbox(label="Italic", value=False)
            underline = gr.Checkbox(label="Underline", value=False)
            strikeout = gr.Checkbox(label="Strikeout", value=False)
            angle = gr.Slider(0, 359, value=0, step=1, label="Angle")
            border_style = gr.Slider(1, 3, value=1, step=2, label="Border Style")
            outline = gr.Slider(0, 10, value=3, step=1, label="Outline")
            shadow = gr.Slider(0, 10, value=1, step=1, label="Shadow")
            with gr.Accordion("Advanced Subtitle Style Options", open=False):
                max_sentences = gr.Slider(1, 5, value=1, step=1, label="Max Sentences per Subtitle")
                max_words = gr.Slider(3, 25, value=5, step=1, label="Max Words per Subtitle")
                secondary_color_hex = gr.ColorPicker(label="Secondary Color", value="#FF0000", visible=False)
                marginl = gr.Slider(0, 100, value=10, step=1, label="MarginL")
                marginr = gr.Slider(0, 100, value=10, step=1, label="MarginR")
                spacing = gr.Slider(0, 20, value=0, step=1, label="Spacing")
                alignment = gr.Slider(1, 9, value=2, step=1, label="Alignment")
                scale_x = gr.Slider(50, 200, value=100, step=1, label="Scale X")
                scale_y = gr.Slider(50, 200, value=100, step=1, label="Scale Y")

        with gr.Accordion("Processing Options", open=False):
            threshold = gr.Slider(0.01, 0.20, value=0.04, step=0.01, label="Auto-Editor Silence Threshold")
            margin = gr.Slider(0.1, 2.0, value=0.5, step=0.1, label="Auto-Editor Margin (seconds)")
            bypass_auto = gr.Checkbox(label="Bypass Auto-Editor (skip silence removal)", value=False)
            bgm_volume = gr.Slider(0.0, 1.0, value=0.15, step=0.01, label="Background Music Volume")
            video_codec = gr.Textbox(label="Video Codec ([CPU]: libx264, libx265, libaom-av1, librav1e, libsvtav1; [Nvidia]: hevc_nvenc, h264_nvenc, av1_nvenc; [AMD]: h264_amf, av1_amf, hevc_amf; [Intel]: h264_qsv, hevc_qsv, av1_qsv, vp9_qsv)", value="hevc_nvenc")
            qp = gr.Textbox(label="FFmpeg QP Value (e.g. 0, 23, 30, 40)", value="30")
            merge_videos = gr.Checkbox(label="Merge/Concatenate selected videos into one", value=True)
            edit_transcript = gr.Checkbox(label="Edit transcript before creating subtitles", value=False)
        submit = gr.Button("Process Video")
        preview_btn = gr.Button("Preview Caption")
        preview_img = gr.Image(label="Preview", type="filepath")
        output_video = gr.File(label="Processed Video")

        # Process Video
        submit.click(
            gradio_main,
            [
                input_videos, background_audio, bypass_auto, edit_transcript,
                subtitle_font, font_size, marginv, threshold, margin,
                demucs_model, demucs_device, bgm_volume,
                max_sentences, max_words,
                nr_propdec, nr_stationary, nr_freqsmooth,
                lp_cutoff,
                use_demucs, use_noisereduce, use_lowpass, use_voicefixer,
                vf_mode, use_deepfilternet, use_pyrnnoise,
                primary_color_hex, highlight_color_hex,
                video_codec, qp, merge_videos,
                secondary_color_hex, outline_color_hex, back_color_hex,
                bold, italic, underline, strikeout,
                scale_x, scale_y, spacing, angle,
                border_style, outline, shadow, alignment,
                marginl, marginr
            ],
            outputs=output_files
        )

        # Preview Caption
        preview_btn.click(
            preview_caption_gradio,
            [
                input_videos, subtitle_font, font_size, primary_color_hex, highlight_color_hex, marginv,
                secondary_color_hex, outline_color_hex, back_color_hex,
                bold, italic, underline, strikeout,
                scale_x, scale_y, spacing, angle,
                border_style, outline, shadow, alignment,
                marginl, marginr
            ],
            outputs=preview_img
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
            (
                video_files, background_audio, bypass_auto, edit_transcript,
                subtitle_font, font_size, marginv, threshold, margin,
                demucs_model, demucs_device, bgm_volume,
                max_sentences, max_words,
                nr_propdec, nr_stationary, nr_freqsmooth,
                lp_cutoff,
                use_demucs, use_noisereduce, use_lowpass, use_voicefixer,
                vf_mode, use_deepfilternet, use_pyrnnoise,
                primary_color_hex, highlight_color_hex,
                video_codec, qp, merge_videos,
                secondary_color, outline_color, back_color,
                bold, italic, underline, strikeout,
                scale_x, scale_y, spacing, angle,
                border_style, outline, shadow, alignment,
                marginl, marginr
            ) = select_files_and_options()
            # Merge if needed
            if merge_videos and len(video_files) > 1:
                merged_filename = "merged_input.mp4"
                merge_videos_ffmpeg(video_files, merged_filename)
                input_video_for_main = merged_filename
            else:
                input_video_for_main = video_files[0]
            
            # Set outputs_folder and output_basename explicitly
            outputs_folder = get_outputs_folder()
            output_basename = f"Processed_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            main(
                input_video_for_main, background_audio, bypass_auto, edit_transcript,
                subtitle_font, font_size, marginv,
                threshold, margin,
                demucs_model, demucs_device, bgm_volume,
                max_sentences, max_words,
                nr_propdec, nr_stationary, nr_freqsmooth,
                lp_cutoff,
                use_demucs, use_noisereduce, use_lowpass, use_voicefixer,
                vf_mode, use_deepfilternet, use_pyrnnoise,
                primary_color_hex, highlight_color_hex,
                video_codec, qp,
                outputs_folder=outputs_folder,
                output_basename=output_basename,
                secondary_color=secondary_color, 
                outline_color=outline_color, 
                back_color=back_color,
                bold=bold, italic=italic, underline=underline, strikeout=strikeout,
                scale_x=scale_x, scale_y=scale_y, spacing=spacing, angle=angle,
                border_style=border_style, outline=outline, shadow=shadow, alignment=alignment,
                marginl=marginl, marginr=marginr
            )
        except Exception as e:
            print("❌ Error:", e)
            input("Press Enter to exit.")
