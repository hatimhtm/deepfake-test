"""
Turn a ComfyUI editor graph into the API format /prompt accepts.

The editor format stores widget values as a bare positional list and links as
numbered edges; the API format wants every input named. The names only exist in
the running ComfyUI's object_info, which is why this reads the definitions the
worker reported rather than guessing them.

Two things the naive conversion gets wrong and this does not:

  * A widget can also be an input socket. When it is linked, the link wins and
    the positional list still contains a placeholder for it — so the list and
    the definition's input order drift apart unless you skip in lockstep.
  * Some widgets are followed by a hidden control ("increment"/"randomize")
    that belongs to no input at all, and Get/SetNode and reroutes are editor
    fictions with no API existence; both have to be walked through, not around.
"""

import json
import sys
from collections import defaultdict

EDITOR_ONLY = {"Note", "MarkdownNote", "Reroute", "PrimitiveNode", "PreviewAny", "PreviewImage"}
CONTROLS = {"fixed", "increment", "decrement", "randomize"}


def load(graph_path, oi_path):
    g = json.load(open(graph_path))
    oi = json.load(open(oi_path))
    oi = oi.get("object_info", oi)
    return g, oi


def build(g, oi):
    nodes = {n["id"]: n for n in g["nodes"]}

    # link id -> (origin node id, origin slot)
    links = {}
    for l in g.get("links", []):
        if isinstance(l, list) and len(l) >= 5:
            links[l[0]] = (l[1], l[2])

    # Get/SetNode pass a value across the canvas by name and vanish in the API
    # format, so a GetNode's output has to resolve to whatever fed the matching
    # SetNode.
    set_by_name = {}
    for n in nodes.values():
        if n["type"] == "SetNode":
            name = (n.get("widgets_values") or [None])[0]
            src = (n.get("inputs") or [{}])[0].get("link")
            if name is not None:
                set_by_name[name] = src

    def resolve(link_id, seen=()):
        """Follow a link back past every editor-only node to a real producer."""
        while True:
            if link_id is None or link_id not in links:
                return None
            nid, slot = links[link_id]
            n = nodes.get(nid)
            if n is None:
                return None
            t = n["type"]
            if t == "GetNode":
                name = (n.get("widgets_values") or [None])[0]
                if name in seen:
                    return None
                link_id = set_by_name.get(name)
                seen = seen + (name,)
                continue
            if t in ("Reroute", "SetNode"):
                link_id = (n.get("inputs") or [{}])[0].get("link")
                continue
            return [str(nid), slot]

    api = {}
    for n in nodes.values():
        t = n["type"]
        if t in EDITOR_ONLY or t in ("GetNode", "SetNode"):
            continue
        if n.get("mode") in (2, 4):  # muted or bypassed in the editor
            continue
        spec = oi.get(t)
        if not spec:
            raise SystemExit(f"no definition for node type {t!r}")

        required = spec["input"].get("required", {})
        optional = spec["input"].get("optional", {})
        defs = {**required, **optional}
        # object_info hands the definitions back with the keys sorted
        # alphabetically, which is not the order the widget values are stored
        # in. Reading the dict directly silently shuffles every parameter in the
        # graph — 832 lands in `crop_position`, the checkpoint name lands in
        # `device` — and the result still validates. input_order is the only
        # field that says what the editor actually showed.
        io = spec.get("input_order") or {}
        order = list(io.get("required") or required) + list(io.get("optional") or optional)
        for name in defs:  # anything input_order forgot, appended once
            if name not in order:
                order.append(name)

        linked = {i.get("name"): i.get("link") for i in (n.get("inputs") or [])}
        widgets = list(n.get("widgets_values") or [])
        if isinstance(n.get("widgets_values"), dict):
            widgets = None  # newer editor format: already named

        out = {}
        wi = 0
        for name in order:
            spec_in = defs[name]
            opts = spec_in[1] if len(spec_in) > 1 and isinstance(spec_in[1], dict) else {}
            # forceInput makes a scalar a socket rather than a widget, so it
            # holds no place in the positional list. Counting it shifts every
            # later widget by one — which is how `False` ended up in a STRING
            # field named coordinates_positive and SAM2 tried to parse it.
            is_widget = not opts.get("forceInput") and (
                isinstance(spec_in[0], list)
                or spec_in[0] in ("INT", "FLOAT", "STRING", "BOOLEAN", "COMBO")
            )
            if name in linked and linked[name] is not None:
                r = resolve(linked[name])
                if r is not None:
                    out[name] = r
                # A linked widget still occupies its slot in the positional list.
                if is_widget and widgets is not None:
                    wi += 1
                continue
            if isinstance(n.get("widgets_values"), dict):
                if name in n["widgets_values"]:
                    out[name] = n["widgets_values"][name]
                continue
            if is_widget and widgets is not None and wi < len(widgets):
                out[name] = widgets[wi]
                wi += 1
                # Skip the hidden control that follows a seeded widget.
                if wi < len(widgets) and widgets[wi] in CONTROLS:
                    wi += 1
        # Literals inlined by the prep pass in place of dropped constant nodes.
        for k, v in (n.get("_inline") or {}).items():
            out[k] = v
        api[str(n["id"])] = {"class_type": t, "inputs": out, "_meta": {"title": n.get("title") or t}}

    # Drop anything nothing reaches: the editor keeps parked nodes, /prompt
    # tries to execute them.
    return api


def prune(api):
    """Keep only nodes an output node depends on."""
    OUTPUTS = {"VHS_VideoCombine", "SaveImage", "PreviewImage", "SaveAnimatedWEBP"}
    keep, stack = set(), [k for k, v in api.items() if v["class_type"] in OUTPUTS]
    while stack:
        k = stack.pop()
        if k in keep or k not in api:
            continue
        keep.add(k)
        for v in api[k]["inputs"].values():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                stack.append(v[0])
    return {k: v for k, v in api.items() if k in keep}


if __name__ == "__main__":
    g, oi = load(sys.argv[1], sys.argv[2])
    api = prune(build(g, oi))
    json.dump(api, open(sys.argv[3], "w"), indent=1)
    counts = defaultdict(int)
    for v in api.values():
        counts[v["class_type"]] += 1
    print(f"{len(api)} nodes ->", sys.argv[3])
    for t, c in sorted(counts.items()):
        print(f"  {c}x {t}")
