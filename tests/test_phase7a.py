"""Phase 7a: the v2 multi-statement held-out group is frozen, digest-checked and disjoint from v1."""

from __future__ import annotations

import json

import pytest


def test_multicell_split_v2_is_frozen_and_holds_out_one_configuration_per_template():
    from benchmarks.multicell import cases_v2, split

    sp = split.load(version=2)
    assert sp.version == 2
    assert len(sp.heldout) == len(cases_v2.TEMPLATES) >= 12
    assert 2 * len(sp.heldout) >= 30  # two sizes per configuration
    assert len(sp.dev) + len(sp.heldout) == len(cases_v2.all_configs())
    assert {k.split("/")[0] for k in sp.heldout} == set(cases_v2.TEMPLATES)
    data = json.loads(split.SPLIT_FILE_V2.read_text())
    data["heldout"] = data["heldout"][1:]
    bad = split.SPLIT_FILE_V2.with_name("bad_split_v2.json")
    try:
        bad.write_text(json.dumps(data))
        with pytest.raises(ValueError):
            split.load(bad, version=2)
    finally:
        bad.unlink(missing_ok=True)
    with pytest.raises(ValueError):  # a v1 file is not a v2 split
        split.load(split.SPLIT_FILE, version=2)


def test_multicell_v2_shares_no_size_or_seed_with_v1():
    from benchmarks.multicell import cases, cases_v2

    assert not set(cases_v2.SIZES) & set(cases.SIZES)
    assert not set(cases_v2.SEEDS) & {1, 2, 3}
    ids = {c.id for c in cases_v2.all_cells()}
    assert not ids & {c.id for c in cases.all_cells()}


def test_multicell_v1_split_unchanged_by_versioning():
    from benchmarks.multicell import split

    sp = split.load()
    assert (sp.version, len(sp.dev), len(sp.heldout)) == (1, 22, 11)


def test_multicell_split_v3_holds_out_two_configurations_per_template():
    from benchmarks.multicell import cases, cases_v2, cases_v3, split

    sp = split.load(version=3)
    assert len(sp.heldout) == 2 * len(cases_v3.TEMPLATES) >= 24
    assert 2 * len(sp.heldout) >= 60  # cells (two sizes)
    per = {}
    for k in sp.heldout:
        per[k.split("/")[0]] = per.get(k.split("/")[0], 0) + 1
    assert set(per.values()) == {2}
    assert not set(cases_v3.SIZES) & (set(cases.SIZES) | set(cases_v2.SIZES))
    assert not set(cases_v3.SEEDS) & (set(cases_v2.SEEDS) | {1, 2, 3})
    with pytest.raises(ValueError):
        split.load(split.SPLIT_FILE_V2, version=3)
    for v in (1, 2):  # earlier versions unchanged
        assert split.load(version=v).version == v


def test_multicell_v3_runner_paths_are_protected():
    from benchmarks.multicell.run import SUITES

    _, results, _, log = SUITES[3]
    assert (
        str(results).replace("\\", "/").endswith("multicell_v3")
        and log.name == "phase7-heldout-access-log.md"
    )
