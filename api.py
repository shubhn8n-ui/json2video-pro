# api.py
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
import asyncio, subprocess, uuid, os, requests, shlex, json, shutil

app = FastAPI()

BASE_DIR = "static"
os.makedirs(BASE_DIR, exist_ok=True)

def safe_filename(s):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in s)

async def download_file(url, out_path):
    # download with requests (blocking) but run inside thread
    loop = asyncio.get_event_loop()
    def _dl():
        r = requests.get(url, stream=True, timeout=60)
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(1024 * 64):
                if chunk:
                    f.write(chunk)
    await loop.run_in_executor(None, _dl)
    return out_path

async def run_cmd(cmd, cwd=None):
    # cmd: list
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd
    )
    out, err = await process.communicate()
    return process.returncode, out.decode(errors="ignore"), err.decode(errors="ignore")

def write_status(job_dir, data):
    with open(os.path.join(job_dir, "status.json"), "w") as f:
        json.dump(data, f)

@app.post("/render")
async def render_endpoint(request: Request):
    data = await request.json()
    job_id = uuid.uuid4().hex
    job_dir = os.path.join(BASE_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    # save received json
    with open(os.path.join(job_dir, "payload.json"), "w") as f:
        json.dump(data, f, indent=2)

    # initial status file
    write_status(job_dir, {"job_id": job_id, "status": "queued"})

    # start background processing task
    asyncio.create_task(process_job(job_id, data))
    return JSONResponse({"job_id": job_id, "status": "processing", "video_url": f"/result/{job_id}.mp4"})

@app.get("/status/{job_id}")
async def status(job_id: str):
    job_dir = os.path.join(BASE_DIR, job_id)
    status_file = os.path.join(job_dir, "status.json")
    if os.path.exists(status_file):
        with open(status_file, "r") as f:
            return JSONResponse(json.load(f))
    return JSONResponse({"job_id": job_id, "status": "not_found"}, status_code=404)

@app.get("/result/{file_name}")
async def result(file_name: str):
    path = os.path.join(BASE_DIR, file_name)
    if os.path.exists(path):
        return FileResponse(path, media_type="video/mp4")
    return JSONResponse({"error": "not_ready"}, status_code=404)

async def process_job(job_id, data):
    job_dir = os.path.join(BASE_DIR, job_id)
    try:
        write_status(job_dir, {"job_id": job_id, "status": "downloading"})
        # parse scenes and elements
        scenes = data.get("scenes", [])
        elements_root = data.get("elements", [])

        # download images
        image_paths = []
        for i, scene in enumerate(scenes):
            el = scene.get("elements", [])
            if not el:
                continue
            img_url = el[0].get("src")
            if not img_url:
                continue
            out_img = os.path.join(job_dir, f"img_{i}.jpg")
            await download_file(img_url, out_img)
            image_paths.append({
                "path": out_img,
                "duration": float(scene.get("duration", 5)),
                "transition": scene.get("transition", None),
                "zoom": el[0].get("zoom", 0),
                "pan": el[0].get("pan", None)
            })

        # download audio (take first audio element if present)
        audio_url = None
        for el in elements_root:
            if el.get("type") == "audio":
                audio_url = el.get("src")
                break
        audio_path = None
        if audio_url:
            audio_path = os.path.join(job_dir, "audio.mp3")
            try:
                await download_file(audio_url, audio_path)
            except Exception as e:
                # if audio download fails, continue without audio
                audio_path = None

        # caption (single caption text, apply on full video)
        caption_text = None
        for el in elements_root:
            if el.get("type") in ("caption", "subtitles", "text"):
                caption_text = el.get("text") or el.get("caption") or el.get("subtitle")
                break

        write_status(job_dir, {"job_id": job_id, "status": "rendering", "progress": 5})

        # create per-image short video files (loop image)
        clip_files = []
        for idx, img in enumerate(image_paths):
            duration = img["duration"]
            out_clip = os.path.join(job_dir, f"clip_{idx}.mp4")
            # simple image->video command (scale to 1080x1920)
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", img["path"],
                "-t", str(duration),
                "-vf", "scale=1080:1920,format=yuv420p",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "23",
                "-r", "25",
                out_clip
            ]
            code, out, err = await run_cmd(cmd)
            if code != 0:
                # if clip generation fails, write error and abort
                write_status(job_dir, {"job_id": job_id, "status": "failed", "error": f"ffmpeg clip error: {err[:200]}"})
                return
            clip_files.append(out_clip)
            write_status(job_dir, {"job_id": job_id, "status": "rendering", "progress": 10 + int((idx+1)/max(1,len(image_paths))*40)})

        # if only one clip, final = clip0 (then add audio+caption)
        final_noaudio = os.path.join(job_dir, "final_noaudio.mp4")
        if len(clip_files) == 0:
            write_status(job_dir, {"job_id": job_id, "status": "failed", "error": "no images"})
            return
        elif len(clip_files) == 1:
            shutil.copyfile(clip_files[0], final_noaudio)
        else:
            # concatenate clips with simple concat demuxer
            list_txt = os.path.join(job_dir, "clips.txt")
            with open(list_txt, "w") as f:
                for c in clip_files:
                    f.write(f"file '{os.path.abspath(c)}'\n")
            cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", list_txt, "-c", "copy", final_noaudio
            ]
            code, out, err = await run_cmd(cmd)
            if code != 0:
                # fallback: try re-encoding concat
                cmd2 = [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", list_txt, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", final_noaudio
                ]
                code2, out2, err2 = await run_cmd(cmd2)
                if code2 != 0:
                    write_status(job_dir, {"job_id": job_id, "status": "failed", "error": f"concat error: {err2[:200]}"})
                    return

        write_status(job_dir, {"job_id": job_id, "status": "mixing", "progress": 70})

        # now add audio (if exists) and caption using drawtext
        final_out = os.path.join(job_dir, f"{job_id}.mp4")
        vf_filters = []
        if caption_text:
            # safe-escape quotes and colons
            safe_text = caption_text.replace("'", r"\'").replace(":", r"\:")
            # try to find a TTF font on system; common is DejaVuSans
            fontfile = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            draw = f"drawtext=fontfile={fontfile}:text='{safe_text}':fontsize=48:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=10:x=(w-text_w)/2:y=h-150"
            vf_filters.append(draw)
        vf = ",".join(vf_filters) if vf_filters else None

        # build ffmpeg command to add audio and filters
        if audio_path:
            cmd = ["ffmpeg", "-y", "-i", final_noaudio, "-i", audio_path, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-map", "0:v:0", "-map", "1:a:0", "-shortest"]
            if vf:
                cmd += ["-vf", vf]
            cmd += [final_out]
        else:
            cmd = ["ffmpeg", "-y", "-i", final_noaudio, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]
            if vf:
                cmd += ["-vf", vf]
            cmd += [final_out]

        code, out, err = await run_cmd(cmd)
        if code != 0:
            write_status(job_dir, {"job_id": job_id, "status": "failed", "error": f"final ffmpeg error: {err[:300]}"})
            return

        # success
        write_status(job_dir, {"job_id": job_id, "status": "done", "video_url": f"/result/{job_id}.mp4"})
        # move final_out to static/{job_id}.mp4 (so /result endpoint serves it)
        shutil.copyfile(final_out, os.path.join(BASE_DIR, f"{job_id}.mp4"))
        # cleanup temp files optionally (keep for debug)
        # shutil.rmtree(job_dir)   # if you want to remove temp
    except Exception as e:
        write_status(job_dir, {"job_id": job_id, "status": "failed", "error": str(e)})


