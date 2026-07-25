#!/usr/bin/env python3
"""Structural validator for a generated ComfyUI save-format graph."""
import json
import sys

wf = json.load(open(sys.argv[1], encoding="utf-8"))
nodes = {n["id"]: n for n in wf["nodes"]}
links = {l[0]: l for l in wf["links"]}
errs = []

if len(links) != len(wf["links"]):
    errs.append("duplicate link ids")

for n in wf["nodes"]:
    for i, inp in enumerate(n.get("inputs", [])):
        lid = inp.get("link")
        if lid is None:
            continue
        if lid not in links:
            errs.append(f"node {n['id']} input {i} -> missing link {lid}")
            continue
        l = links[lid]
        if l[3] != n["id"] or l[4] != i:
            errs.append(f"link {lid} target mismatch on node {n['id']} slot {i}")
    for s, out in enumerate(n.get("outputs", [])):
        for lid in out.get("links", []):
            if lid not in links:
                errs.append(f"node {n['id']} output {s} -> missing link {lid}")
                continue
            l = links[lid]
            if l[1] != n["id"] or l[2] != s:
                errs.append(f"link {lid} source mismatch on node {n['id']} slot {s}")

for lid, l in links.items():
    if l[1] not in nodes or l[3] not in nodes:
        errs.append(f"link {lid} references unknown node")

anchor = min(nodes)

def sources(nid):
    return [l[1] for l in wf["links"] if l[3] == nid]

def reaches_anchor(nid, seen=None):
    seen = set() if seen is None else seen
    if nid == anchor:
        return True
    if nid in seen:
        return False
    seen.add(nid)
    return any(reaches_anchor(s, seen) for s in sources(nid))

saves = [n for n in wf["nodes"] if n["type"] == "SaveImage"]
for s in saves:
    if not reaches_anchor(s["id"]):
        errs.append(f"SaveImage {s['id']} ({s['widgets_values'][0]}) not chained to anchor")

# every Nano Banana except the anchor must have a reference image wired in
for n in wf["nodes"]:
    if n["type"] == "GeminiNanoBanana2" and n["id"] != anchor:
        if n["inputs"][0]["link"] is None:
            errs.append(f"node {n['id']} ({n['title']}) has NO reference image — it would re-roll style")

print(f"nodes {len(wf['nodes'])}  links {len(wf['links'])}  plates {len(saves)}")
print("ERRORS:" if errs else "graph OK — every plate chains back to the master anchor")
for e in errs:
    print(" -", e)
sys.exit(1 if errs else 0)
