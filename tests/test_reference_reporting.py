"""验证参考报告生成只消费已校验合同，并输出 DOCX 与机器文件清单。"""

import hashlib
import json
from pathlib import Path

from docx import Document
from test_reference_report_contract import make_reference_report

from video_create_plugin.application.reference_reporting import ReferenceReportingService
from video_create_plugin.contracts import FileRef
from video_create_plugin.reporting.generator import REPORT_FILE_ROLES


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _materialize_evidence(root: Path):
    report = make_reference_report()
    entries = []
    for entry in report.evidence_bundle.entries:
        path = root / entry.file.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"evidence:{entry.evidence_id}".encode())
        entries.append(
            entry.model_copy(
                update={
                    "file": FileRef(
                        path=entry.file.path,
                        sha256=_sha256(path),
                    )
                }
            )
        )
    return report.model_copy(
        update={
            "evidence_bundle": report.evidence_bundle.model_copy(update={"entries": tuple(entries)})
        }
    )


def test_generate_report_writes_docx_json_and_hash_manifest(tmp_path: Path) -> None:
    report = _materialize_evidence(tmp_path)
    service = ReferenceReportingService(tmp_path)

    output = service.generate(report, tmp_path / "reports/reference-example")

    assert output.manifest.schema_version == "2.0"
    assert tuple(item.role for item in output.manifest.files) == REPORT_FILE_ROLES
    assert (tmp_path / output.manifest_file.path).is_file()
    for item in output.manifest.files:
        path = tmp_path / item.file.path
        assert path.is_file()
        assert _sha256(path) == item.file.sha256
    assert all((tmp_path / item.file.path).suffix != ".md" for item in output.manifest.files)

    manifest_payload = json.loads(
        (tmp_path / output.manifest_file.path).read_text(encoding="utf-8")
    )
    assert manifest_payload == output.manifest.model_dump(mode="json")
    assert _sha256(tmp_path / output.manifest_file.path) == output.manifest_file.sha256


def test_generated_report_is_openable_and_byte_stable(tmp_path: Path) -> None:
    report = _materialize_evidence(tmp_path)
    service = ReferenceReportingService(tmp_path)
    output_dir = tmp_path / "reports/reference-example"

    first = service.generate(report, output_dir)
    first_hashes = {item.role: item.file.sha256 for item in first.manifest.files}
    second = service.generate(report, output_dir)

    assert {item.role: item.file.sha256 for item in second.manifest.files} == first_hashes
    human_report = tmp_path / second.manifest.file_for("human_report_docx").path
    document = Document(human_report)
    paragraphs = tuple(paragraph.text for paragraph in document.paragraphs)
    assert "参考视频分析报告" in paragraphs
    assert "参考视频总体理解" in paragraphs
    assert "BGM 与音画关系分析" in paragraphs
    assert "逐镜分析" in paragraphs
    assert "可复用剪辑语法" in paragraphs
    assert "创作阶段知识投影" in paragraphs
    assert "证据索引" in paragraphs
    assert any("镜头 shot_001" in text for text in paragraphs)
