#!/usr/bin/env python3
"""Builds lists.json for TV Clean: every TV list in the Clean Your TV project.

  build_lists.py <reviewed profiles.json> <cleanyourtv examples dir> <out lists.json>
                 [--app-release vX.Y.Z] [--community-commit SHA]

When <out> already holds the same lists (ignoring the build time), it is left as it is, so the daily
job only publishes real changes.

The reviewed lists are the CleanYourTV Android app's profiles.json (taken from its release APK), used
as they are. Every other examples/<folder>/debloat.txt is converted here: its packages become "your
choice" groups (nothing pre-ticked), its header's keep list becomes neverDisable, and its model codes
and device codename (from tv.json and the header) become the match. Both sources are MIT licensed.
"""
import argparse
import datetime
import json
import os
import re
import sys

PACKAGE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")
PACKAGE_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+)\s*(?:#\s?(.*))?$")
DECORATION = re.compile(r"^[-=*\s]+|[-=*\s]+$")
PKG_TOKEN = re.compile(r"(?<![A-Za-z0-9_./-])([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+)(?![A-Za-z0-9_*/-]|\.[A-Za-z*])")
LIKELY_PACKAGE = re.compile(r"^(com|org|net|tv|android|in|co|io|de|jp|cn|air|mitv|ai)\..+")
SDK_OF_RELEASE = {"5": 21, "5.1": 22, "6": 23, "7": 24, "7.1": 25, "8": 26, "8.0": 26, "8.1": 27, "9": 28,
                  "10": 29, "11": 30, "12": 31, "13": 33, "14": 34, "15": 35, "16": 36}
# Words that follow "model"/"device" in the free text but are not identifiers.
NOT_IDS = {"smart_tv", "smart", "android", "google", "tv", "box", "name", "number", "family", "is", "the",
           "and", "with", "from", "built", "board", "reports", "reported", "string", "a", "an", "of",
           "names", "codename", "codenames", "id", "ids"}


def comment_text(line):
    return line.lstrip().removeprefix("#").strip()


def scan(text):
    """Header comment lines and package groups, as the Android app's DebloatTxt.scan reads them."""
    header, groups, block = [], [], []
    in_packages = seen_package = False
    for raw in text.split("\n"):
        line = raw.rstrip("\r")
        if not line.strip():
            if not seen_package:
                header += block
            block, in_packages = [], False
            continue
        if line.lstrip().startswith("#"):
            if in_packages and line[0] in " \t":
                more = comment_text(line)
                if more and groups and groups[-1]["entries"]:
                    last = groups[-1]["entries"][-1]
                    last["note"] = " ".join(x for x in (last["note"], more) if x)
                continue
            if in_packages:
                in_packages, block = False, []
            block.append(line)
            continue
        m = PACKAGE_LINE.match(line)
        if not m:
            continue  # not a package or a comment: skip rather than guess
        if not in_packages:
            title = next((t for t in (DECORATION.sub("", comment_text(b)) for b in block) if t), "")
            if block or not groups:
                groups.append({"title": title, "entries": []})
            seen_package, block, in_packages = True, [], True
        groups[-1]["entries"].append({"name": m.group(1), "note": (m.group(2) or "").strip() or None})
    if not seen_package:
        header += block
    return header, groups


def packages_in(s):
    return [p for p in PKG_TOKEN.findall(s) if LIKELY_PACKAGE.match(p) and PACKAGE.match(p)]


def keep_list(header):
    """Packages a header paragraph says to keep (the Android app's keepListIn, simplified)."""
    out, in_keep = [], False
    for line in header:
        t = comment_text(line)
        lower = t.lower().removeprefix("- ")
        starts = re.match(r"^keep\b", lower) or "do not disable" in lower or "must stay enabled" in lower or "keep enabled" in lower
        if starts:
            in_keep = True
        elif in_keep and (not t or re.match(r"^[A-Z][A-Za-z ]{2,40}:", t) or lower.startswith("already ") or re.match(r"^\d+\.\s", t)):
            in_keep = False
        if in_keep:
            out += [p for p in packages_in(t) if p not in out]
    return out


def identifiers(tv_line, header_text):
    """Model codes and device codenames named in the TV's description."""
    text = tv_line + "\n" + header_text
    models, devices = [], []

    def add(lst, v):
        v = v.strip().strip('".,;:)(')
        if len(v) >= 2 and v.lower() not in NOT_IDS and v not in lst:
            lst.append(v)

    for m in re.finditer(r'ro\.product\.model\s*[=:]?\s*"([^"]+)"', text):
        add(models, m.group(1))
    for m in re.finditer(r'\bmodel\s+"([^"]+)"', text):
        add(models, m.group(1))
    for m in re.finditer(r"\bmodel\s+([A-Z0-9][A-Za-z0-9_-]{2,})", text):
        add(models, m.group(1))
    for m in re.finditer(r"\bAFT[A-Z0-9]{2,}\b", text):
        add(models, m.group(0))
    for m in re.finditer(r'ro\.product\.device\s*[=:]?\s*"?([A-Za-z0-9_.-]+)', text):
        add(devices, m.group(1))
    for m in re.finditer(r'\b(?:device|codename)\s+"?([A-Za-z0-9][A-Za-z0-9_.-]+)"?', text):
        add(devices, m.group(1))
    # A model code in the name itself: "Acer AR55AR2851UDPRO 55\"" (letters and digits, 4 or more).
    for tok in re.findall(r"[A-Za-z0-9-]+", tv_line.split("(")[0]):
        if len(tok) >= 4 and re.search(r"[A-Za-z]", tok) and re.search(r"\d", tok) and not re.fullmatch(r"\d+[pPkK]", tok):
            add(models, tok)
    return models, devices


def sdk_of(header_text):
    m = re.search(r"\((?:SDK|API)\s*(\d{2})\)|\b(?:SDK|API)\s+(\d{2})\b", header_text)
    if m:
        return int(m.group(1) or m.group(2))
    m = re.search(r"(?:Android TV|Google TV|Android)\s+(\d{1,2}(?:\.\d)?)", header_text)
    if m:
        v = m.group(1)
        return SDK_OF_RELEASE.get(v) or SDK_OF_RELEASE.get(v.split(".")[0])
    return None


def convert(folder, path):
    text = open(os.path.join(path, "debloat.txt"), encoding="utf-8").read()
    header, groups = scan(text)
    if not any(g["entries"] for g in groups):
        return None, "no package lines"
    tv = {}
    if os.path.isfile(os.path.join(path, "tv.json")):
        tv = json.load(open(os.path.join(path, "tv.json"), encoding="utf-8"))
    header_text = "\n".join(comment_text(h) for h in header)
    title = (tv.get("tv") or (comment_text(header[0]) if header else folder)).strip()
    models, devices = identifiers(tv.get("tv", ""), header_text)
    if not models and not devices:
        return None, "no model code or device codename in its description"
    sdk = sdk_of(header_text)
    stock = []
    for h in header:
        if "stock launcher" in h.lower():
            stock += [p + "/" for p in packages_in(h) if p + "/" not in stock]
    seen, out_groups = set(), []
    for i, g in enumerate(groups, 1):
        entries = []
        for e in g["entries"]:
            if e["name"] in seen:
                continue
            seen.add(e["name"])
            entries.append(e)
        if entries:
            out_groups.append({"id": f"community-{i}", "title": g["title"] or "On this TV's list",
                               "default": "ASK", "packages": entries})
    brand = folder.split("-")[0]
    return {
        "id": folder,
        "title": title,
        "reviewed": False,
        "match": {"models": models, "devices": devices, "brand": None, "brandHint": brand,
                  "sdkMin": sdk, "sdkMax": sdk, "fingerprintPrefix": None},
        "stockLaunchers": stock,
        "neverDisable": keep_list(header),
        "groups": out_groups,
    }, None


def validate(bundle, reviewed_count):
    problems = []
    if bundle.get("schema") != 1:
        problems.append("schema is not 1")
    ids = [p["id"] for p in bundle["profiles"]]
    if len(ids) != len(set(ids)):
        problems.append("duplicate ids")
    if sum(1 for p in bundle["profiles"] if p.get("reviewed", True)) != reviewed_count:
        problems.append("reviewed lists changed in conversion")
    for p in bundle["profiles"]:
        m = p["match"]
        if not (m.get("models") or m.get("devices")):
            problems.append(f"{p['id']}: matches no TV")
        for g in p["groups"]:
            if g["default"] not in ("DISABLE", "ASK", "KEEP"):
                problems.append(f"{p['id']}: bad default {g['default']}")
            for e in g["packages"]:
                if not PACKAGE.match(e["name"]):
                    problems.append(f"{p['id']}: bad package {e['name']!r}")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("reviewed")
    ap.add_argument("examples")
    ap.add_argument("out")
    ap.add_argument("--app-release", default=None)
    ap.add_argument("--community-commit", default=None)
    args = ap.parse_args()

    reviewed = json.load(open(args.reviewed, encoding="utf-8"))
    profiles = []
    for p in reviewed["profiles"]:
        p = dict(p)
        p["reviewed"] = True
        tv_json = os.path.join(args.examples, p["id"], "tv.json")
        if os.path.isfile(tv_json):
            p["title"] = json.load(open(tv_json, encoding="utf-8")).get("tv")
        profiles.append(p)
    have = {p["id"] for p in profiles}
    skipped = {}
    for folder in sorted(os.listdir(args.examples)):
        path = os.path.join(args.examples, folder)
        if folder in have or not os.path.isfile(os.path.join(path, "debloat.txt")):
            continue
        profile, why = convert(folder, path)
        if profile:
            profiles.append(profile)
        else:
            skipped[folder] = why

    bundle = {
        "schema": 1,
        "upstreamCommit": reviewed.get("upstreamCommit"),
        "communityCommit": args.community_commit,
        "appRelease": args.app_release,
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "profiles": profiles,
        "skipped": skipped,
    }
    problems = validate(bundle, len(reviewed["profiles"]))
    if problems:
        print("\n".join(problems[:50]), file=sys.stderr)
        sys.exit(1)
    community = len(profiles) - len(reviewed["profiles"])
    if os.path.isfile(args.out):
        old = json.load(open(args.out, encoding="utf-8"))
        old.pop("generated", None)
        if old == {k: v for k, v in bundle.items() if k != "generated"}:
            print(f"unchanged: {len(profiles)} TVs")
            return
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(profiles)} TVs: {len(reviewed['profiles'])} reviewed, {community} community, {len(skipped)} skipped")
    for k, v in skipped.items():
        print(f"  skipped {k}: {v}")


if __name__ == "__main__":
    main()
