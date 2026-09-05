"""
A thin serverless handler for the Wan-Animate worker on RunPod.

The stock worker-comfyui handler takes base64 images under 10 MB in and returns
images out, which a reel cannot travel through in either direction. This does
three things and nothing else:

  1. `input.files` — [{name, url}] fetched into ComfyUI's input folder, so a
     100 MB reel never rides inside the request body.
  2. `input.upload_urls` — signed URLs, spent in filename order on whatever
     ComfyUI writes during the job, mp4s included. The credential stays with
     the caller; this worker is rented by the minute and holds none.
  3. `input.op = "object_info"` — what ComfyUI thinks a node's inputs are,
     which is the only way to convert an editor-format graph or tell a missing
     node pack from a malformed one, there being no shell on a live worker.

ComfyUI itself is the untouched one from the base image; this only talks to it
over its local HTTP API.
"""

import base64
import json
import os
import shutil
import time
import urllib.request
import urllib.parse
import mimetypes
import uuid

import runpod

COMFY = os.environ.get("COMFY_HOST", "127.0.0.1:8188")
INPUT_DIR = os.environ.get("COMFY_INPUT_DIR", "/comfyui/input")
OUTPUT_DIR = os.environ.get("COMFY_OUTPUT_DIR", "/comfyui/output")

# Outputs leave over per-job signed URLs the caller mints, so this worker never
# holds a storage credential. A GPU box rented by the minute from strangers is
# the last place a service-role key should live, and a signed URL that expires
# is worth nothing to anyone who finds it afterwards.
MAX_INLINE = int(os.environ.get("MAX_INLINE_BYTES", 8 << 20))


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


def _put(path, target):
    """Send one file to a signed URL the caller minted.

    `target` is either the URL string or {url, method, headers}, so the same
    handler works against Supabase, S3 or anything else that hands out a signed
    PUT — the worker never learns which, and never holds a key for any of them.
    """
    if isinstance(target, str):
        target = {"url": target}
    ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    with open(path, "rb") as f:
        data = f.read()
    headers = {"Content-Type": ctype}
    headers.update(target.get("headers") or {})
    req = urllib.request.Request(
        target["url"], data=data, method=target.get("method", "PUT"), headers=headers
    )
    with urllib.request.urlopen(req, timeout=900) as r:
        r.read()
    # The public address is the caller's to know; it minted the URL.
    return target.get("public_url")


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

    # What is actually on the volume. Two lanes now share it and guessing
    # which folder a checkpoint landed in has already cost a rebuild.
    if inp.get("op") == "ls":
        root = os.path.join("/runpod-volume", str(inp.get("path") or "models").lstrip("/"))
        out = []
        for base, dirs, names in os.walk(root):
            depth = base[len(root):].count(os.sep)
            for n in sorted(names):
                p = os.path.join(base, n)
                out.append({"file": os.path.relpath(p, root), "bytes": os.path.getsize(p)})
            if depth >= int(inp.get("depth") or 2):
                dirs[:] = []
        return {"root": root, "files": out[:2000]}

    # Put a file ONTO the volume. A LoRA trained here lands in ComfyUI's
    # output folder, which no loader reads; without this it would have to
    # travel out to storage and back in on a rented pod just to be usable.
    # Confined to /runpod-volume/models so a job cannot write anywhere else.
    if inp.get("op") == "install":
        rel = str(inp.get("path") or "").lstrip("/")
        url = inp.get("url")
        root = "/runpod-volume/models"
        dest = os.path.normpath(os.path.join(root, rel))
        if not rel or not url:
            return {"error": "input.path and input.url are required"}
        if not dest.startswith(root + os.sep):
            return {"error": f"path escapes {root}"}
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        try:
            with urllib.request.urlopen(url, timeout=600) as r, open(dest, "wb") as f:
                shutil.copyfileobj(r, f, 1024 * 1024)
        except Exception as e:  # noqa: BLE001
            return {"error": f"install failed: {e}"}
        return {"installed": os.path.relpath(dest, root), "bytes": os.path.getsize(dest)}

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

    # Ship everything new in the output folder, in filename order, spending the
    # caller's signed URLs in that same order. Anything left over comes back
    # inline if it is small enough to travel, and is otherwise only named — a
    # 200 MB mp4 cannot ride inside a JSON response, and pretending otherwise
    # fails later and less clearly than saying so here.
    uploads = list(inp.get("upload_urls") or [])
    outputs = []
    for root, _, names in os.walk(OUTPUT_DIR):
        for n in sorted(names):
            p = os.path.join(root, n)
            if p in before:
                continue
            rel = os.path.relpath(p, OUTPUT_DIR)
            size = os.path.getsize(p)
            entry = {"file": rel, "bytes": size}
            if uploads:
                try:
                    entry["url"] = _put(p, uploads.pop(0))
                except Exception as e:  # noqa: BLE001
                    entry["error"] = f"upload failed: {e}"
            elif size <= MAX_INLINE:
                with open(p, "rb") as f:
                    entry["base64"] = base64.b64encode(f.read()).decode()
            else:
                entry["error"] = "no upload URL left for this file, and too big to inline"
            outputs.append(entry)

    # What ComfyUI itself says each output node produced — the way to tell a
    # graph that saved nothing from a scan that missed something.
    reported = {}
    for node, out in (h.get("outputs") or {}).items():
        reported[node] = {k: v for k, v in out.items() if k in ("images", "gifs", "video", "audio", "text")}
    return {
        "outputs": outputs,
        "reported": reported,
        "seconds": round(time.time() - started, 1),
        "prompt_id": prompt_id,
    }


runpod.serverless.start({"handler": handler})
