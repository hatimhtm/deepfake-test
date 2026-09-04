"""
Tom Eden's "AnimateCharacter Transfer v5" — SCAIL-2 with SAM3 tracking — made to
run on our worker.

His editor graph leans on seven nodes from packs we do not carry, every one of
them either a constant or a pass-through: two integer boxes (segments, seconds),
a "a*20+1" arithmetic box (frames to load), an empty text box (the prompt), a
VRAM purge, and GIMM-VFI interpolation with its loader. This inlines the
constants into their consumers, wires the pass-throughs straight through, drops
the loader, then converts with the same converter as the Wan-Animate graph.
RIFE ×2 is added at the end so the 40 fps his graph promises through GIMM is
real. The weights we hold replace his fp16 names (fp8 scaled, fp8 text encoder,
the repackaged clip-vision), and the CivitAI "Running" motion LoRA at 0.2 is
simply not loaded.

    python3 scail2-prep.py upstream.json object-info.json out.json
"""
import json, subprocess, sys, tempfile, os

src, oi, out = sys.argv[1:4]
g = json.load(open(src))
nodes = {n["id"]: n for n in g["nodes"]}
links = {l[0]: l for l in g["links"] if isinstance(l, list)}

def consumers(nid):
    r = []
    for o in nodes[nid].get("outputs") or []:
        for lid in o.get("links") or []:
            l = links.get(lid)
            if not l: continue
            to, slot = l[3], l[4]
            r += consumers(to) if nodes[to]["type"] == "Reroute" else [(to, slot)]
    return r

def producer(nid, slot):
    n = nodes[nid]
    while n["type"] == "Reroute":
        l = links[n["inputs"][0]["link"]]; nid, slot = l[1], l[2]; n = nodes[nid]
    return nid, slot

def inline_constant(nid, value):
    for to, slot in consumers(nid):
        inp = nodes[to]["inputs"][slot]; inp["link"] = None
        nodes[to].setdefault("_inline", {})[inp["name"]] = value
    nodes[nid]["_drop"] = True

by_type = lambda t: [n["id"] for n in g["nodes"] if n["type"] == t]
for nid in by_type("JWInteger"): inline_constant(nid, 5)           # SAM3 max_objects
for nid in by_type("SimpleMath+"): inline_constant(nid, 12 * 20 + 1)  # frames to load: 12 s at 20 fps
for nid in by_type("easy int"): nodes[nid]["_drop"] = True          # only fed the arithmetic box
for nid in by_type("CR Text"): inline_constant(nid, "")             # the (empty) prompt
gimm = by_type("GIMMVFI_interpolate")[0]
purge = by_type("LayerUtility: PurgeVRAM V2")[0]
frames_src = producer(*producer(purge, 0)[:1], 0) if False else None
# what feeds the purge → that is what the final combine should read, through RIFE
pl = links[[i for i in nodes[purge]["inputs"] if i["name"] == "anything"][0]["link"]]
frames_src = producer(pl[1], pl[2])
final = [to for to, _ in consumers(gimm)][0]
for nid in (gimm, purge, *by_type("DownloadAndLoadGIMMVFIModel")): nodes[nid]["_drop"] = True
g["nodes"] = [n for n in g["nodes"] if not n.get("_drop")]

tmp = os.path.join(tempfile.mkdtemp(), "prepped.json"); json.dump(g, open(tmp, "w"))
subprocess.check_call([sys.executable, os.path.join(os.path.dirname(__file__), "convert.py"), tmp, oi, out])

a = json.load(open(out))
a["300"] = {"class_type": "RIFE VFI", "inputs": {"ckpt_name": "rife49.pth", "frames": [str(frames_src[0]), frames_src[1]], "clear_cache_after_n_frames": 10, "multiplier": 2, "fast_mode": True, "ensemble": True, "scale_factor": 1, "dtype": "float32", "batch_size": 1, "torch_compile": False}, "_meta": {"title": "RIFE VFI"}}
a[str(final)]["inputs"].update({"images": ["300", 0], "frame_rate": 40, "filename_prefix": "scail"})
for nid, n in a.items():
    t = n["class_type"]
    if t == "UNETLoader": n["inputs"]["unet_name"] = "wan2.1_14B_SCAIL_2_fp8_scaled.safetensors"
    if t == "CLIPLoader": n["inputs"]["clip_name"] = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
    if t == "CLIPVisionLoader": n["inputs"]["clip_name"] = "clip_vision_h.safetensors"
    if t == "VHS_LoadVideo": n["inputs"]["video"] = "reel.mp4"
    if t == "LoadImage": n["inputs"]["image"] = "persona.png"
    if t == "VHS_VideoCombine" and nid != str(final): n["inputs"]["save_output"] = False
running = [nid for nid, n in a.items() if n["class_type"] == "LoraLoaderModelOnly" and "Running" in str(n["inputs"].get("lora_name"))]
for r in running:
    up = a[r]["inputs"]["model"]
    for n in a.values():
        for k, v in n["inputs"].items():
            if isinstance(v, list) and len(v) == 2 and v[0] == r: n["inputs"][k] = up
    del a[r]
json.dump(a, open(out, "w"), indent=1)
print(f"{len(a)} nodes -> {out}")
