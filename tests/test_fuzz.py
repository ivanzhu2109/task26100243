"""Deterministic randomized differential test: engine vs cache-free reference."""

from __future__ import annotations

import random
import unittest

from docassemble import (
    DeleteFragment,
    DeleteVariable,
    Engine,
    Fragment,
    Project,
    SetFragment,
    SetVariable,
    Text,
    Topic,
    Use,
    Var,
    When,
)
from docassemble.reference import expand_all

from tests.test_engine import apply_to_project

TAGS = ("t1", "t2", "t3")
VARS = ("v1", "v2", "v3", "v4")
FRAGS = ("f1", "f2", "f3", "f4", "f5")
TOPICS = ("a", "b", "c")
PROFILES = ("p1", "p2", "p3")


def random_nodes(rng, depth):
    count = rng.randint(0, 3)
    nodes = []
    for _ in range(count):
        kind = rng.choice(("text", "var", "use", "when"))
        if depth <= 0:
            kind = rng.choice(("text", "var"))
        if kind == "text":
            nodes.append(Text(rng.choice(("", "x", "ab", "."))))
        elif kind == "var":
            nodes.append(Var(rng.choice(VARS + ("ghost_var",))))
        elif kind == "use":
            nodes.append(Use(rng.choice(FRAGS + ("ghost_frag",))))
        else:
            nodes.append(
                When(
                    rng.choice(TAGS),
                    then=tuple(random_nodes(rng, depth - 1)),
                    otherwise=tuple(random_nodes(rng, depth - 1)),
                )
            )
    return nodes


class TestFuzz(unittest.TestCase):
    def test_random_edits_and_tag_switches(self):
        rng = random.Random(20261002)
        project = Project(
            topics={t: Topic(t, tuple(random_nodes(rng, 2))) for t in TOPICS},
            fragments={f: Fragment(f, tuple(random_nodes(rng, 2))) for f in FRAGS},
            variables={v: f"val-{v}" for v in VARS},
        )
        engine = Engine(project)

        for step in range(300):
            action = rng.random()
            if action < 0.45:
                changes = []
                for _ in range(rng.randint(1, 3)):
                    what = rng.random()
                    if what < 0.3:
                        fid = rng.choice(FRAGS)
                        changes.append(
                            SetFragment(Fragment(fid, tuple(random_nodes(rng, 2))))
                        )
                    elif what < 0.5:
                        changes.append(DeleteFragment(rng.choice(FRAGS)))
                    elif what < 0.8:
                        changes.append(
                            SetVariable(rng.choice(VARS), f"val-{step}")
                        )
                    else:
                        changes.append(DeleteVariable(rng.choice(VARS)))
                engine.apply(changes)
                project = apply_to_project(project, changes)

            profile = rng.choice(PROFILES)
            tags = {t for t in TAGS if rng.random() < 0.5}
            result = engine.build(profile, tags)
            reference = expand_all(project, frozenset(tags))
            for topic_id, (ok, payload) in reference.items():
                actual = result.topic(topic_id)
                self.assertEqual(
                    actual.ok, ok, f"step={step} {profile}/{topic_id} tags={sorted(tags)}"
                )
                self.assertEqual(
                    actual.text if ok else actual.error,
                    payload,
                    f"step={step} {profile}/{topic_id} tags={sorted(tags)}",
                )


if __name__ == "__main__":
    unittest.main()
