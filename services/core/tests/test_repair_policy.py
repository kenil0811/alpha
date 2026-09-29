"""Repairs: a fixed allowance, plus one more while the failing checks keep shrinking."""

from __future__ import annotations

from alpha.builds.service import RepairPolicy


def test_the_allowance_counts_down_when_nothing_improves() -> None:
    policy = RepairPolicy(2)
    assert policy.repairs_left(1, 5) == 2
    assert policy.repairs_left(2, 5) == 1
    assert policy.repairs_left(3, 5) == 0


def test_a_converging_build_earns_one_more_repair_each_time() -> None:
    policy = RepairPolicy(2)
    assert policy.repairs_left(1, 6) == 2
    assert policy.repairs_left(2, 4) == 1
    assert policy.repairs_left(3, 2) == 1, "past the allowance, still shrinking"
    assert policy.repairs_left(4, 1) == 1
    assert policy.repairs_left(5, 1) == 0, "it stalled"


def test_no_repairs_are_ever_offered_for_a_passing_or_stalled_build() -> None:
    policy = RepairPolicy(0)
    assert policy.repairs_left(1, 3) == 0
    assert policy.repairs_left(2, 0) == 0, "nothing failed: nothing to repair"
