"""项目数据模型：主题、片段、字符串变量与正文节点。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple, Union


@dataclass(frozen=True)
class Text:
    """原样输出的文本节点。"""

    text: str


@dataclass(frozen=True)
class Var:
    """读取一个字符串变量。"""

    name: str


@dataclass(frozen=True)
class Use:
    """展开一个片段。"""

    fragment: str


@dataclass(frozen=True)
class When:
    """按标签是否启用选择 then 或 else 节点序列。"""

    tag: str
    then: Tuple["Node", ...] = ()
    otherwise: Tuple["Node", ...] = ()


Node = Union[Text, Var, Use, When]


@dataclass(frozen=True)
class Topic:
    """以 ID 寻址的主题，正文为节点序列。"""

    body: Tuple[Node, ...] = ()


@dataclass(frozen=True)
class Fragment:
    """以 ID 寻址的可复用片段。"""

    body: Tuple[Node, ...] = ()


@dataclass(frozen=True)
class Project:
    """完整项目：主题、片段与字符串变量的集合。"""

    topics: Dict[str, Topic] = field(default_factory=dict)
    fragments: Dict[str, Fragment] = field(default_factory=dict)
    variables: Dict[str, str] = field(default_factory=dict)
