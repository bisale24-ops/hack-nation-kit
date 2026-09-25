"""The video renderer's own checks. No browser, no encoder, no network.

render.py imports playwright inside the function that needs it, so everything below runs on a
bare interpreter with pytest and nothing else.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "video"))

import render  # noqa: E402


def script_at(tmp_path, body, shots=(), images=()):
    (tmp_path / "shots").mkdir(exist_ok=True)
    for name, text in shots:
        (tmp_path / "shots" / name).write_text(text)
    for name in images:
        (tmp_path / name).write_bytes(b"\x89PNG\r\n\x1a\n")
    path = tmp_path / "script.py"
    path.write_text(body)
    return render.load_script(path)


def test_a_script_without_scenes_is_refused(tmp_path):
    with pytest.raises(SystemExit):
        script_at(tmp_path, "SCENES = []")


def test_defaults_are_filled_in(tmp_path):
    script = script_at(tmp_path, 'SCENES = [("card:a", "x")]\nCARDS = {"a": "<h1>a</h1>"}')
    assert (script.W, script.H, script.FPS) == (1280, 720, 30)
    assert script.VOICE.startswith("en-")
    assert script.HERE == tmp_path


def test_a_scene_pointing_at_nothing_is_named(tmp_path):
    script = script_at(tmp_path, 'SCENES = [("card:ghost", "x")]')
    with pytest.raises(SystemExit) as raised:
        render.check_scenes(script)
    assert "ghost" in str(raised.value)


def test_a_scene_without_narration_is_named(tmp_path):
    script = script_at(tmp_path, 'SCENES = [("card:a", "  ")]\nCARDS = {"a": "x"}')
    with pytest.raises(SystemExit) as raised:
        render.check_scenes(script)
    assert "no narration" in str(raised.value)


def test_a_malformed_frame_is_named(tmp_path):
    script = script_at(tmp_path, 'SCENES = [("title", "x")]')
    with pytest.raises(SystemExit) as raised:
        render.check_scenes(script)
    assert "kind:name" in str(raised.value)


def test_an_unknown_kind_is_named(tmp_path):
    script = script_at(tmp_path, 'SCENES = [("video:a", "x")]')
    with pytest.raises(SystemExit) as raised:
        render.check_scenes(script)
    assert "unknown kind" in str(raised.value)


def test_a_missing_capture_file_is_named(tmp_path):
    script = script_at(tmp_path,
                       'SCENES = [("term:a", "x")]\nSHELL = {"a": ("$ run", "gone.txt")}')
    with pytest.raises(SystemExit) as raised:
        render.check_scenes(script)
    assert "gone.txt" in str(raised.value)


def test_a_missing_image_is_named(tmp_path):
    script = script_at(tmp_path,
                       'SCENES = [("shot:a", "x")]\nIMAGES = {"a": "nowhere.png"}')
    with pytest.raises(SystemExit) as raised:
        render.check_scenes(script)
    assert "nowhere.png" in str(raised.value)


def test_every_problem_is_reported_at_once_not_one_per_run(tmp_path):
    script = script_at(tmp_path, 'SCENES = [("card:ghost", "x"), ("nope", "y")]')
    with pytest.raises(SystemExit) as raised:
        render.check_scenes(script)
    assert "ghost" in str(raised.value) and "nope" in str(raised.value)


def test_a_sound_script_passes(tmp_path):
    script = script_at(tmp_path,
                       'SCENES = [("card:a", "one"), ("term:b", "two"), ("shot:c", "three")]\n'
                       'CARDS = {"a": "<h1>a</h1>"}\n'
                       'SHELL = {"b": ("$ run", "b.txt")}\n'
                       'IMAGES = {"c": "c.png"}',
                       shots=[("b.txt", "output")], images=["c.png"])
    assert render.check_scenes(script) is None


# ---- the terminal frame -------------------------------------------------------------------

def test_captured_output_is_escaped_not_interpreted(tmp_path):
    script = script_at(tmp_path, 'SCENES = [("term:b", "x")]\nSHELL = {"b": ("", "b.txt")}',
                       shots=[("b.txt", "a <script>alert(1)</script> & b")])
    html = render.shell_html(script, "", "b.txt")
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html and "&amp;" in html


def test_the_command_line_is_shown_above_the_output(tmp_path):
    script = script_at(tmp_path, 'SCENES = [("term:b", "x")]\nSHELL = {"b": ("", "b.txt")}',
                       shots=[("b.txt", "result")])
    html = render.shell_html(script, "$ ./run.sh --repo .", "b.txt")
    assert html.index("./run.sh") < html.index("result")


def test_a_slice_of_the_output_can_be_shown(tmp_path):
    script = script_at(tmp_path, 'SCENES = [("term:b", "x")]\nSHELL = {"b": ("", "b.txt")}',
                       shots=[("b.txt", "one\ntwo\nthree\nfour")])
    html = render.shell_html(script, "", "b.txt", 1, 3)
    assert "two" in html and "three" in html and "four" not in html


def test_invalid_bytes_in_a_capture_do_not_stop_the_build(tmp_path):
    (tmp_path / "shots").mkdir()
    (tmp_path / "shots" / "b.txt").write_bytes(b"ok \xff\xfe still ok")
    script = script_at(tmp_path, 'SCENES = [("term:b", "x")]\nSHELL = {"b": ("", "b.txt")}')
    assert "still ok" in render.shell_html(script, "", "b.txt")


# ---- narration cache ----------------------------------------------------------------------

def test_the_same_line_in_the_same_voice_is_the_same_file(tmp_path):
    assert render.slot(tmp_path, "hello", "v") == render.slot(tmp_path, "hello", "v")


def test_an_edited_line_is_a_different_file(tmp_path):
    assert render.slot(tmp_path, "hello", "v") != render.slot(tmp_path, "hello.", "v")


def test_a_different_voice_is_a_different_file(tmp_path):
    assert render.slot(tmp_path, "hello", "a") != render.slot(tmp_path, "hello", "b")
