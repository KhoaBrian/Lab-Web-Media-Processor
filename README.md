# Lab Web Media Processor

A local, multithreaded GUI utility developed to automate batch watermarking, compression, and WebP/GIF conversion for lab media assets.

## Why?
This project was built for our mem for web media optimization. It ensures:
- **Data Privacy:** offline local processing (crucial for unpublished scientific images).
- **Accessibility:** A friendly GUI allows non-programming lab members to easily batch process hundreds of images without dealing with command lines.
- **Custom Timestamps:** Automated sequence text overlay (time/number) across frames, specifically designed for time-lapse microscopy animations.

## Features
- **Batch Optimization:** Fast multithreaded image processing, optional WebP conversion, and high-quality diagonal watermarking.
- **Animation Sequence:** Sequence frame compilation (GIF / Animated WebP) with dynamic timestamp/number overlays per frame.
- **Advanced Rendering:** Uses SSAA via Lanczos resampling to ensure crisp, clean watermarks.

## 💻 Tech Stack & Architecture
- **Language:** Python 3.12
- **GUI Framework:** Tkinter.
- **Image Processing:** Pillow
