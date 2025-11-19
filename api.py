from fastapi import FastAPI
from pydantic import BaseModel
import uuid
import redis
from rq import Queue

r = redis.Redis(host="redis", port=6379, db=0)
q = Queue("render", connection=r)

app = FastAPI()

class RenderInput(BaseModel):
    resolution: str
    scenes: list
    elements: list

@app.post("/render")
async def render_video(data: RenderInput):
    job_id = uuid.uuid4().hex
    q.enqueue("worker.render_task", job_id, data.dict())
    return {"job_id": job_id, "status": "queued"}

@app.get("/status/{job_id}")
def get_status(job_id: str):
    try:
        with open(f"/tmp/{job_id}.json") as f:
            import json
            return json.load(f)
    except:
        return {"status": "processing"}

@app.get("/result/{job_id}")
def result(job_id: str):
    return {"url": f"https://your-bucket/{job_id}.mp4"}
