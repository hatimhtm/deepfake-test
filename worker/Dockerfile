# TrendSwap video worker: ComfyUI + Wan 2.2 Animate, on RunPod serverless.
#
# The stock worker-comfyui takes base64 images in and gives images out, which a
# reel cannot travel through. Everything here is the base image plus the four
# node packs the official Wan-Animate graph uses, and a handler that moves files
# by URL instead.
FROM runpod/worker-comfyui:5.10.0-base

# Pinned to a commit each, so a rebuild six months from now is the same worker
# and a broken upstream push can never reach production on its own.
ARG VHS_SHA=4d907bee61e92c2e65af3bd6383a4e4d356126d1
ARG KJ_SHA=e8e88f7c88e3f6205b122f5de87e69a09fbce5ac
ARG WAP_SHA=0e0b6a2a555625acf4d4aefb780e27d06937132f
ARG SAM2_SHA=0c35fff5f382803e2310103357b5e985f5437f32
ARG SEEDVR_SHA=4490bd1f482e026674543386bb2a4d176da245b9
ARG VFI_SHA=26545cc2dd95bc3d27f056016300673bdeee78f5

RUN set -eux; cd /comfyui/custom_nodes; \
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git   && cd ComfyUI-VideoHelperSuite   && git checkout ${VHS_SHA}  && cd ..; \
    git clone https://github.com/kijai/ComfyUI-KJNodes.git                  && cd ComfyUI-KJNodes            && git checkout ${KJ_SHA}   && cd ..; \
    git clone https://github.com/kijai/ComfyUI-WanAnimatePreprocess.git     && cd ComfyUI-WanAnimatePreprocess && git checkout ${WAP_SHA} && cd ..; \
    git clone https://github.com/kijai/ComfyUI-segment-anything-2.git       && cd ComfyUI-segment-anything-2  && git checkout ${SAM2_SHA} && cd ..; \
    git clone https://github.com/Fannovel16/ComfyUI-Frame-Interpolation.git && cd ComfyUI-Frame-Interpolation && git checkout ${VFI_SHA}  && cd ..; \
    git clone https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler.git   && cd ComfyUI-SeedVR2_VideoUpscaler  && git checkout ${SEEDVR_SHA} && cd ..; \
    rm -rf */.git

# The node packs' own dependencies, then onnxruntime on the GPU: ViTPose and the
# YOLO detector are ONNX, and on CPU they cost more than the diffusion does.
RUN set -eux; \
    for r in /comfyui/custom_nodes/*/requirements.txt; do \
      [ -f "$r" ] && uv pip install -r "$r"; \
    done; \
    uv pip install -r /comfyui/custom_nodes/ComfyUI-Frame-Interpolation/requirements-no-cupy.txt; \
    uv pip install "onnxruntime-gpu>=1.20" imageio-ffmpeg

# Adds diffusion_models, text_encoders, detection and sam2 to the folders read
# off the network volume; the stock file lists none of them.
COPY extra_model_paths.yaml /comfyui/extra_model_paths.yaml

# Video in by URL, video out to Supabase.
COPY handler.py /handler.py

# Same smoke test the base image runs: import the whole node graph on CPU, so a
# node pack that cannot even load fails the build instead of a live worker.
RUN cd /comfyui && timeout 600 python main.py --quick-test-for-ci --cpu
