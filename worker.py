import os, json, requests, subprocess

def update(job_id, status):
    with open(f"/tmp/{job_id}.json","w") as f:
        json.dump({"status": status}, f)

def render_task(job_id, payload):
    update(job_id, "downloading")

    # Just demo — real ffmpeg logic later
    # This will create a dummy video (black screen)
    update(job_id, "rendering")

    cmd = [
        "ffmpeg",
        "-f", "lavfi",
        "-i", "color=color=black:size=1080x1920:duration=5",
        f"/tmp/{job_id}.mp4"
    ]
    subprocess.run(cmd)

    update(job_id, "done")
