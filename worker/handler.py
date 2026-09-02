"""
A thin serverless handler for SCAIL-2 on RunPod.

The stock worker-comfyui handler only accepts input as base64 images under
10 MB and only returns images. This job moves a reel in and a video out, so
this handler does two extra things and nothing else:

  1. `input.files`  — [{name, url}] downloaded into ComfyUI's input folder,
     so a 100 MB reel never rides inside the request body.
  2. Every file ComfyUI writes to its output folder during the job — mp4s
     included — is uploaded to Supabase storage and returned as a URL.

ComfyUI itself is the untouched one from the base image; this only talks to it
over its local HTTP API.
"""

import json
import os
import time
import urllib.request
import urllib.parse
import mimetypes
import uuid

import runpod

COMFY = os.environ.get("COMFY_HOST", "127.0.0.1:8188")
INPUT_DIR = os.environ.get("COMFY_INPUT_DIR", "/comfyui/input")
OUTPUT_DIR = os.environ.get("COMFY_OUTPUT_DIR", "/comfyui/output")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
BUCKET = os.environ.get("SUPABASE_BUCKET", "deepfake-test")


def _get(url, timeout=30):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def _download(name, url):
    """Fetch one input file into ComfyUI's input folder, by URL."""
    safe = os.path.basename(name)
    path = os.path.join(INPUT_DIR, safe)
    os.makedirs(INPUT_DIR, exist_ok=True)
    with urllib.request.urlopen(url, timeout=600) as r, open(path, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    return safe


def _wait_for_comfy(seconds=300):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            _get(f"http://{COMFY}/system_stats", timeout=5)
            return True
        except Exception:
            time.sleep(1)
    return False


def _queue(workflow, client_id):
    body = json.dumps({"prompt": workflow, "client_id": client_id}).encode()
    req = urllib.request.Request(
        f"http://{COMFY}/prompt", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def _history(prompt_id):
    return json.loads(_get(f"http://{COMFY}/history/{prompt_id}", timeout=30))


def _upload(path, key):
    """PUT one file into Supabase storage; returns its public URL."""
    ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    with open(path, "rb") as f:
        data = f.read()
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{urllib.parse.quote(key)}"
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "apikey": SUPABASE_KEY,
            "Content-Type": ctype,
            "x-upsert": "true",
        },
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        r.read()
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{urllib.parse.quote(key)}"


def _object_info(names):
    """The definitions of specific nodes, as ComfyUI reports them.

    Graphs are drawn in the editor's format, but /prompt only accepts the API
    format, and converting between the two needs to know each node's real input
    names — which only the running ComfyUI knows. Asking for named nodes rather
    than the whole catalogue keeps the reply small enough to travel.
    """
    if not names:
        return json.loads(_get(f"http://{COMFY}/object_info", timeout=60))
    out = {}
    for n in names:
        try:
            out.update(json.loads(_get(f"http://{COMFY}/object_info/{urllib.parse.quote(n)}", timeout=30)))
        except Exception as e:  # noqa: BLE001
            out[n] = {"error": str(e)}
    return out


def handler(job):
    started = time.time()
    inp = job.get("input") or {}

    # Introspection, so a graph can be converted and a missing node pack
    # diagnosed without shell access to a serverless worker.
    if inp.get("op") == "object_info":
        if not _wait_for_comfy():
            return {"error": "ComfyUI did not come up"}
        return {"object_info": _object_info(inp.get("nodes") or [])}

    workflow = inp.get("workflow")
    if not isinstance(workflow, dict):
        return {"error": "input.workflow (API format) is required"}

    if not _wait_for_comfy():
        return {"error": "ComfyUI did not come up"}

    # Inputs by URL.
    for f in inp.get("files") or []:
        try:
            _download(f["name"], f["url"])
        except Exception as e:  # noqa: BLE001
            return {"error": f"could not fetch {f.get('name')}: {e}"}

    # Note what is already in the output folder, so only this job's files ship.
    before = set()
    for root, _, names in os.walk(OUTPUT_DIR):
        for n in names:
            before.add(os.path.join(root, n))

    client_id = str(uuid.uuid4())
    try:
        queued = _queue(workflow, client_id)
    except urllib.error.HTTPError as e:  # type: ignore[attr-defined]
        return {"error": f"ComfyUI rejected the workflow: {e.read().decode()[:2000]}"}
    prompt_id = queued.get("prompt_id")
    if not prompt_id:
        return {"error": f"no prompt_id in {queued}"}

    # Poll until the prompt has a history entry.
    deadline = time.time() + int(os.environ.get("JOB_TIMEOUT_S", "3300"))
    while time.time() < deadline:
        h = _history(prompt_id).get(prompt_id)
        if h:
            status = h.get("status") or {}
            if status.get("status_str") == "error" or status.get("completed") is False and status.get("messages"):
                # Surface ComfyUI's own error text.
                msgs = [m for m in status.get("messages", []) if m and m[0] == "execution_error"]
                return {"error": "ComfyUI execution error", "detail": msgs[-1][1] if msgs else status}
            if status.get("completed") or h.get("outputs"):
                break
        time.sleep(2)
    else:
        return {"error": "timed out waiting for ComfyUI"}

    # Ship everything new in the output folder.
    outputs = []
    prefix = inp.get("prefix") or job.get("id") or client_id
    for root, _, names in os.walk(OUTPUT_DIR):
        for n in sorted(names):
            p = os.path.join(root, n)
            if p in before:
                continue
            rel = os.path.relpath(p, OUTPUT_DIR)
            try:
                url = _upload(p, f"{prefix}/{rel}") if SUPABASE_URL and SUPABASE_KEY else None
            except Exception as e:  # noqa: BLE001
                url = None
                outputs.append({"file": rel, "error": str(e)})
                continue
            outputs.append({"file": rel, "url": url, "bytes": os.path.getsize(p)})

    return {
        "outputs": outputs,
        "seconds": round(time.time() - started, 1),
        "prompt_id": prompt_id,
    }


runpod.serverless.start({"handler": handler})
