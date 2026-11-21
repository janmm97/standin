from standin import direction
from standin.plan import DEFAULT_LOOK, normalize


def test_normalize_clamps_film_language():
    p = normalize({"location": "  a  cafe ", "beats": [{"shot": "Close", "angle": "dutch"}, {}]})
    assert [(b["shot"], b["angle"]) for b in p["beats"]] == [("close", "eye"), ("medium", "eye")]
    assert p["location"] == "a cafe" and p["look"] == DEFAULT_LOOK


def test_still_prompt_carries_shot_lens_location_look_and_avoid():
    plan = {"location": "corner cafe at 7am", "look": "cold window key, film grain"}
    s = direction.still_prompt(plan, {"shot": "detail", "angle": "high", "scene": "hand on the cup"})
    for part in ("extreme close-up", "high angle", "corner cafe at 7am", "hand on the cup",
                 "cold window key", "85mm prime", "Avoid:", "mannequins"):
        assert part in s


def test_motion_prompt_names_the_move_and_keeps_continuity():
    m = direction.motion_prompt({}, {"shot": "wide", "camera": "dolly", "scene": "she walks in"})
    assert m.startswith("Slow, smooth dolly push-in, wide establishing shot")
    assert "identical to the first frame" in m and DEFAULT_LOOK in m


def test_cast_prompt_uses_the_film_look():
    c = direction.cast_prompt({"look": "warm tungsten"}, {"look": "woman in her 40s, grey coat"})
    assert "woman in her 40s, grey coat" in c and "warm tungsten" in c and "50mm" in c
