"""Copy this next to the project as video/script.py and replace every line.

    ~/.venvs/video/bin/python kit/video/render.py video/script.py --length-only
    ~/.venvs/video/bin/python kit/video/render.py video/script.py --out video/demo.mp4 --max-seconds 175

Narration is prose read aloud, so write out numbers and avoid symbols: "one hundred percent",
not "100%". Terminal frames read files under video/shots/, which must be real captured output.
"""

VOICE = "en-US-AndrewNeural"

SCENES = [
    ("card:title", "This is the smoke test for the video pipeline. If you can hear this "
                   "sentence, the narration, the browser and the encoder all work."),
    ("term:run", "A terminal frame is the tool's real output, read from a file captured by "
                 "running it. Nothing is retyped for the camera."),
    ("shot:page", "And an image frame, embedded rather than linked, because a file URL is not "
                  "loaded by the page."),
]

CARDS = {
    "title": """<h1>Video pipeline</h1>
    <p class=sub>Three kinds of frame, one narrated track, no presenter.</p>
    <table>
      <tr><th>frame</th><th>made from</th></tr>
      <tr><td>card</td><td>HTML written in the script</td></tr>
      <tr><td>term</td><td>captured output under shots/</td></tr>
      <tr><td>shot</td><td>a PNG, embedded as a data URI</td></tr>
    </table>""",
}

SHELL = {
    "run": ("$ ./run.sh --repo .", "run.txt"),
}

IMAGES = {
    "page": "page.png",
}
