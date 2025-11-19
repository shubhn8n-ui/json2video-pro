from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
import subprocess, uuid, os, json

app = FastAPI()

@app.post("/render")
async def render_api(request: Request):
    body = await request.json()

    os.makedirs("static", exist_ok=True)

    output_path = f"static/{uuid.uuid4()}.mp4"

    # Render-friendly simple ffmpeg black video
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "color=c=black:s=1080x1920:d=5",
        output_path
    ]

    subprocess.run(cmd)

    return {
        "status": "done",
        "video_url": f"/result/{os.path.basename(output_path)}"
    }

@app.get("/result/{file}")
async def download(file: str):
    return FileResponse(f"static/{file}", media_type="video/mp4")


