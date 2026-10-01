"""Incremental assembly engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, List, Optional, Tuple

from .model import (
    Change,
    DeleteFragment,
    DeleteTopic,
    DeleteVariable,
    Node,
    Project,
    SetFragment,
    SetTopic,
    SetVariable,
    Text,
    Use,
    Var,
    When,
)

_Dep = Tuple[str, str]


class _Missing(Exception):
    """Cacheable, context-free failure (missing variable or fragment)."""

    def __init__(self, message: str, deps: FrozenSet[_Dep], tag_reads=None):
        super().__init__(message)
        self.message = message
        self.deps = deps
        self.tag_reads = tag_reads or {}


class _Cycle(Exception):
    """Non-cacheable, path-dependent failure (fragment cycle)."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class _Outcome:
    __slots__ = ("ok", "text", "error", "deps", "tag_reads")

    def __init__(self, ok, text, error, deps, tag_reads):
        self.ok = ok
        self.text = text
        self.error = error
        self.deps = deps
        self.tag_reads = tag_reads

    def valid_for(self, tags: FrozenSet[str]) -> bool:
        return all((tag in tags) == enabled for tag, enabled in self.tag_reads.items())


@dataclass(frozen=True)
class TopicResult:
    """Immutable per-topic build outcome."""

    ok: bool
    text: Optional[str] = None
    error: Optional[str] = None


class BuildResult:
    """Immutable snapshot of one build."""

    def __init__(self, profile: str, tags: FrozenSet[str], topics: Dict[str, TopicResult]):
        self.profile = profile
        self.tags = tags
        self._topics = dict(topics)

    def topic(self, topic_id: str) -> TopicResult:
        return self._topics[topic_id]

    @property
    def topic_ids(self):
        return tuple(self._topics.keys())

    def as_dict(self) -> Dict[str, TopicResult]:
        return dict(self._topics)


class Engine:
    def __init__(self, project: Project):
        self._topics = dict(project.topics)
        self._fragments = dict(project.fragments)
        self._variables = dict(project.variables)
        self._frag_cache: Dict[str, Dict[str, _Outcome]] = {}
        self._topic_cache: Dict[str, Dict[str, _Outcome]] = {}

    def apply(self, changes: Iterable[Change]) -> None:
        changed: List[_Dep] = []
        for change in changes:
            if isinstance(change, SetTopic):
                self._topics[change.topic.topic_id] = change.topic
                changed.append(("topic", change.topic.topic_id))
            elif isinstance(change, DeleteTopic):
                self._topics.pop(change.topic_id, None)
                changed.append(("topic", change.topic_id))
            elif isinstance(change, SetFragment):
                self._fragments[change.fragment.fragment_id] = change.fragment
                changed.append(("frag", change.fragment.fragment_id))
            elif isinstance(change, DeleteFragment):
                self._fragments.pop(change.fragment_id, None)
                changed.append(("frag", change.fragment_id))
            elif isinstance(change, SetVariable):
                self._variables[change.name] = change.value
                changed.append(("var", change.name))
            elif isinstance(change, DeleteVariable):
                self._variables.pop(change.name, None)
                changed.append(("var", change.name))
            else:
                raise TypeError(f"unknown change: {change!r}")
        if changed:
            self._invalidate(set(changed))

    def _invalidate(self, changed: FrozenSet[_Dep]) -> None:
        for cache in (self._frag_cache, self._topic_cache):
            for entries in cache.values():
                doomed = [k for k, e in entries.items() if e.deps & changed]
                for key in doomed:
                    del entries[key]

    def build(self, profile: str, tags) -> BuildResult:
        tag_set = frozenset(tags)
        results: Dict[str, TopicResult] = {}
        for topic_id in self._topics:
            outcome = self._topic_result(profile, topic_id, tag_set)
            if outcome.ok:
                results[topic_id] = TopicResult(True, text=outcome.text)
            else:
                results[topic_id] = TopicResult(False, error=outcome.error)
        return BuildResult(profile, tag_set, results)

    def _topic_result(self, profile: str, topic_id: str, tags: FrozenSet[str]) -> _Outcome:
        cache = self._topic_cache.setdefault(profile, {})
        cached = cache.get(topic_id)
        if cached is not None and cached.valid_for(tags):
            return cached
        topic = self._topics[topic_id]
        own_dep = frozenset({("topic", topic_id)})
        try:
            text, deps, tag_reads = self._expand_nodes(profile, topic.body, tags, ())
        except _Missing as miss:
            outcome = _Outcome(False, None, miss.message, own_dep | miss.deps, miss.tag_reads)
            cache[topic_id] = outcome
            return outcome
        except _Cycle as cycle:
            return _Outcome(False, None, cycle.message, own_dep, {})
        outcome = _Outcome(True, text, None, own_dep | deps, tag_reads)
        cache[topic_id] = outcome
        return outcome

    def _fragment_result(
        self, profile: str, fragment_id: str, tags: FrozenSet[str], stack: Tuple[str, ...]
    ) -> _Outcome:
        cache = self._frag_cache.setdefault(profile, {})
        cached = cache.get(fragment_id)
        if cached is not None and cached.valid_for(tags):
            return cached
        fragment = self._fragments.get(fragment_id)
        own_dep = frozenset({("frag", fragment_id)})
        if fragment is None:
            outcome = _Outcome(
                False, None, f"missing fragment: {fragment_id}", own_dep, {}
            )
            cache[fragment_id] = outcome
            return outcome
        try:
            text, deps, tag_reads = self._expand_nodes(
                profile, fragment.body, tags, stack + (fragment_id,)
            )
        except _Missing as miss:
            outcome = _Outcome(False, None, miss.message, own_dep | miss.deps, miss.tag_reads)
            cache[fragment_id] = outcome
            return outcome
        outcome = _Outcome(True, text, None, own_dep | deps, tag_reads)
        cache[fragment_id] = outcome
        return outcome

    def _expand_nodes(
        self,
        profile: str,
        nodes: Tuple[Node, ...],
        tags: FrozenSet[str],
        stack: Tuple[str, ...],
    ):
        parts: List[str] = []
        deps: set = set()
        tag_reads: Dict[str, bool] = {}
        for node in nodes:
            if isinstance(node, Text):
                parts.append(node.text)
            elif isinstance(node, Var):
                deps.add(("var", node.name))
                if node.name not in self._variables:
                    raise _Missing(
                        f"missing variable: {node.name}", frozenset(deps), dict(tag_reads)
                    )
                parts.append(self._variables[node.name])
            elif isinstance(node, Use):
                if node.fragment_id in stack:
                    raise _Cycle(
                        "fragment cycle: " + " -> ".join(stack + (node.fragment_id,))
                    )
                outcome = self._fragment_result(profile, node.fragment_id, tags, stack)
                deps |= outcome.deps
                tag_reads.update(outcome.tag_reads)
                if not outcome.ok:
                    raise _Missing(outcome.error, frozenset(deps), dict(tag_reads))
                parts.append(outcome.text)
            elif isinstance(node, When):
                enabled = node.tag in tags
                tag_reads[node.tag] = enabled
                branch = node.then if enabled else node.otherwise
                try:
                    text, sub_deps, sub_tags = self._expand_nodes(
                        profile, branch, tags, stack
                    )
                except _Missing as miss:
                    merged = dict(tag_reads)
                    merged.update(miss.tag_reads)
                    raise _Missing(miss.message, miss.deps, merged)
                parts.append(text)
                deps |= sub_deps
                tag_reads.update(sub_tags)
            else:
                raise TypeError(f"unknown node: {node!r}")
        return "".join(parts), frozenset(deps), tag_reads
