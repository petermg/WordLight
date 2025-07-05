# WordLight
Automatic Video highlighted captioning with noise removal, vocal enhancement and background music option

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

## 🖼️ Example Output

<img src="https://imgur.com/your-sample-output.png" alt="Sample video output" width="600"/>

---

## 🚀 Quick Start

### **1. Install Dependencies**

Make sure [ffmpeg](https://ffmpeg.org/download.html) is installed and available in your PATH.

```bash
pip install -r requirements.txt
# or individually:
pip install torch whisper_timestamped noisereduce gradio soundfile scipy deepfilternet voicefixer auto-editor

