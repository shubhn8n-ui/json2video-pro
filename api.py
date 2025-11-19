from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
import subprocess, uuid, os, json, asyncio

app = FastAPI()

@app.post("/render")
async def render_api(request: Request):
    body = await request.json()

    os.makedirs("static", exist_ok=True)

    filename = f"{uuid.uuid4()}.mp4"
    output_path = f"static/{filename}"

    # ffmpeg command (non-blocking)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "color=c=black:s=1080x1920:d=5",
        output_path
    ]

    # Run FFmpeg asynchronously (no blocking)
    asyncio.create_task(run_ffmpeg(cmd))

    # Immediate response (no timeout)
    return{
    "job_id": job_id,
    "status": "processing",
    "video_url": f"/result/{job_id}.mp4"
}
async def run_ffmpeg(cmd):
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await process.communicate()

@app.get("/result/{file}")
async def result(file: str):
    file_path = f"static/{file}"
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return JSONResponse({"error": "not ready"}, status_code=404)


@app.get("/result/{file}")
async def download(file: str):
    return FileResponse(f"static/{file}", media_type="video/mp4")


