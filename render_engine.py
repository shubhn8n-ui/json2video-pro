import os
from moviepy.editor import *
from PIL import Image
import requests
from io import BytesIO

def download_image(url):
    r = requests.get(url)
    img = Image.open(BytesIO(r.content))
    return img

def download_audio(url):
    filename = "static/output/temp_audio.mp3"
    r = requests.get(url)
    with open(filename, "wb") as f:
        f.write(r.content)
    return filename

def render_video(data):
    os.makedirs("static/output", exist_ok=True)

    clips = []

    for scene in data["scenes"]:
        img = download_image(scene["elements"][0]["src"])
        img_path = "static/output/temp_img.png"
        img.save(img_path)

        img_clip = ImageClip(img_path).set_duration(scene["duration"])

        # zoom
        zoom = scene["elements"][0].get("zoom", 0)
        if zoom != 0:
            img_clip = img_clip.resize(lambda t: 1 + zoom * 0.05)

        # pan
        pan = scene["elements"][0].get("pan", "none")
        if pan == "right":
            img_clip = img_clip.set_position(lambda t: (t * 20, 0))
        if pan == "left":
            img_clip = img_clip.set_position(lambda t: (-t * 20, 0))
        if pan == "top":
            img_clip = img_clip.set_position(lambda t: (0, -t * 20))
        if pan == "bottom":
            img_clip = img_clip.set_position(lambda t: (0, t * 20))

        clips.append(img_clip)

    final = concatenate_videoclips(clips, method="compose")

    # audio
    audio_url = data["elements"][0]["src"]
    audio_file = download_audio(audio_url)
    final = final.set_audio(AudioFileClip(audio_file))

    output_path = "static/output/final.mp4"
    final.write_videofile(output_path, fps=30)

    return output_path
