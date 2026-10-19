"""Cross-artifact integration: validate the outputs pipeline's dry-run artefacts.

The outputs-builder teammate produces SPEC-schema artefacts from the historical
80-route baseline under ``scratch/outputs_dryrun/``.  These tests exercise the
validator's ``--run-dir``/``--routes`` loaders on artefacts this validator did
not create itself.  They are skipped until that dry-run exists.
"""
from __future__ import annotations

import json

import pytest

from d56_helpers import ROOT
from four_side_1024.d56 import validate_d56 as V

DRYRUN_OUT80 = ROOT / "scratch/outputs_dryrun/out80"
DRYRUN_RUN80 = ROOT / "scratch/outputs_dryrun/run80"

pytestmark = pytest.mark.skipif(
    not (DRYRUN_OUT80 / "routes.json").exists(),
    reason="outputs-builder dry-run artefacts not present")


def test_outputs_pipeline_dryrun_routes_json_passes():
    """SPEC ``routes.json`` with 1024 identities (80 routed, 944 failed)."""
    report = V.build_report(run_dir=DRYRUN_OUT80, audit_pairs=True,
                            expected_route_count=1024)
    assert report["passed"] is True, report["errors"]
    assert report["route_count"] == 1024
    assert report["routed_count"] == 80
    assert report["failed_status_count"] == 944
    assert report["d56_passed_count"] == 80
    assert report["d56_failed_count"] == 0
    assert report["violations"] == []
    assert report["crossing_count"] == 1141
    statistics = json.loads((DRYRUN_OUT80 / "statistics.json").read_text(encoding="utf-8"))
    assert report["crossing_count"] == statistics["crossing_count"]
    assert report["crossing_angle_histogram"] == statistics["crossing_angle_histogram"]


def test_outputs_pipeline_dryrun_routes_geometry_mode_passes():
    """``--routes routes_geometry.json`` without repeated endpoint identities."""
    report = V.build_report(routes_path=DRYRUN_OUT80 / "routes_geometry.json",
                            audit_pairs=True)
    assert report["passed"] is True, report["errors"]
    assert report["d56_passed_count"] == 80
    assert report["crossing_count"] == 1141


def test_outputs_pipeline_run80_input_config_artefact():
    """The pipeline's input-directory ``routes.json`` (config + identities)."""
    if not (DRYRUN_RUN80 / "routes.json").exists():
        pytest.skip("run80 input artefact not present")
    report = V.build_report(run_dir=DRYRUN_RUN80, audit_pairs=True)
    # The 80 dry-run geometry may be split between routed and failed identities;
    # whatever is routed must be D56-legal and the report must stay consistent.
    assert report["d56_failed_count"] == 0, report["route_errors"][:5]
    assert report["violations"] == []
    assert report["route_count"] == 1024
