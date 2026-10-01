"""docforge：进程内增量文档装配库。"""
from .changes import (
    Change,
    RemoveFragment,
    RemoveTopic,
    RemoveVariable,
    SetVariable,
    UpsertFragment,
    UpsertTopic,
)
from .engine import Engine, Snapshot, TopicResult
from .model import Fragment, Node, Project, Text, Topic, Use, Var, When

__all__ = [
    "Change",
    "Engine",
    "Fragment",
    "Node",
    "Project",
    "RemoveFragment",
    "RemoveTopic",
    "RemoveVariable",
    "SetVariable",
    "Snapshot",
    "Text",
    "Topic",
    "TopicResult",
    "UpsertFragment",
    "UpsertTopic",
    "Use",
    "Var",
    "When",
]
