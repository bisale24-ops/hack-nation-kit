"""Turn a script module into a narrated demo video. No presenter, no screen recording.

    ~/.venvs/video/bin/python kit/video/render.py video/script.py --out demo.mp4
    ~/.venvs/video/bin/python kit/video/render.py video/script.py --length-only

A script module supplies SCENES and the material each scene needs; everything below is the
machinery. Two rules the machinery enforces, because both have cost a submission before:

  * narration files are named by the hash of their text, so editing one line regenerates that
    line and only that line — an index-named cache silently keeps the old audio;
  * --max-seconds fails the build instead of producing a video that is over the limit.
"""
import argparse
import asyncio
import base64
import hashlib
import importlib.util
import pathlib
import re
import shutil
import subprocess
import sys

DEFAULT_STYLE = """
 body { margin:0; width:%(W)dpx; height:%(H)dpx; background:#fbfaf7; color:#1a1a18;
   font:20px/1.5 system-ui,-apple-system,sans-serif; display:flex; flex-direction:column;
   justify-content:center; padding:0 64px; box-sizing:border-box; }
 body:has(img.page) { padding:0 12px; }
 h1 { font-size:40px; margin:0 0 6px; letter-spacing:-.02em; }
 .sub { color:#6b6a64; margin:0 0 26px; font-size:22px; }
 table { border-collapse:collapse; font-size:19px; width:100%%; }
 td, th { text-align:left; padding:8px 12px; border-bottom:1px solid #e2e0d8; vertical-align:top; }
 th { font-size:14px; text-transform:uppercase; letter-spacing:.06em; color:#6b6a64; }
 .ok { color:#2f6f45; font-weight:600; } .no { color:#8a5a12; font-weight:600; }
 .d { color:#6b6a64; font-weight:600; }
 .big { font-size:28px; } .foot { color:#6b6a64; font-size:16px; margin-top:22px; }
 pre { font:17px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; background:#fff;
   border:1px solid #e2e0d8; border-left:3px solid #8a5a12; border-radius:10px;
   padding:16px 18px; margin:0; white-space:pre-wrap; }
 code { font-family:ui-monospace,Menlo,monospace; }
 img.page { width:100%%; height:auto; max-height:690px; object-fit:contain;
   border:1px solid #e2e0d8; border-radius:12px; background:#fff; }
 .term { background:#14140f; color:#eceae2; border-radius:12px; padding:22px 24px;
   font:16px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace; white-space:pre-wrap;
   overflow:hidden; height:%(TERM)dpx; box-sizing:border-box; }
 .term b { color:#fff; } .term .g { color:#7fc79a; } .term .a { color:#e0b063; }
 .term .d { color:#9a988e; } .term .p { color:#7fc79a; }
"""

PAGE = "<!doctype html><meta charset=utf-8><style>%s</style>%s"


