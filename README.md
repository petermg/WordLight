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
- **LAN/Internet/Remote Access:** Use Gradio to process from any device in your network over the web!
- **Output Archive:** Every processed video is saved in an `Outputs` folder with timestamp, accessible via web UI
- **Edit Transcript Before Finalization:** Optional edit step for perfect captions

---

## 🚀 Quick Start

### **1. Install Dependencies**

Make sure [ffmpeg and ffprobe](https://ffmpeg.org/download.html) are installed and available in your PATH or you can just place them in the same directory as the WordLight.py script.


just download the repo or clone it with:
```bash
git clone https://github.com/petermg/WordLight/
```
then just double click on `runme.bat` and it will set up everything for you and run the application.

## NOTES:
If you don't want to have background music you can just select your input video for the background music, you can also set the volume to 0, though this probably isn't needed.


## To-Do
Give user options over which whisper model to use.

Make option to reprocess temp video file before burning captions with new/modified/editied ass/subtitle file for quicker edits.

Make subtitle editing possible over Gradio.
