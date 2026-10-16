"""Report rendering: JSON evidence object and Markdown research report.

Templates are plain Python string formatting; no template engine. Rendering
never derives new scientific statements: every sentence in a finding comes
from the ``FindingAssessment`` with its evidence-id citation intact.
"""

from somaweave.reporting.bundle import RunBundle
from somaweave.reporting.render_json import render_json
from somaweave.reporting.render_markdown import RESEARCH_USE_BANNER, render_markdown

__all__ = ["RESEARCH_USE_BANNER", "RunBundle", "render_json", "render_markdown"]
