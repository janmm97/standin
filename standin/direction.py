"""Film language: turns a plan's shot, angle, camera move, location and look into the prompts every image
and video model gets, so the output reads as a directed film shot instead of a generic AI image."""

from __future__ import annotations

SHOTS = ("wide", "medium", "close", "detail")
ANGLES = ("eye", "low", "high")
# A prime per shot size, as a cinematographer would pick it.
LENS = {"wide": 24, "medium": 35, "close": 50, "detail": 85}
SHOT_TEXT = {
    "wide": "wide establishing shot, full figure small in a deep, layered environment",
    "medium": "medium shot from the waist up",
    "close": "close-up on the face and shoulders",
    "detail": "extreme close-up insert on the hands and the product",
}
ANGLE_TEXT = {"eye": "eye-level", "low": "slightly low angle looking up", "high": "high angle looking down"}
MOVE_TEXT = {
    "static": "locked-off tripod shot",
    "dolly": "slow, smooth dolly push-in",
    "orbit": "slow arc around the subject",
    "handheld": "subtle handheld drift",
}
DEFAULT_LOOK = ("naturalistic, motivated light from a single soft key with gentle falloff, "
                "restrained colour palette, deep blacks, fine 35mm film grain")
CRAFT = ("Photographed on a cinema camera with a {lens}mm prime, shallow depth of field, "
         "realistic skin with pores and texture, real-world materials, believable wardrobe and props")
AVOID = ("Avoid: plastic or airbrushed skin, oversaturated or HDR colour, glowing edges, stock-photo grins, "
         "looking into the lens unless the beat says so, warped hands or extra fingers, "
         "text, captions, logos, watermarks, mannequins.")


def _sentence(*parts: str) -> str:
    return ". ".join(p.strip().rstrip(".") for p in parts if p and p.strip()) + "."


def look(plan: dict) -> str:
    return plan.get("look") or DEFAULT_LOOK


def still_prompt(plan: dict, beat: dict) -> str:
    """One keyframe: framing, lens, angle, world, action and look, then what to avoid."""
    shot = beat.get("shot", "medium")
    lens = LENS.get(shot, 35)
    return _sentence(
        f"Cinematic film still, {SHOT_TEXT.get(shot, SHOT_TEXT['medium'])}, "
        f"{ANGLE_TEXT.get(beat.get('angle'), 'eye-level')}",
        f"Location: {plan['location']}" if plan.get("location") else "",
        beat.get("scene", ""),
        f"Look: {look(plan)}",
        CRAFT.format(lens=lens),
    ) + " " + AVOID


def motion_prompt(plan: dict, beat: dict) -> str:
    """One video segment between two keyframes: the move, the action, continuity, the look."""
    return _sentence(
        f"{MOVE_TEXT.get(beat.get('camera'), MOVE_TEXT['static']).capitalize()}, "
        f"{SHOT_TEXT.get(beat.get('shot', 'medium'), SHOT_TEXT['medium'])}",
        beat.get("scene", ""),
        "Natural, unhurried human motion with weight; keep faces, wardrobe, light and set identical "
        "to the first frame",
        f"Look: {look(plan)}",
    ) + " " + AVOID


def cast_prompt(plan: dict, member: dict) -> str:
    """A casting still: the actor on their own, in the film's light, used as an identity reference."""
    return _sentence(
        f"Casting photo, full body, of {member.get('look') or 'an actor'}, "
        "standing naturally, neutral expression",
        "Plain seamless backdrop, soft large key light from the side",
        f"Colour and grade matching: {look(plan)}",
        CRAFT.format(lens=50),
    ) + " " + AVOID
