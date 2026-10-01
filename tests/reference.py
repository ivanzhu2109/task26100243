"""无缓存参考展开器：测试专用，与引擎实现完全独立。

直接对 Project 做朴素递归展开，每次调用都是全量构建。
"""
from __future__ import annotations

from typing import Dict, FrozenSet, Tuple

from docforge.model import Node, Project, Text, Use, Var, When


def expand_all(project: Project, tags: FrozenSet[str]) -> Dict[str, Tuple[bool, object]]:
    """对每个主题返回 (ok, text_or_error)，不做任何缓存。"""
    return {
        topic_id: _expand_nodes(project, topic.body, tags, ())
        for topic_id, topic in sorted(project.topics.items())
    }


def _expand_nodes(
    project: Project, nodes, tags: FrozenSet[str], stack: Tuple[str, ...]
) -> Tuple[bool, object]:
    parts = []
    for node in nodes:
        if isinstance(node, Text):
            parts.append(node.text)
        elif isinstance(node, Var):
            if node.name not in project.variables:
                return False, f"missing variable: {node.name}"
            parts.append(project.variables[node.name])
        elif isinstance(node, Use):
            ok, value = _expand_fragment(project, node.fragment, tags, stack)
            if not ok:
                return False, value
            parts.append(value)
        elif isinstance(node, When):
            branch = node.then if node.tag in tags else node.otherwise
            ok, value = _expand_nodes(project, branch, tags, stack)
            if not ok:
                return False, value
            parts.append(value)
        else:
            raise TypeError(f"unknown node: {node!r}")
    return True, "".join(parts)


def _expand_fragment(
    project: Project, fragment_id: str, tags: FrozenSet[str], stack: Tuple[str, ...]
) -> Tuple[bool, object]:
    fragment = project.fragments.get(fragment_id)
    if fragment is None:
        return False, f"missing fragment: {fragment_id}"
    if fragment_id in stack:
        cycle = " -> ".join(stack[stack.index(fragment_id):] + (fragment_id,))
        return False, f"fragment cycle: {cycle}"
    return _expand_nodes(project, fragment.body, tags, stack + (fragment_id,))
