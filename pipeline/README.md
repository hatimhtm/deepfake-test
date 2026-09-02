# The self-hosted route

Kling motion control on kie.ai takes the *scene* from the reference image, not
just the face. Feed it a portrait of the persona and you get her in the wrong
room with the props gone — the McDonald's cone became an empty hand. The way
around it was to composite the persona into a frame of the reel first, which
works but is two generations and a hand-picked frame per clip.

Wan 2.2 Animate has a replacement mode that keeps the driving video's own
background and swaps only the person. That is the reason to self-host it. Per
clip it is also cheaper, but that is the smaller half of the argument.

Measured on a 9.8s reel, 480×832, on one H100: **131s of GPU, ~$0.15**, against
~$0.55 and 250s on the hosted route — and the café, the cups, the table and the
people in the background all survive.

## Running one

    python3 convert.py upstream-graph.json object-info.json workflow.json
    python3 patch.py workflow.json 0 "a woman eating an ice cream cone in a fast food restaurant"

then submit `workflow.json` to the endpoint. The submitting script lives in the
private repo rather than here: it names our endpoint, our bucket and the env var
holding a service key, none of which belong in a public one.

`0` means every frame of the reel; a small number caps it, which is what to use
while iterating — 81 frames costs a third of a full clip.

`object-info.json` is what the worker reports about its own nodes. Regenerate it
whenever the image changes:

Send `{"op": "object_info", "nodes": []}` as the job input; the worker answers
with its whole node catalogue.

## Why there is a converter at all

Graphs are drawn in ComfyUI's editor format; `/prompt` only accepts the API
format. Converting between them needs each node's true input names, and there
are three traps that all produce a graph which *validates* and then does the
wrong thing:

* `object_info` returns the input dictionary **alphabetically sorted**. It is
  not the order the widget values are stored in. Use `input_order`, or `832`
  lands in `crop_position` and the checkpoint name lands in `device`.
* An input marked `forceInput` is a socket, not a widget, and holds no place in
  the positional list. Counting it shifts every later value by one — that is
  how `False` ended up in a `STRING` field called `coordinates_positive` and
  SAM2 died trying to parse it.
* `GetNode`/`SetNode` and reroutes are editor fictions with no API existence.
  A link through one has to be followed to whatever really produced the value.

## Choices worth keeping

* **fp8 `_v2`, not bf16.** Half the size and the version whose face-encoder
  layers are quantised for *native* ComfyUI; the first upload leaves a grid of
  noise on native workflows.
* **The lightx2v 4-step distill LoRA**, with `cfg 1` and the `lcm` sampler.
  This is what makes a clip 131 seconds instead of most of an hour.
* **`sage_attention: disabled`.** The example asks for it; it is a compiled
  package that is not in the image, and asking for it when it is absent is a
  hard failure, not a fallback. Worth adding later for the speed.
* **No `torch.compile`.** It pays for itself on a long-lived server. A
  serverless worker is thrown away after the job, so the compile is paid again
  on every cold start and never amortised.

## Known flaw

Whatever the subject holds is inside the character mask, so it is regenerated
rather than kept — across ten seconds the ice cream cone drifts into a red cup
and back. The background never wavers; it is only what is in the hands.
