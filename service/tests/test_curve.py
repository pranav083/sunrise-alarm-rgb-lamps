import pytest
from sunlight.curve import curve, floor_values


def test_endpoints_match_keyframes():
    assert curve(0.0) == pytest.approx((80, 0, 0, 0.005))
    assert curve(1.0) == pytest.approx((255, 220, 150, 1.0))


def test_keyframe_in_middle_is_exact():
    assert curve(0.50) == pytest.approx((255, 95, 5, 0.18))


def test_clamps_out_of_range():
    assert curve(-1) == curve(0.0)
    assert curve(2) == curve(1.0)


def test_brightness_monotonic():
    values = [curve(i / 200)[3] for i in range(201)]
    assert values == sorted(values)


def test_smoothstep_midpoint_between_keyframes():
    # between p=0.00 (R=80) and p=0.10 (R=140); smoothstep(0.5)=0.5 -> 110
    assert curve(0.05)[0] == pytest.approx(110)


def test_floor_values_calibrates_green_and_blue():
    r, g, b, pct = floor_values(255, 100, 100, 1.0)
    assert (r, g, b, pct) == (255, 30, 60, 100)


def test_floor_values_fine_dimming_below_one_percent():
    # 0.5% -> pct 1, RGB scaled by 0.5
    assert floor_values(80, 0, 0, 0.005) == (40, 0, 0, 1)


def test_floor_values_pct_is_ceiling():
    r, g, b, pct = floor_values(200, 0, 0, 0.041)   # 4.1% -> pct 5, k = 0.82
    assert pct == 5 and r == round(200 * 0.82)
