"""In-process incremental document assembly library."""

from .model import (
    Text,
    Var,
    Use,
    When,
    Node,
    Topic,
    Fragment,
    Project,
    Change,
    SetTopic,
    DeleteTopic,
    SetFragment,
    DeleteFragment,
    SetVariable,
    DeleteVariable,
)
from .engine import Engine, BuildResult, TopicResult

__all__ = [
    "Text",
    "Var",
    "Use",
    "When",
    "Node",
    "Topic",
    "Fragment",
    "Project",
    "Change",
    "SetTopic",
    "DeleteTopic",
    "SetFragment",
    "DeleteFragment",
    "SetVariable",
    "DeleteVariable",
    "Engine",
    "BuildResult",
    "TopicResult",
]
