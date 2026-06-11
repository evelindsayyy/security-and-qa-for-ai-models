"""Tool-specific exporters → ``SafetyRunResult`` JSON."""

from safety.exporters.garak import export_from_garak_report
from safety.exporters.promptfoo import export_from_promptfoo_eval

__all__ = ["export_from_garak_report", "export_from_promptfoo_eval"]
