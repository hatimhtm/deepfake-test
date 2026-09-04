#!/usr/bin/env bash
# Fills the RunPod network volume with everything the Wan 2.2 Animate graph
# loads. Runs on a throwaway CPU pod with the volume mounted at /workspace, so
# the ~29 GB is pulled once at CPU prices and every GPU worker afterwards finds
# it already there.
#
# Every file is picked to match the official example graph rather than the
# biggest available: the fp8 v2 checkpoint instead of the 34 GB bf16 (v2 is the
# one whose face-encoder layers are quantised properly for *native* ComfyUI —
# the earlier upload puts a grid of noise in the output), and the lightx2v
# 4-step distill LoRA, which is what makes a clip cost minutes instead of an
# hour.
#
# Safe to re-run: anything already the right size is skipped.
set -uo pipefail

VOL="${VOL:-/workspace}"
LOG="$VOL/models/_fetch.log"
mkdir -p "$VOL/models"/{diffusion_models,text_encoders,vae,clip_vision,loras,detection,sam2}

say() {
  echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG"
  # Mirror the log out, so progress is visible without shell access to the pod.
  if [ -n "${SUPABASE_URL:-}" ] && [ -n "${SUPABASE_KEY:-}" ]; then
    curl -s -o /dev/null -X POST \
      "$SUPABASE_URL/storage/v1/object/${SUPABASE_BUCKET:-cloneos}/deepfake-test/fetch.log" \
      -H "Authorization: Bearer $SUPABASE_KEY" -H "apikey: $SUPABASE_KEY" \
      -H "Content-Type: text/plain" -H "x-upsert: true" \
      --data-binary "@$LOG" || true
  fi
}

# get <repo> <path-in-repo> <dest-dir> [dest-name]
get() {
  local repo="$1" path="$2" dir="$3" name="${4:-$(basename "$2")}"
  local dest="$VOL/models/$dir/$name"
  local url="https://huggingface.co/$repo/resolve/main/$path"
  # The expected size comes from the final redirect target, so a half-finished
  # file from an earlier run is resumed rather than trusted.
  local want
  want=$(curl -sIL "$url" | tr -d '\r' | awk 'tolower($1)=="content-length:"{n=$2} END{print n+0}')
  if [ -f "$dest" ]; then
    local have; have=$(stat -c%s "$dest" 2>/dev/null || echo 0)
    if [ "$want" -gt 0 ] && [ "$have" -eq "$want" ]; then
      say "have  $dir/$name ($(numfmt --to=iec "$have"))"
      return 0
    fi
  fi
  say "get   $dir/$name ($(numfmt --to=iec "${want:-0}"))"
  curl -fL --retry 5 --retry-delay 5 -C - -o "$dest" "$url" || { say "FAIL  $dir/$name"; return 1; }
  say "ok    $dir/$name ($(numfmt --to=iec "$(stat -c%s "$dest")"))"
}

say "=== volume before ==="
df -h "$VOL" | tail -1 | tee -a "$LOG"
du -sh "$VOL"/* 2>/dev/null | tee -a "$LOG"
say "==="

# Smallest first, so a space problem shows up before 17 GB is spent on it.
get Comfy-Org/Wan_2.1_ComfyUI_repackaged  split_files/clip_vision/clip_vision_h.safetensors            clip_vision
get Comfy-Org/Wan_2.2_ComfyUI_Repackaged  split_files/vae/wan_2.1_vae.safetensors                      vae
get Wan-AI/Wan2.2-Animate-14B             process_checkpoint/det/yolov10m.onnx                         detection
get Kijai/sam2-safetensors                sam2.1_hiera_base_plus.safetensors                           sam2
get JunkyByte/easy_ViTPose                onnx/wholebody/vitpose-l-wholebody.onnx                      detection
get Kijai/WanVideo_comfy                  Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors  loras
get Comfy-Org/Wan_2.2_ComfyUI_Repackaged  split_files/loras/wan2.2_animate_14B_relight_lora_bf16.safetensors        loras
get Comfy-Org/Wan_2.2_ComfyUI_Repackaged  split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors          text_encoders
get Kijai/WanVideo_comfy_fp8_scaled       Wan22Animate/Wan2_2-Animate-14B_fp8_scaled_e4m3fn_KJ_v2.safetensors       diffusion_models

# SCAIL-2 — Tom Eden's character-transfer engine, for an A/B against Wan-Animate.
# fp8 scaled rather than the 33 GB fp16 his graph names; the worker already
# carries every core node it needs. SAM3.1 drives its character mask.
mkdir -p "$VOL/models/checkpoints"
get Comfy-Org/SCAIL-2   diffusion_models/wan2.1_14B_SCAIL_2_fp8_scaled.safetensors   diffusion_models
get Comfy-Org/SCAIL-2   loras/wan2.1_SCAIL_2_DPO_lora_bf16.safetensors               loras
get Comfy-Org/SCAIL-2   loras/wan2.1_SCAIL_2_relight_lora_bf16.safetensors           loras
get Comfy-Org/sam3.1    checkpoints/sam3.1_multiplex_fp16.safetensors                checkpoints

say "=== volume after ==="
df -h "$VOL" | tail -1 | tee -a "$LOG"
find "$VOL/models" -maxdepth 2 -type f -newermt '-1 day' -printf '%10s  %p\n' 2>/dev/null | tee -a "$LOG"
say "=== done ==="
