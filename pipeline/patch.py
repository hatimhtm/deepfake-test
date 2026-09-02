"""
Point the example graph at what we actually have.

Three kinds of change: the model names (the example's are Windows paths into
someone else's folders), the framing (the example is landscape; a reel is not),
and the media. Plus one removal — see below.
"""

import json
import sys

api = json.load(open(sys.argv[1]))
frames = int(sys.argv[2]) if len(sys.argv) > 2 else 0
prompt = sys.argv[3] if len(sys.argv) > 3 else (
    "a person filmed on a handheld phone camera, natural realistic lighting"
)

MODELS = {
    "187": ("model_name", "Wan2_2-Animate-14B_fp8_scaled_e4m3fn_KJ_v2.safetensors"),
    "188": ("vae_name", "wan_2.1_vae.safetensors"),
    "190": ("lora_name", "wan2.2_animate_14B_relight_lora_bf16.safetensors"),
    "191": ("lora_name", "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"),
}
for node, (field, value) in MODELS.items():
    api[node]["inputs"][field] = value
api["178"]["inputs"]["yolo_model"] = "yolov10m.onnx"

# SageAttention is a faster attention kernel the example turns on. It is not in
# the image (it is a compiled package, not a pip-and-go one), and asking for it
# when it is absent is a hard failure rather than a fallback.
api["187"]["inputs"]["sage_attention"] = "disabled"

# A reel is portrait. The example's 832x480 would letterbox the subject into a
# strip and spend most of the frame on padding.
api["150"]["inputs"]["value"] = 480   # width
api["151"]["inputs"]["value"] = 832   # height

api["57"]["inputs"]["image"] = "persona.png"
api["63"]["inputs"]["video"] = "reel.mp4"
api["63"]["inputs"]["frame_load_cap"] = frames

api["198"]["inputs"]["text"] = prompt

# torch.compile pays for itself over a long-lived server and costs on a
# serverless one: the worker is thrown away after the job, so the compile is
# paid again on every cold start and never amortised.
COMPILE = "192"
if COMPILE in api:
    src = next(
        (v for v in api[COMPILE]["inputs"].values()
         if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str)),
        None,
    )
    if src:
        for node in api.values():
            for k, v in node["inputs"].items():
                if isinstance(v, list) and len(v) == 2 and v[0] == COMPILE:
                    node["inputs"][k] = src
        del api[COMPILE]

# The example's final video is a contact strip — reference, pose, mask and
# result side by side — which is a debugging view, not a deliverable. Node 42 is
# the decoded result on its own; that becomes the video, and the strip stays as
# a second output because it is the thing that shows a person what changed.
api["30"]["inputs"]["images"] = ["42", 0]
api["30"]["inputs"]["filename_prefix"] = "swap"

COMPARE = "181"
if COMPARE in api:
    api[COMPARE]["inputs"]["images"] = ["66", 0]
    api[COMPARE]["inputs"]["audio"] = ["63", 2]
    api[COMPARE]["inputs"]["save_output"] = True
    api[COMPARE]["inputs"]["filename_prefix"] = "compare"

# Anything else that writes to the output folder just costs an encode.
for k, v in list(api.items()):
    if v["class_type"] == "VHS_VideoCombine" and k not in ("30", COMPARE):
        v["inputs"]["save_output"] = False

json.dump(api, open(sys.argv[1], "w"), indent=1)
print(f"patched {sys.argv[1]}: {len(api)} nodes, frame_load_cap={frames}")
