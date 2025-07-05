# 🌟 WordLight: AI-Powered Video Captioning & Audio Enhancement Suite

WordLight is the **ultimate video speech captioning and audio enhancement tool** for content creators, educators, and anyone wanting to make videos more engaging and accessible. With just a few clicks, WordLight will:

- **Clean and enhance your spoken audio**
- **Transcribe every word with millisecond precision**
- **Burn in beautiful, word-synced subtitles (ASS) with highlighting**
- **Mix and duck background music automatically**
- **Export your final video in minutes**

---

## ✨ Features

- **One-Click Operation:** User-friendly desktop or web-based GUI (Tkinter/Gradio)
- **Accurate Word-Level Captions:** Powered by Whisper + word timestamping
- **Visual Word Highlighting:** The currently spoken word is always highlighted
- **Flexible Denoising Pipeline:** Choose from DeepFilterNet, Demucs, Noisereduce, or VoiceFixer, or stack them for maximal quality
- **Audio Silence Removal:** Optional automatic silencing of gaps (auto-editor)
- **Background Music Mixing:** Adds music with auto ducking and fadeout
- **Customizable Everything:** Fonts, sizes, colors (caption and highlight), position, and more
- **LAN/Remote Access:** Use Gradio to process from any device in your network
- **Output Archive:** Every processed video is saved in an `Outputs` folder with timestamp, accessible via web UI
- **Edit Transcript Before Finalization:** Optional edit step for perfect captions

---

## 🚀 Quick Start

### **1. Installation**

Make sure [ffmpeg and ffprobe](https://ffmpeg.org/download.html) are installed and available in your PATH or you can just place them in the same directory as the WordLight.py script.


just download the repo or clone it with:
```bash
git clone https://github.com/petermg/WordLight/
```
then on Windows just double click on `runme.bat` and it will set up everything for you and run the application.

Or if not on Windows, make sure you have python 3.10.x installed and do:
`pip install -r requirements.txt`


### 2. Run WordLight

**Desktop GUI:**
```bash
python WordLight.py
```
(or just double-click on runme.bat if on Windows)

and select `Tkinter GUI` when prompted.

**Web GUI (Gradio):**
```bash
python WordLight.py
```
(or just double-click on runme.bat if on Windows)

and select `Gradio Web UI` when prompted.

---

## 🧩 How It Works

1. **Select Input Video and (optional) Background Music**
2. **Choose Enhancement & Captioning Options**  
   (Denoising, enhancement, font style, silence removal, etc.)
3. **WordLight processes:**  
   - Audio is cleaned, denoised, and enhanced  
   - Video is trimmed for silences (if selected)  
   - Captions are generated, optionally edited, and burned-in  
   - Background music is added and ducked for clarity  
4. **Download your finished video**  
   - All outputs are saved in the `Outputs` folder
   - Gradio UI shows download links to all recent outputs

---

## 🖥️ User Interface Overview

- **Font & Color Selection**: Live font preview and easy color pickers for both subtitle and highlighted word colors.
- **Denoising/Enhancement**: Toggle Demucs, Noisereduce, DeepFilterNet, VoiceFixer, and set model/parameters for each.
- **Silence Removal**: Enable/disable auto-editor, adjust threshold and margin.
- **Caption Customization**: Set font, size, highlight color, margin, words per caption, etc.
- **Background Music**: Select file and adjust volume; automatic fade-out and sidechain ducking.
- **Transcript Editing**: (Optional) Edit the transcript in your default text editor before finalizing.

---

## 🛠️ Advanced Features

- **Demucs**: Choose from a range of models; automatic CUDA/CPU selection.
- **Noisereduce**: Propagation, stationary, and frequency mask parameters exposed.
- **DeepFilterNet**: Quick switch for deep-learning denoising.
- **VoiceFixer**: Restore and enhance degraded speech with selectable modes.
- **Low-Pass Filter**: For additional cleaning.
- **Output Management**: Every session's output is saved with a timestamp. Broken sessions? Just refresh in Gradio—your files are still there!

---

## 📝 Requirements

- Python 3.8+
- ffmpeg + ffprobe in your PATH (or the same folder as the WordLight.py script)

### Python Packages
- `torch`
- `whisper_timestamped`
- `noisereduce`
- `gradio`
- `soundfile`
- `scipy`
- `deepfilternet`
- `voicefixer`
- `auto-editor`
- (and their dependencies)

---

## 🤝 Credits

- **[OpenAI Whisper](https://github.com/openai/whisper)**
- **[Whisper-timestamped](https://github.com/linto-ai/whisper-timestamped)**
- **[Demucs](https://github.com/facebookresearch/demucs)**
- **[DeepFilterNet](https://github.com/Rikorose/DeepFilterNet)**
- **[VoiceFixer](https://github.com/haoheliu/voicefixer)**
- **[Noisereduce](https://github.com/timsainb/noisereduce)**
- **[Gradio](https://github.com/gradio-app/gradio)**
- **[Tkinter]** (built-in)
- **[auto-editor](https://github.com/WyattBlue/auto-editor)**

---

## 📜 License

[MIT License](LICENSE)

---

## 🏁 To-do

- [ ] Give user options over which whisper model to use.
- [ ] Make option to reprocess temp video file before burning captions with new/modified/editied ass/subtitle file for quicker edits.
- [ ] Make subtitle editing possible over Gradio.

---

## 💬 Feedback & Contributions

Found a bug or want to contribute? Open an issue or pull request!  
Questions? [Start a discussion](https://github.com/yourusername/WordLight/discussions)

---

**Empower your words. Light up your videos. — WordLight**
