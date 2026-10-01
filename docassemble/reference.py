"""Cache-free reference expander used by tests to cross-check the engine."""

from __future__ import annotations

from typing import Dict, FrozenSet, List, Tuple

from .model import Node, Project, Text, Use, Var, When


class ExpandError(Exception):
    """A failure on the active expansion path."""


def _expand_nodes(
    project: Project,
    nodes: Tuple[Node, ...],
    tags: FrozenSet[str],
    stack: Tuple[str, ...],
    out: List[str],
) -> None:
    for node in nodes:
        if isinstance(node, Text):
            out.append(node.text)
        elif isinstance(node, Var):
            if node.name not in project.variables:
                raise ExpandError(f"missing variable: {node.name}")
            out.append(project.variables[node.name])
        elif isinstance(node, Use):
            if node.fragment_id in stack:
                cycle = " -> ".join(stack + (node.fragment_id,))
                raise ExpandError(f"fragment cycle: {cycle}")
            fragment = project.fragments.get(node.fragment_id)
            if fragment is None:
                raise ExpandError(f"missing fragment: {node.fragment_id}")
            _expand_nodes(project, fragment.body, tags, stack + (node.fragment_id,), out)
        elif isinstance(node, When):
            branch = node.then if node.tag in tags else node.otherwise
            _expand_nodes(project, branch, tags, stack, out)
        else:
            raise ExpandError(f"unknown node: {node!r}")


def expand_topic(project: Project, topic_id: str, tags: FrozenSet[str]) -> Tuple[bool, str]:
    """Return (ok, text_or_error) for one topic with no caching."""
    topic = project.topics.get(topic_id)
    if topic is None:
        return False, f"missing topic: {topic_id}"
    out: List[str] = []
    try:
        _expand_nodes(project, topic.body, tags, (), out)
    except ExpandError as exc:
        return False, str(exc)
    return True, "".join(out)


def expand_all(project: Project, tags: FrozenSet[str]) -> Dict[str, Tuple[bool, str]]:
    """Expand every topic in the project independently."""
    return {tid: expand_topic(project, tid, tags) for tid in project.topics}
