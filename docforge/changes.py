"""增量变更描述：对主题、片段、变量的增删改。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

from .model import Fragment, Topic


@dataclass(frozen=True)
class UpsertTopic:
    """新增或替换一个主题；已存在则整体替换。"""

    topic_id: str
    topic: Topic


@dataclass(frozen=True)
class RemoveTopic:
    topic_id: str


@dataclass(frozen=True)
class UpsertFragment:
    """新增或替换一个片段；已存在则整体替换。"""

    fragment_id: str
    fragment: Fragment


@dataclass(frozen=True)
class RemoveFragment:
    fragment_id: str


@dataclass(frozen=True)
class SetVariable:
    """设置或覆盖一个字符串变量。"""

    name: str
    value: str


@dataclass(frozen=True)
class RemoveVariable:
    name: str


Change = Union[
    UpsertTopic,
    RemoveTopic,
    UpsertFragment,
    RemoveFragment,
    SetVariable,
    RemoveVariable,
]
