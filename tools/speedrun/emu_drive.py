#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Tiny uiautomator-based driver for the Android emulator.

Robust element taps by text / content-desc / resource-id regex (not blind
coordinates), used to drive the real AnkiDroid emulator for the on-device
two-way sync validation (rubric 7b). Keeps the phone side a genuine "user
workflow": open deck, show answer, grade, sync.

    emu_drive.py ui                       # list clickable/labelled nodes
    emu_drive.py find   <regex>           # print center xy of first match
    emu_drive.py tap    <regex>           # tap center of first match
    emu_drive.py tapxy  <x> <y>
    emu_drive.py wait   <regex> [secs]    # wait until a match appears
    emu_drive.py exists <regex>           # exit 0 if present, 1 if not
    emu_drive.py shot   <path>            # screenshot
    emu_drive.py text   <regex>           # print texts of matching nodes
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time

ADB = os.path.join(
    os.environ.get("ANDROID_HOME", os.path.expanduser("~/Library/Android/sdk")),
    "platform-tools",
    "adb",
)


def adb(*args: str, binary: bool = False):
    out = subprocess.run([ADB, *args], check=False, capture_output=True)
    if binary:
        return out.stdout
    return out.stdout.decode("utf-8", "replace")


def dump_nodes() -> list[dict]:
    """Return parsed uiautomator nodes: text, desc, rid, clickable, center."""
    # Retry: uiautomator occasionally races with animations.
    xml = ""
    for _ in range(4):
        adb("shell", "uiautomator", "dump", "/sdcard/ui.xml")
        xml = adb("shell", "cat", "/sdcard/ui.xml")
        if "<node" in xml:
            break
        time.sleep(0.4)
    nodes = []
    for m in re.finditer(r"<node ([^>]*?)/?>", xml):
        tag = m.group(1)

        def attr(n: str) -> str:
            mm = re.search(n + r'="([^"]*)"', tag)
            return mm.group(1) if mm else ""

        bounds = attr("bounds")
        b = re.findall(r"\d+", bounds)
        cx = cy = -1
        if len(b) == 4:
            cx = (int(b[0]) + int(b[2])) // 2
            cy = (int(b[1]) + int(b[3])) // 2
        nodes.append(
            {
                "text": attr("text"),
                "desc": attr("content-desc"),
                "rid": attr("resource-id"),
                "clickable": attr("clickable") == "true",
                "bounds": bounds,
                "cx": cx,
                "cy": cy,
            }
        )
    return nodes


def match(nodes: list[dict], pattern: str) -> list[dict]:
    rx = re.compile(pattern, re.I)
    hits = []
    for n in nodes:
        for field in ("text", "desc", "rid"):
            if n[field] and rx.search(n[field]):
                hits.append(n)
                break
    return hits


def main() -> int:  # noqa: PLR0911
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]

    if cmd == "shot":
        path = sys.argv[2]
        data = adb("exec-out", "screencap", "-p", binary=True)
        with open(path, "wb") as f:
            f.write(data)
        print(f"saved {path} ({len(data)} bytes)")
        return 0

    if cmd == "tapxy":
        x, y = sys.argv[2], sys.argv[3]
        adb("shell", "input", "tap", x, y)
        print(f"tapped ({x},{y})")
        return 0

    if cmd == "ui":
        for n in dump_nodes():
            if n["text"] or n["desc"] or (n["rid"] and n["clickable"]):
                label = n["text"] or n["desc"] or n["rid"].split("/")[-1]
                flag = "C" if n["clickable"] else " "
                print(f"[{flag}] '{label[:44]}' ({n['cx']},{n['cy']}) {n['bounds']}")
        return 0

    pattern = sys.argv[2]

    if cmd == "wait":
        timeout = float(sys.argv[3]) if len(sys.argv) > 3 else 15.0
        deadline = time.time() + timeout
        while time.time() < deadline:
            if match(dump_nodes(), pattern):
                print(f"found: {pattern}")
                return 0
            time.sleep(0.6)
        print(f"TIMEOUT waiting for: {pattern}", file=sys.stderr)
        return 1

    nodes = dump_nodes()
    hits = match(nodes, pattern)

    if cmd == "exists":
        print("yes" if hits else "no")
        return 0 if hits else 1

    if cmd == "text":
        for n in hits:
            print(n["text"] or n["desc"] or n["rid"])
        return 0 if hits else 1

    if cmd == "find":
        if not hits:
            print(f"NOT FOUND: {pattern}", file=sys.stderr)
            return 1
        n = hits[0]
        print(f"{n['cx']} {n['cy']}  ('{(n['text'] or n['desc'])[:40]}')")
        return 0

    if cmd == "tap":
        # prefer a clickable match, else first match
        clickable = [n for n in hits if n["clickable"]]
        chosen = clickable or hits
        if not chosen:
            print(f"NOT FOUND: {pattern}", file=sys.stderr)
            return 1
        n = chosen[0]
        adb("shell", "input", "tap", str(n["cx"]), str(n["cy"]))
        print(f"tapped '{(n['text'] or n['desc'])[:40]}' at ({n['cx']},{n['cy']})")
        return 0

    print(f"unknown cmd: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
