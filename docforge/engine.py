"""增量文档装配引擎。"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Dict, Iterable, Mapping, Optional, Set, Tuple

from .changes import (
    Change,
    RemoveFragment,
    RemoveTopic,
    RemoveVariable,
    SetVariable,
    UpsertFragment,
    UpsertTopic,
)
from .model import Node, Project, Text, Use, Var, When

# 依赖键：("topic" | "frag" | "var", 对象 ID)
Dep = Tuple[str, str]

# 缓存键：("topic" | "frag", 对象 ID, 启用标签集合)
CacheKey = Tuple[str, str, frozenset]


@dataclass(frozen=True)
class TopicResult:
    """单个主题的构建结果：成功为正文，失败为错误信息。"""

    ok: bool
    text: Optional[str] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class Snapshot:
    """一次构建产出的不可变快照。"""

    profile: str
    tags: frozenset
    results: Mapping[str, TopicResult]


@dataclass
class _Entry:
    result: TopicResult
    deps: frozenset


class _ProfileState:
    """单个配置的缓存：结果缓存 + 依赖到缓存键的反向索引。"""

    def __init__(self) -> None:
        self.cache: Dict[CacheKey, _Entry] = {}
        self.dependents: Dict[Dep, Set[CacheKey]] = {}


class Engine:
    """进程内增量装配引擎。调用串行，输出可放入内存。"""

    def __init__(self, project: Project) -> None:
        self._topics = dict(project.topics)
        self._fragments = dict(project.fragments)
        self._variables = dict(project.variables)
        self._profiles: Dict[str, _ProfileState] = {}

    def apply(self, changes: Iterable[Change]) -> None:
        """应用一批增删改变更。"""
        touched: Set[Dep] = set()
        for change in changes:
            if isinstance(change, UpsertTopic):
                self._topics[change.topic_id] = change.topic
                touched.add(("topic", change.topic_id))
            elif isinstance(change, RemoveTopic):
                self._topics.pop(change.topic_id, None)
                touched.add(("topic", change.topic_id))
            elif isinstance(change, UpsertFragment):
                self._fragments[change.fragment_id] = change.fragment
                touched.add(("frag", change.fragment_id))
            elif isinstance(change, RemoveFragment):
                self._fragments.pop(change.fragment_id, None)
                touched.add(("frag", change.fragment_id))
            elif isinstance(change, SetVariable):
                self._variables[change.name] = change.value
                touched.add(("var", change.name))
            elif isinstance(change, RemoveVariable):
                self._variables.pop(change.name, None)
                touched.add(("var", change.name))
            else:
                raise TypeError(f"unknown change: {change!r}")
        for profile in self._profiles.values():
            for dep in touched:
                self._invalidate(profile, dep)

    def build(self, profile: str, tags: Iterable[str]) -> Snapshot:
        """按配置 ID 与启用标签集合构建全部主题，返回不可变快照。"""
        tag_set = frozenset(tags)
        state = self._profiles.setdefault(profile, _ProfileState())
        results: Dict[str, TopicResult] = {}
        for topic_id in sorted(self._topics):
            result, _ = self._expand_topic(state, topic_id, tag_set)
            results[topic_id] = result
        return Snapshot(profile, tag_set, MappingProxyType(results))

    # ---- 缓存维护 ----

    def _store(
        self, state: _ProfileState, key: CacheKey, result: TopicResult, deps: Set[Dep]
    ) -> None:
        frozen = frozenset(deps)
        state.cache[key] = _Entry(result, frozen)
        for dep in frozen:
            state.dependents.setdefault(dep, set()).add(key)

    def _invalidate(self, state: _ProfileState, dep: Dep) -> None:
        for key in state.dependents.pop(dep, ()):
            entry = state.cache.pop(key, None)
            if entry is None:
                continue
            for other in entry.deps:
                bucket = state.dependents.get(other)
                if bucket is not None:
                    bucket.discard(key)

    # ---- 展开 ----

    def _expand_topic(
        self, state: _ProfileState, topic_id: str, tags: frozenset
    ) -> Tuple[TopicResult, Set[Dep]]:
        key = ("topic", topic_id, tags)
        entry = state.cache.get(key)
        if entry is not None:
            return entry.result, set(entry.deps)
        deps: Set[Dep] = {("topic", topic_id)}
        topic = self._topics.get(topic_id)
        if topic is None:
            result = TopicResult(False, error=f"missing topic: {topic_id}")
        else:
            result, extra = self._expand_nodes(state, topic.body, tags, ())
            deps |= extra
        self._store(state, key, result, deps)
        return result, deps

    def _expand_fragment(
        self,
        state: _ProfileState,
        fragment_id: str,
        tags: frozenset,
        stack: Tuple[str, ...],
    ) -> Tuple[TopicResult, Set[Dep]]:
        key = ("frag", fragment_id, tags)
        entry = state.cache.get(key)
        if entry is not None:
            return entry.result, set(entry.deps)
        deps: Set[Dep] = {("frag", fragment_id)}
        fragment = self._fragments.get(fragment_id)
        if fragment is None:
            result = TopicResult(False, error=f"missing fragment: {fragment_id}")
        elif fragment_id in stack:
            cycle = " -> ".join(stack[stack.index(fragment_id):] + (fragment_id,))
            result = TopicResult(False, error=f"fragment cycle: {cycle}")
        else:
            result, extra = self._expand_nodes(
                state, fragment.body, tags, stack + (fragment_id,)
            )
            deps |= extra
        self._store(state, key, result, deps)
        return result, deps

    def _expand_nodes(
        self,
        state: _ProfileState,
        nodes: Tuple[Node, ...],
        tags: frozenset,
        stack: Tuple[str, ...],
    ) -> Tuple[TopicResult, Set[Dep]]:
        parts = []
        deps: Set[Dep] = set()
        for node in nodes:
            if isinstance(node, Text):
                parts.append(node.text)
            elif isinstance(node, Var):
                deps.add(("var", node.name))
                value = self._variables.get(node.name)
                if value is None:
                    return TopicResult(False, error=f"missing variable: {node.name}"), deps
                parts.append(value)
            elif isinstance(node, Use):
                result, extra = self._expand_fragment(
                    state, node.fragment, tags, stack
                )
                deps |= extra
                if not result.ok:
                    return result, deps
                parts.append(result.text)
            elif isinstance(node, When):
                branch = node.then if node.tag in tags else node.otherwise
                result, extra = self._expand_nodes(state, branch, tags, stack)
                deps |= extra
                if not result.ok:
                    return result, deps
                parts.append(result.text)
            else:
                raise TypeError(f"unknown node: {node!r}")
        return TopicResult(True, text="".join(parts)), deps