def load_script(path):
    path = pathlib.Path(path).resolve()
    spec = importlib.util.spec_from_file_location("demo_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HERE = path.parent
    for name, default in (("W", 1280), ("H", 720), ("FPS", 30),
                          ("VOICE", "en-US-AndrewNeural"), ("CARDS", {}),
                          ("SHELL", {}), ("IMAGES", {}), ("STYLE", None),
                          ("BACKGROUND", "0xfbfaf7"), ("TAIL", 0.8)):
        if not hasattr(module, name):
            setattr(module, name, default)
    if not getattr(module, "SCENES", None):
        raise SystemExit("%s defines no SCENES" % path)
    return module


def check_scenes(script):
    """Every scene must point at material that exists. Found now, not after eleven renders."""
    problems = []
    for frame, line in script.SCENES:
        if ":" not in frame:
            problems.append("%r is not kind:name" % frame)
            continue
        kind, name = frame.split(":", 1)
        table = {"card": script.CARDS, "term": script.SHELL, "shot": script.IMAGES}.get(kind)
        if table is None:
            problems.append("%r: unknown kind %r (card, term, shot)" % (frame, kind))
        elif name not in table:
            problems.append("%r: nothing named %r in %s" % (frame, name, kind.upper()))
        if not line.strip():
            problems.append("%r has no narration" % frame)
    for name, entry in script.SHELL.items():
        source = script.HERE / "shots" / entry[1]
        if not source.exists():
            problems.append("term:%s reads %s, which does not exist" % (name, source))
    for name, relative in script.IMAGES.items():
        if not (script.HERE / relative).exists():
            problems.append("shot:%s is %s, which does not exist" % (name, relative))
    if problems:
        raise SystemExit("the script does not hold together:\n  " + "\n  ".join(problems))


def shell_html(script, command, source, start=None, end=None):
    text = (script.HERE / "shots" / source).read_text(encoding="utf-8",
                                                      errors="replace").splitlines()
    if start is None:
        start, end = 0, len(text)
    body = []
    for piece in (command.split("\n") if command else []):
        body.append("<span class=p>$</span> <b>%s</b>" % piece.lstrip("$ "))
    if command:
        body.append("")
    for line in text[start:end]:
        escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if re.match(r"^[A-Z][A-Z ]{2,}", line):
            escaped = "<b>%s</b>" % escaped
        elif line.startswith("      "):
            escaped = "<span class=d>%s</span>" % escaped
        elif line.startswith("  "):
            escaped = "<span class=a>%s</span>" % escaped
        body.append(escaped)
    return '<div class=term>%s</div>' % "\n".join(body)


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def slot(build, text, voice):
    stamp = hashlib.sha256(("%s\n%s" % (voice, text)).encode("utf-8")).hexdigest()[:16]
    return build / ("line-%s.mp3" % stamp)


def narrate(script, build):
    """One mp3 per line of narration, named by what it says."""
    tts = pathlib.Path(sys.executable).parent / "edge-tts"
    if not tts.exists():
        raise SystemExit("edge-tts not next to %s — run kit/video/setup.sh, then use that "
                         "interpreter" % sys.executable)
    paths = []
    for _, line in script.SCENES:
        target = slot(build, line, script.VOICE)
        if not target.exists():
            subprocess.run([str(tts), "--voice", script.VOICE, "--text", line,
                            "--write-media", str(target)], check=True)
        paths.append(target)
    return paths


async def render_frames(script, build):
    from playwright.async_api import async_playwright

    style = script.STYLE or (DEFAULT_STYLE % {"W": script.W, "H": script.H,
                                              "TERM": script.H - 120})
    async with async_playwright() as play:
        browser = await play.chromium.launch()
        page = await browser.new_page(viewport={"width": script.W, "height": script.H},
                                      device_scale_factor=2)
        for name, body in script.CARDS.items():
            await page.set_content(PAGE % (style, body))
            await page.screenshot(path=str(build / ("card-%s.png" % name)))
        for name, entry in script.SHELL.items():
            await page.set_content(PAGE % (style, shell_html(script, *entry)))
            await page.screenshot(path=str(build / ("term-%s.png" % name)))
        for name, relative in script.IMAGES.items():
            # embedded, not linked: set_content will not load a file:// image
            raw = (script.HERE / relative).resolve().read_bytes()
            kind = "png" if relative.lower().endswith(".png") else "jpeg"
            data = "data:image/%s;base64,%s" % (kind, base64.b64encode(raw).decode())
            await page.set_content(PAGE % (style, '<img class=page src="%s">' % data))
            await page.wait_for_selector("img.page")
            await page.screenshot(path=str(build / ("shot-%s.png" % name)))
        await browser.close()


def build_video(script, build, out):
    segments = []
    for index, ((frame, line), audio) in enumerate(zip(script.SCENES,
                                                       narrate(script, build))):
        kind, name = frame.split(":", 1)
        image = build / ("%s-%s.png" % (kind, name))
        segment = build / ("seg-%02d.mp4" % index)
        length = duration(audio) + script.TAIL
        ffmpeg("-loop", "1", "-i", str(image), "-i", str(audio), "-filter_complex",
               "[0:v]scale=%d:%d:force_original_aspect_ratio=decrease,"
               "pad=%d:%d:(ow-iw)/2:0:color=%s,format=yuv420p[v];"
               "[1:a]apad=pad_dur=%s,aresample=48000[a]"
               % (script.W, script.H, script.W, script.H, script.BACKGROUND, script.TAIL),
               "-map", "[v]", "-map", "[a]", "-r", str(script.FPS), "-t", "%.2f" % length,
               "-c:v", "libx264", "-preset", "medium", "-crf", "20",
               "-c:a", "aac", "-b:a", "160k", str(segment))
        segments.append(segment)
    listing = build / "segments.txt"
    listing.write_text("".join("file '%s'\n" % s.name for s in segments))
    ffmpeg("-f", "concat", "-safe", "0", "-i", str(listing),
           "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:v", "copy",
           "-c:a", "aac", "-b:a", "160k", str(out))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("script", help="the module defining SCENES")
    parser.add_argument("--out", default=None, help="where to write the mp4")
    parser.add_argument("--max-seconds", type=float, default=None,
                        help="fail instead of producing a video over the limit")
    parser.add_argument("--length-only", action="store_true",
                        help="narrate and report the length; render nothing")
    parser.add_argument("--fresh", action="store_true", help="discard the build directory first")
    args = parser.parse_args(argv)

    for binary in ("ffmpeg", "ffprobe"):
        if not shutil.which(binary):
            raise SystemExit("%s is not on PATH" % binary)

    script = load_script(args.script)
    check_scenes(script)
    build = script.HERE / "build"
    if args.fresh and build.exists():
        shutil.rmtree(build)
    build.mkdir(parents=True, exist_ok=True)

    if args.length_only:
        total, words = 0.0, 0
        for (frame, line), audio in zip(script.SCENES, narrate(script, build)):
            length = duration(audio) + script.TAIL
            total += length
            words += len(line.split())
            flag = "  <- long" if length > 25 else ""
            print("%6.1fs  %3d words  %-18s %s…%s"
                  % (length, len(line.split()), frame, line[:44], flag))
        pace = (words / total) if total else 0
        print("%6.1fs  %3d words  TOTAL (%d scenes, %.1f words per second)"
              % (total, words, len(script.SCENES), pace))
        if args.max_seconds:
            over = total - args.max_seconds
            if over > 0:
                print("cut about %d words to fit" % int(over * pace + 0.5))
                raise SystemExit("over the limit by %.1fs" % over)
            print("%.1fs of room left, about %d words" % (-over, int(-over * pace)))
        return 0

    out = pathlib.Path(args.out) if args.out else script.HERE / "demo.mp4"
    asyncio.run(render_frames(script, build))
    build_video(script, build, out)
    length = duration(out)
    print("%s  %.1fs" % (out, length))
    if args.max_seconds and length > args.max_seconds:
        raise SystemExit("over the limit by %.1fs — shorten the narration and rebuild"
                         % (length - args.max_seconds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
