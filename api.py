from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from render_engine import render_video
import uuid

app = FastAPI()

@app.post("/render")
async def render_api(request: Request):
    body = await request.json()

    print("RECEIVED JSON:", body)

    output = render_video(body)

    return {"status": "completed", "video_url": f"/result/{uuid.uuid4()}"}


@app.get("/result/{id}")
async def download(id: str):
    return FileResponse("static/output/final.mp4", media_type="video/mp4")


