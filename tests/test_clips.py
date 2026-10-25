import numpy as np

from bot.clips import layout, pick, render, transcribe
from bot.clips.make import caption_with_tags


def W(word, s, e):
    return {"word": word, "start": s, "end": e}


def test_scribe_keeps_words_only():
    data = {"words": [{"text": "Hi", "start": 0, "end": .2, "type": "word"},
                      {"text": " ", "start": .2, "end": .3, "type": "spacing"},
                      {"text": "(laughs)", "start": .3, "end": .9, "type": "audio_event"},
                      {"text": "bro", "start": 1, "end": 1.2, "type": "word"}]}
    assert transcribe.words_from_scribe(data) == [W("Hi", 0, .2), W("bro", 1, 1.2)]


def test_keep_ranges_cuts_long_quiet_gap_only():
    words = [W("a", 0, .5), W("b", .6, 1), W("c", 4, 4.5)]
    quiet = np.full(500, 0.01)
    assert render.keep_ranges(words, 5, quiet) == [(0.0, 1.15), (3.85, 5.0)]
    loud = quiet.copy()
    loud[150:250] = 0.5  # a scream between the words: keep it
    assert render.keep_ranges(words, 5, loud) == [(0.0, 5.0)]


def test_remap_words():
    ranges = [(0.0, 1.0), (3.0, 5.0)]
    assert render.remap(0.5, ranges) == 0.5
    assert render.remap(2.0, ranges) is None
    assert render.remap(3.5, ranges) == 1.5
    assert render.remap_words([W("x", 3.2, 3.4)], ranges) == [W("x", 1.2, 1.4)]


def test_group_words_splits_on_pause_and_length():
    words = [W("no", 0, .2), W("way", .25, .5), W("bro", 1.5, 1.7), W("seriously", 1.75, 2.2)]
    groups = render.group_words(words)
    assert [[w["word"] for w in g] for g in groups] == [["no", "way"], ["bro", "seriously"]]


def test_hook_wrap_and_emoji_strip():
    assert render.wrap_hook("He did NOT expect this answer 😭", 16) == "He did NOT\\Nexpect this\\Nanswer"


def test_piecewise_expr_holds_then_moves():
    e = layout.piecewise_expr([(0, 100), (2, 100), (2.4, 300)])
    t = 1.0
    assert eval(e.replace("if(", "_if(").replace("lt(", "_lt("),
                {"_if": lambda c, a, b: a if c else b, "_lt": lambda a, b: a < b, "t": t}) == 100


def test_track_keyframes_dead_zone():
    faces = {"samples": [(0, [(0.45, .2, .1, .2, .9)]), (.5, [(0.46, .2, .1, .2, .9)]),
                         (1.0, [(0.8, .2, .1, .2, .9)])]}
    keys = layout.track_keyframes(faces, 3400, 1080)
    assert len(keys) == 3 and keys[-1][1] > keys[0][1]


def test_choose_layout():
    cam = {"samples": [(i, [(0.05, 0.8, 0.03, 0.06, .9)]) for i in range(10)]}
    big = {"samples": [(i, [(0.4 + i * .01, 0.2, 0.15, 0.3, .9)]) for i in range(10)]}
    none = {"samples": [(i, []) for i in range(10)]}
    assert layout.choose_layout(cam) == "stack"
    assert layout.choose_layout(big) == "track"
    assert layout.choose_layout(none) == "fit"


def test_gameplay_crop_avoids_left_webcam():
    cam = {"samples": [(i, [(0.08, 0.8, 0.03, 0.06, .9)]) for i in range(5)]}
    x = layout.gameplay_x(cam, 1920, 1080, 1080 / 1120)
    assert x > (1920 - 1041) / 2


def test_snap_to_word_edges():
    words = [W("a", 10.0, 10.3), W("b", 10.4, 10.9), W("c", 30.0, 30.5)]
    out = pick.snap({"start": 10.2, "end": 30.2}, words)
    assert out["start"] == 9.75 and out["end"] == 31.1


def test_required_tags_added_once():
    spec = {"caption": "crazy clip #Kai", "campaign": {"required_tags": ["#kai", "#clips"]}}
    assert caption_with_tags(spec) == "crazy clip #Kai #clips"


def test_subtract_cut_out():
    assert render.subtract([(0.0, 10.0)], [(2.0, 4.0)]) == [(0.0, 2.0), (4.0, 10.0)]
    assert render.subtract([(0.0, 3.0), (5.0, 9.0)], [(2.0, 6.0)]) == [(0.0, 2.0), (6.0, 9.0)]


def test_fit_box_panel_and_caption():
    chain, y = render.layout_filter("fit", 1280, 720, None, [470, 80, 560, 610])
    assert "crop=560:610:470:80" in chain and y < 1920 * 0.8
