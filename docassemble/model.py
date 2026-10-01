"""Project data model: nodes, topics, fragments, variables, changes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple, Union


@dataclass(frozen=True)
class Text:
    text: str


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class Use:
    fragment_id: str


@dataclass(frozen=True)
class When:
    tag: str
    then: Tuple["Node", ...] = ()
    otherwise: Tuple["Node", ...] = ()


Node = Union[Text, Var, Use, When]


@dataclass(frozen=True)
class Topic:
    topic_id: str
    body: Tuple[Node, ...] = ()


@dataclass(frozen=True)
class Fragment:
    fragment_id: str
    body: Tuple[Node, ...] = ()


@dataclass(frozen=True)
class Project:
    topics: Dict[str, Topic] = field(default_factory=dict)
    fragments: Dict[str, Fragment] = field(default_factory=dict)
    variables: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SetTopic:
    topic: Topic


@dataclass(frozen=True)
class DeleteTopic:
    topic_id: str


@dataclass(frozen=True)
class SetFragment:
    fragment: Fragment


@dataclass(frozen=True)
class DeleteFragment:
    fragment_id: str


@dataclass(frozen=True)
class SetVariable:
    name: str
    value: str


@dataclass(frozen=True)
class DeleteVariable:
    name: str


Change = Union[
    SetTopic,
    DeleteTopic,
    SetFragment,
    DeleteFragment,
    SetVariable,
    DeleteVariable,
]
