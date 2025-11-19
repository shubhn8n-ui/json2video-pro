from fastapi import FastAPI
from pydantic import BaseModel
import subprocess
import uuid
import os

app = FastAPI()

class RenderInput(BaseModel):
    resolution: str
    scenes: list
    elements: list

@app.post("/render")
def render_video(data: RenderInput):
    job_id = uuid.uuid4().hex
    output_path = f"/tmp/{job_id}.mp4"

    # Simple demo ffmpeg cmd: 5 sec black video
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", "color=color=black:size=1080x1920:duration=5",
        output_path
    ]

    subprocess.run(cmd)

    return {
        "job_id": job_id,
        "status": "done",
        "url": f"https://json2video-pro.onrender.com/result/{job_id}"
    }

@app.get("/result/{job_id}")
def get_result(job_id: str):
    path = f"/tmp/{job_id}.mp4"

    if not os.path.exists(path):
        return {"error": "not found"}

    return {
        "download": f"https://json2video-pro.onrender.com/static/{job_id}.mp4"
    }

