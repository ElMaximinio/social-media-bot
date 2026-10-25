from bot.edit import pick_cuts
from bot.voice import words_from_alignment


def test_words_from_alignment():
    al = {"characters": list("Hi you"),
          "character_start_times_seconds": [0, .1, .2, .3, .4, .5],
          "character_end_times_seconds": [.1, .2, .3, .4, .5, .6]}
    assert words_from_alignment(al) == [
        {"word": "Hi", "start": 0, "end": .2},
        {"word": "you", "start": .3, "end": .6},
    ]


def test_cuts():
    cuts = pick_cuts([9, 9, 9, 9, 9, 9], peak=2)
    assert cuts["tiktok"] == [0, 1, 2, 3, 4, 5]
    assert cuts["instagram"] == [0, 1, 2, 3, 4]  # stays within 45 s
    assert cuts["x"] == [0, 2]
