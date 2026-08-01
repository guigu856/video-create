"""验证 EvidenceBundle 属于分析边界且每次读取都核对真实文件哈希。"""

from pathlib import Path

import pytest
from reference_analysis_fixtures import (
    materialize_refinement,
    materialize_succeeded_analysis,
)

from video_create_plugin.analysis.evidence import (
    build_evidence_bundle,
    verified_evidence_path,
)
from video_create_plugin.errors import PluginError


def test_completed_job_builds_deterministic_evidence_bundle(tmp_path: Path) -> None:
    _, job = materialize_succeeded_analysis(tmp_path)

    first = build_evidence_bundle(job, tmp_path)
    second = build_evidence_bundle(job, tmp_path)

    assert first == second
    assert first.analysis_id == job.analysis_id
    assert first.source_media_sha256 == job.source.file.sha256
    assert {entry.evidence_id for entry in first.entries} >= {
        "frame_000001",
        "frame_000002",
        "audio_signals",
        "contact_sheet",
    }


def test_result_manifest_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    _, job = materialize_succeeded_analysis(tmp_path)
    assert job.video_output is not None
    (tmp_path / job.video_output.path).write_text("{}\n", encoding="utf-8")

    with pytest.raises(PluginError) as caught:
        build_evidence_bundle(job, tmp_path)

    assert caught.value.code == "file_hash_mismatch"


def test_nested_evidence_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    _, job = materialize_succeeded_analysis(tmp_path)
    frame = tmp_path / f"output/plugin/analysis/{job.analysis_id}/video/frames/frame_000001.jpg"
    frame.write_bytes(b"modified")

    with pytest.raises(PluginError) as caught:
        build_evidence_bundle(job, tmp_path)

    assert caught.value.code == "file_hash_mismatch"


def test_refinement_frames_and_contact_sheet_are_individual_resources(tmp_path: Path) -> None:
    repository, job = materialize_succeeded_analysis(tmp_path)
    job = materialize_refinement(tmp_path, repository, job)

    bundle = build_evidence_bundle(job, tmp_path)
    by_id = {entry.evidence_id: entry for entry in bundle.entries}

    assert {
        "refinement_001",
        "refinement_001_frame_000001",
        "refinement_001_frame_000002",
        "refinement_001_contact_sheet",
    } <= set(by_id)
    assert verified_evidence_path(
        tmp_path,
        by_id["refinement_001_frame_000001"],
    ).read_bytes() == b"refined-one"


def test_refinement_nested_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    repository, job = materialize_succeeded_analysis(tmp_path)
    job = materialize_refinement(tmp_path, repository, job)
    refined_frame = (
        tmp_path
        / job.analysis_dir
        / "refinements/refinement_test/frames/frame_000001.jpg"
    )
    refined_frame.write_bytes(b"modified")

    with pytest.raises(PluginError) as caught:
        build_evidence_bundle(job, tmp_path)

    assert caught.value.code == "file_hash_mismatch"
