"""随机差分测试：随机项目 + 随机变更 + 随机标签，逐步与参考展开器核对。"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docforge import (
    Engine,
    Fragment,
    Project,
    RemoveFragment,
    RemoveTopic,
    RemoveVariable,
    SetVariable,
    Text,
    Topic,
    UpsertFragment,
    UpsertTopic,
    Use,
    Var,
    When,
)
import reference

TAGS = ["t1", "t2", "t3"]


def random_nodes(rng, frag_ids, var_names, depth):
    count = rng.randint(0, 4)
    nodes = []
    for _ in range(count):
        kind = rng.choice(["text", "var", "use", "when"] if depth < 3 else ["text", "var"])
        if kind == "text":
            nodes.append(Text(rng.choice(["a", "b", "c", ""])))
        elif kind == "var":
            nodes.append(Var(rng.choice(var_names + ["nope"])))
        elif kind == "use":
            nodes.append(Use(rng.choice(frag_ids + ["ghost"])))
        else:
            nodes.append(
                When(
                    rng.choice(TAGS),
                    then=tuple(random_nodes(rng, frag_ids, var_names, depth + 1)),
                    otherwise=tuple(random_nodes(rng, frag_ids, var_names, depth + 1)),
                )
            )
    return nodes


def random_project(rng):
    frag_ids = [f"f{i}" for i in range(4)]
    var_names = [f"v{i}" for i in range(3)]
    topics = {
        f"topic{i}": Topic(tuple(random_nodes(rng, frag_ids, var_names, 0)))
        for i in range(3)
    }
    fragments = {
        fid: Fragment(tuple(random_nodes(rng, frag_ids, var_names, 1)))
        for fid in frag_ids
    }
    variables = {v: f"val-{v}" for v in var_names}
    return Project(topics=topics, fragments=fragments, variables=variables)


def random_changes(rng):
    frag_ids = [f"f{i}" for i in range(4)]
    var_names = [f"v{i}" for i in range(3)]
    topic_ids = [f"topic{i}" for i in range(3)]
    changes = []
    for _ in range(rng.randint(1, 4)):
        kind = rng.choice(
            ["up_t", "rm_t", "up_f", "rm_f", "set_v", "rm_v"]
        )
        if kind == "up_t":
            tid = rng.choice(topic_ids)
            changes.append(
                UpsertTopic(tid, Topic(tuple(random_nodes(rng, frag_ids, var_names, 0))))
            )
        elif kind == "rm_t":
            changes.append(RemoveTopic(rng.choice(topic_ids)))
        elif kind == "up_f":
            fid = rng.choice(frag_ids)
            changes.append(
                UpsertFragment(
                    fid, Fragment(tuple(random_nodes(rng, frag_ids, var_names, 1)))
                )
            )
        elif kind == "rm_f":
            changes.append(RemoveFragment(rng.choice(frag_ids)))
        elif kind == "set_v":
            changes.append(SetVariable(rng.choice(var_names), f"x{rng.randint(0, 9)}"))
        else:
            changes.append(RemoveVariable(rng.choice(var_names)))
    return changes


class Mirror:
    def __init__(self, project):
        self.project = Project(
            topics=dict(project.topics),
            fragments=dict(project.fragments),
            variables=dict(project.variables),
        )

    def apply(self, changes):
        p = self.project
        for change in changes:
            if isinstance(change, UpsertTopic):
                p.topics[change.topic_id] = change.topic
            elif isinstance(change, RemoveTopic):
                p.topics.pop(change.topic_id, None)
            elif isinstance(change, UpsertFragment):
                p.fragments[change.fragment_id] = change.fragment
            elif isinstance(change, RemoveFragment):
                p.fragments.pop(change.fragment_id, None)
            elif isinstance(change, SetVariable):
                p.variables[change.name] = change.value
            elif isinstance(change, RemoveVariable):
                p.variables.pop(change.name, None)


def test_random_differential():
    rng = random.Random(20261002)
    for round_no in range(30):
        project = random_project(rng)
        engine = Engine(project)
        mirror = Mirror(project)
        profiles = ["pa", "pb"]
        for step in range(20):
            changes = random_changes(rng)
            engine.apply(changes)
            mirror.apply(changes)
            for profile in profiles:
                tags = frozenset(t for t in TAGS if rng.random() < 0.5)
                snapshot = engine.build(profile, tags)
                expected = reference.expand_all(mirror.project, tags)
                assert set(snapshot.results) == set(expected), (round_no, step)
                for topic_id, (ok, value) in expected.items():
                    result = snapshot.results[topic_id]
                    assert result.ok == ok, (round_no, step, profile, topic_id)
                    if ok:
                        assert result.text == value, (round_no, step, profile, topic_id)
                    else:
                        assert result.error == value, (round_no, step, profile, topic_id)
