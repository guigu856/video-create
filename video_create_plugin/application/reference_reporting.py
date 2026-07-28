"""参考报告应用服务，只编排合同校验和确定性文件生成。"""

from pathlib import Path

from video_create_plugin.reporting.generator import ReferenceReportGenerator
from video_create_plugin.reporting.models import ReferenceReportOutput, ReferenceStudyReport


class ReferenceReportingService:
    def __init__(self, workspace_root: Path) -> None:
        self._generator = ReferenceReportGenerator(workspace_root)

    def generate(
        self,
        report: ReferenceStudyReport,
        output_dir: Path,
    ) -> ReferenceReportOutput:
        return self._generator.generate(report, output_dir)
