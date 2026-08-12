"""Graph package.

Keep package import lightweight to avoid circular imports while agent modules use
the shared ``StudyState`` contract. Import ``app.graph.workflow`` explicitly when
building the executable LangGraph graph.
"""

from app.graph.state import StudyState

__all__ = ["StudyState"]
