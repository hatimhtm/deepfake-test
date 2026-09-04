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
# Tom Eden's workflows use 175 node types; this worker had 77 of them. These
# are the packs behind the gaps that matter for the lanes we run or want:
# Kijai's Wan wrapper (their I2V engine and T5 loader), the tiling and maths
# helpers their upscale chain is built from, FaceDetailer for face polish, and
# GIMM-VFI, the interpolator they use instead of RIFE.
ARG WVW_SHA=088128b224242e110d3906c6750e9a3a348a659b
ARG ESS_SHA=9d9f4bedfc9f0321c19faf71855e228c93bd0dc9
ARG EASY_SHA=8b522f121d63524baaf6dce51a155edcc980fb59
ARG IMPACT_SHA=429d0159ad429e64d2b3916e6e7be9c22d025c3c
ARG IMPACTSUB_SHA=50c7b71a6a224734cc9b21963c6d1926816a97f1
ARG TTP_SHA=c8889e40e90e293226cc6810c7d27b9c17300da6
ARG GIMM_SHA=4c9a3123762af85e7c796e41737da0b70c75d72d
ARG RGTHREE_SHA=2c5342a8cb0eaecaabf61435a5f37dd594c510ba
ARG INPAINT_SHA=606e2b4fd83fc44e1f0b403e1f076501db8c3749
ARG PYSSSSS_SHA=609f3afaa74b2f88ef9ce8d939626065e3247469
ARG CROLL_SHA=d78b780ae43fcf8c6b7c6505e6ffb4584281ceca
# Second round: the packs behind the last gaps that produce pixels — LayerStyle
# (their scale/reel/person-mask helpers), SparkVSR (the other branch of their
# upscale graph) and the SAM3 pack whose node names match their faceswap
# graphs (PozzettiAndrea's, not yolain's, whose classes are spelled Sam3).
ARG LS_SHA=5ba939099b33f998ecfbd63dcbbf089925b64a47
ARG LSADV_SHA=7b678b401a38307a4a7e99ef6630bd48f9cecedb
ARG SPARK_SHA=30f3378e5ddc172b85c3d8776a02e808f7694c28
ARG SAM3_SHA=de0ff5d2c2ea435d29f800abfa568cffdfb94773

RUN set -eux; cd /comfyui/custom_nodes; \
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git   && cd ComfyUI-VideoHelperSuite   && git checkout ${VHS_SHA}  && cd ..; \
    git clone https://github.com/kijai/ComfyUI-KJNodes.git                  && cd ComfyUI-KJNodes            && git checkout ${KJ_SHA}   && cd ..; \
    git clone https://github.com/kijai/ComfyUI-WanAnimatePreprocess.git     && cd ComfyUI-WanAnimatePreprocess && git checkout ${WAP_SHA} && cd ..; \
    git clone https://github.com/kijai/ComfyUI-segment-anything-2.git       && cd ComfyUI-segment-anything-2  && git checkout ${SAM2_SHA} && cd ..; \
    git clone https://github.com/Fannovel16/ComfyUI-Frame-Interpolation.git && cd ComfyUI-Frame-Interpolation && git checkout ${VFI_SHA}  && cd ..; \
    git clone https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler.git   && cd ComfyUI-SeedVR2_VideoUpscaler  && git checkout ${SEEDVR_SHA} && cd ..; \
    git clone https://github.com/kijai/ComfyUI-WanVideoWrapper.git          && cd ComfyUI-WanVideoWrapper     && git checkout ${WVW_SHA}       && cd ..; \
    git clone https://github.com/cubiq/ComfyUI_essentials.git              && cd ComfyUI_essentials          && git checkout ${ESS_SHA}       && cd ..; \
    git clone https://github.com/yolain/ComfyUI-Easy-Use.git               && cd ComfyUI-Easy-Use            && git checkout ${EASY_SHA}      && cd ..; \
    git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack.git          && cd ComfyUI-Impact-Pack         && git checkout ${IMPACT_SHA}    && cd ..; \
    git clone https://github.com/ltdrdata/ComfyUI-Impact-Subpack.git       && cd ComfyUI-Impact-Subpack      && git checkout ${IMPACTSUB_SHA} && cd ..; \
    git clone https://github.com/TTPlanetPig/Comfyui_TTP_Toolset.git       && cd Comfyui_TTP_Toolset         && git checkout ${TTP_SHA}       && cd ..; \
    git clone https://github.com/kijai/ComfyUI-GIMM-VFI.git                && cd ComfyUI-GIMM-VFI            && git checkout ${GIMM_SHA}      && cd ..; \
    git clone https://github.com/rgthree/rgthree-comfy.git                 && cd rgthree-comfy               && git checkout ${RGTHREE_SHA}   && cd ..; \
    git clone https://github.com/lquesada/ComfyUI-Inpaint-CropAndStitch.git && cd ComfyUI-Inpaint-CropAndStitch && git checkout ${INPAINT_SHA} && cd ..; \
    git clone https://github.com/pythongosssss/ComfyUI-Custom-Scripts.git  && cd ComfyUI-Custom-Scripts      && git checkout ${PYSSSSS_SHA}   && cd ..; \
    git clone https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes.git  && cd ComfyUI_Comfyroll_CustomNodes && git checkout ${CROLL_SHA}   && cd ..; \
    git clone https://github.com/chflame163/ComfyUI_LayerStyle.git         && cd ComfyUI_LayerStyle          && git checkout ${LS_SHA}        && cd ..; \
    git clone https://github.com/chflame163/ComfyUI_LayerStyle_Advance.git && cd ComfyUI_LayerStyle_Advance  && git checkout ${LSADV_SHA}     && cd ..; \
    git clone https://github.com/smthemex/ComfyUI_SparkVSR_SM.git          && cd ComfyUI_SparkVSR_SM         && git checkout ${SPARK_SHA}     && cd ..; \
    git clone https://github.com/PozzettiAndrea/ComfyUI-SAM3.git           && cd ComfyUI-SAM3                && git checkout ${SAM3_SHA}      && cd ..; \
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
