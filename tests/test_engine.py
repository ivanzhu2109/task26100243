"""Engine tests: every build is cross-checked against the cache-free reference."""

from __future__ import annotations

import unittest

from docassemble import (
    DeleteFragment,
    DeleteTopic,
    DeleteVariable,
    Engine,
    Fragment,
    Project,
    SetFragment,
    SetTopic,
    SetVariable,
    Text,
    Topic,
    Use,
    Var,
    When,
)
from docassemble.reference import expand_all


def apply_to_project(project: Project, changes) -> Project:
    """Pure reference counterpart of Engine.apply."""
    topics = dict(project.topics)
    fragments = dict(project.fragments)
    variables = dict(project.variables)
    for change in changes:
        if isinstance(change, SetTopic):
            topics[change.topic.topic_id] = change.topic
        elif isinstance(change, DeleteTopic):
            topics.pop(change.topic_id, None)
        elif isinstance(change, SetFragment):
            fragments[change.fragment.fragment_id] = change.fragment
        elif isinstance(change, DeleteFragment):
            fragments.pop(change.fragment_id, None)
        elif isinstance(change, SetVariable):
            variables[change.name] = change.value
        elif isinstance(change, DeleteVariable):
            variables.pop(change.name, None)
        else:
            raise TypeError(change)
    return Project(topics=topics, fragments=fragments, variables=variables)


class EngineCase(unittest.TestCase):
    def assert_build_matches_reference(self, engine, project, profile, tags):
        """Build via engine and compare every topic with the reference expander."""
        result = engine.build(profile, tags)
        reference = expand_all(project, frozenset(tags))
        self.assertEqual(set(result.topic_ids), set(reference))
        for topic_id, (ok, payload) in reference.items():
            actual = result.topic(topic_id)
            self.assertEqual(actual.ok, ok, f"{profile}/{topic_id} tags={sorted(tags)}")
            if ok:
                self.assertEqual(actual.text, payload, f"{profile}/{topic_id}")
                self.assertIsNone(actual.error)
            else:
                self.assertEqual(actual.error, payload, f"{profile}/{topic_id}")
                self.assertIsNone(actual.text)
        return result


class TestAlternatingProfiles(EngineCase):
    """Two profiles alternate over the same nested fragments with different tags."""

    def setUp(self):
        self.project = Project(
            topics={
                "main": Topic("main", (Text("M "), Use("outer"))),
                "other": Topic("other", (Text("O "), Var("v_shown"))),
            },
            fragments={
                "outer": Fragment(
                    "outer",
                    (
                        Text("["),
                        Use("inner"),
                        Text("]"),
                        When(
                            "extra",
                            then=(Text("{"), Use("hidden_only"), Text("}")),
                            otherwise=(Text("none"),),
                        ),
                    ),
                ),
                "inner": Fragment("inner", (Text("in:"), Var("v_shown"))),
                "hidden_only": Fragment("hidden_only", (Text("H:"), Var("v_hidden"))),
            },
            variables={"v_shown": "S", "v_hidden": "H1"},
        )
        self.engine = Engine(self.project)

    def build_both(self, pa_tags=("extra",), pb_tags=()):
        ra = self.assert_build_matches_reference(
            self.engine, self.project, "pa", set(pa_tags)
        )
        rb = self.assert_build_matches_reference(
            self.engine, self.project, "pb", set(pb_tags)
        )
        return ra, rb

    def test_alternating_profiles_hidden_branch_edits(self):
        ra1, rb1 = self.build_both()
        self.assertEqual(ra1.topic("main").text, "M [in:S]{H:H1}")
        self.assertEqual(rb1.topic("main").text, "M [in:S]none")

        # Alternate again to warm both profile caches.
        self.build_both()

        # Edit objects referenced only by the hidden branch.
        edits = [
            SetVariable("v_hidden", "H2"),
            SetFragment(Fragment("hidden_only", (Text("H2:"), Var("v_hidden"), Text("!")))),
        ]
        self.engine.apply(edits)
        self.project = apply_to_project(self.project, edits)

        ra2, rb2 = self.build_both()
        self.assertEqual(ra2.topic("main").text, "M [in:S]{H2:H2!}")
        self.assertEqual(rb2.topic("main").text, "M [in:S]none")

        # Old snapshots must not have changed.
        self.assertEqual(ra1.topic("main").text, "M [in:S]{H:H1}")
        self.assertEqual(rb1.topic("main").text, "M [in:S]none")

        # Enable the branch for pb, then switch back.
        rb_on = self.assert_build_matches_reference(
            self.engine, self.project, "pb", {"extra"}
        )
        self.assertEqual(rb_on.topic("main").text, "M [in:S]{H2:H2!}")
        rb_off = self.assert_build_matches_reference(
            self.engine, self.project, "pb", set()
        )
        self.assertEqual(rb_off.topic("main").text, "M [in:S]none")

        # Modify again after switching back; hidden edit must not leak.
        edits2 = [SetVariable("v_hidden", "H3")]
        self.engine.apply(edits2)
        self.project = apply_to_project(self.project, edits2)

        ra3, rb3 = self.build_both()
        self.assertEqual(ra3.topic("main").text, "M [in:S]{H2:H3!}")
        self.assertEqual(rb3.topic("main").text, "M [in:S]none")

        # Snapshots taken before this edit are still frozen.
        self.assertEqual(ra2.topic("main").text, "M [in:S]{H2:H2!}")
        self.assertEqual(rb_off.topic("main").text, "M [in:S]none")

        # Re-enabling the branch must use the latest content.
        rb_on2 = self.assert_build_matches_reference(
            self.engine, self.project, "pb", {"extra"}
        )
        self.assertEqual(rb_on2.topic("main").text, "M [in:S]{H2:H3!}")


class TestFailureAndRecovery(EngineCase):
    """Missing references and cycles in a warmed chain; repair restores output."""

    def setUp(self):
        self.project = Project(
            topics={
                "chain": Topic("chain", (Text("C:"), Use("a"))),
                "unrelated": Topic("unrelated", (Text("fine"),)),
                "branchy": Topic(
                    "branchy",
                    (When("on", then=(Use("a"),), otherwise=(Text("off"),)),),
                ),
            },
            fragments={
                "a": Fragment("a", (Text("a>"), Use("b"))),
                "b": Fragment("b", (Text("b>"), Use("c"))),
                "c": Fragment("c", (Text("c="), Var("v"))),
            },
            variables={"v": "1"},
        )
        self.engine = Engine(self.project)

    def apply(self, changes):
        self.engine.apply(changes)
        self.project = apply_to_project(self.project, changes)

    def test_missing_variable_and_recovery(self):
        warm = self.assert_build_matches_reference(
            self.engine, self.project, "p1", {"on"}
        )
        self.assertEqual(warm.topic("chain").text, "C:a>b>c=1")

        self.apply([DeleteVariable("v")])
        broken = self.assert_build_matches_reference(
            self.engine, self.project, "p1", {"on"}
        )
        self.assertFalse(broken.topic("chain").ok)
        self.assertEqual(broken.topic("chain").error, "missing variable: v")
        self.assertTrue(broken.topic("unrelated").ok)
        # Cached failure is served identically on a repeat build.
        broken2 = self.assert_build_matches_reference(
            self.engine, self.project, "p1", {"on"}
        )
        self.assertEqual(broken2.topic("chain").error, "missing variable: v")

        self.apply([SetVariable("v", "2")])
        healed = self.assert_build_matches_reference(
            self.engine, self.project, "p1", {"on"}
        )
        self.assertEqual(healed.topic("chain").text, "C:a>b>c=2")
        # The pre-break snapshot is untouched.
        self.assertEqual(warm.topic("chain").text, "C:a>b>c=1")

    def test_missing_fragment_and_recovery(self):
        self.assert_build_matches_reference(self.engine, self.project, "p1", {"on"})
        self.apply([DeleteFragment("c")])
        broken = self.assert_build_matches_reference(
            self.engine, self.project, "p1", {"on"}
        )
        self.assertEqual(broken.topic("chain").error, "missing fragment: c")
        self.assertTrue(broken.topic("unrelated").ok)

        self.apply([SetFragment(Fragment("c", (Text("c="), Var("v"))))])
        healed = self.assert_build_matches_reference(
            self.engine, self.project, "p1", {"on"}
        )
        self.assertEqual(healed.topic("chain").text, "C:a>b>c=1")

    def test_cycle_and_recovery(self):
        self.assert_build_matches_reference(self.engine, self.project, "p1", {"on"})
        self.apply([SetFragment(Fragment("b", (Text("b>"), Use("a"))))])
        cyclic = self.assert_build_matches_reference(
            self.engine, self.project, "p1", {"on"}
        )
        self.assertFalse(cyclic.topic("chain").ok)
        self.assertIn("fragment cycle", cyclic.topic("chain").error)
        self.assertTrue(cyclic.topic("unrelated").ok)
        # Repeat build reports the same failure (no stale cache).
        cyclic2 = self.assert_build_matches_reference(
            self.engine, self.project, "p1", {"on"}
        )
        self.assertEqual(cyclic2.topic("chain").error, cyclic.topic("chain").error)

        self.apply([SetFragment(Fragment("b", (Text("b>"), Use("c"))))])
        healed = self.assert_build_matches_reference(
            self.engine, self.project, "p1", {"on"}
        )
        self.assertEqual(healed.topic("chain").text, "C:a>b>c=1")

    def test_errors_in_unselected_branch_do_not_fail(self):
        # Break the chain, then build with the branch disabled.
        self.apply([DeleteVariable("v")])
        result = self.assert_build_matches_reference(
            self.engine, self.project, "p2", set()
        )
        self.assertTrue(result.topic("branchy").ok)
        self.assertEqual(result.topic("branchy").text, "off")

        # A cycle in the unselected branch is likewise invisible.
        self.apply([SetFragment(Fragment("b", (Text("b>"), Use("a"))))])
        result2 = self.assert_build_matches_reference(
            self.engine, self.project, "p2", set()
        )
        self.assertEqual(result2.topic("branchy").text, "off")

        # Re-enabling the branch surfaces the current (broken) state...
        result3 = self.assert_build_matches_reference(
            self.engine, self.project, "p2", {"on"}
        )
        self.assertFalse(result3.topic("branchy").ok)

        # ...and after repair the re-enabled branch uses the latest content.
        self.apply(
            [
                SetFragment(Fragment("b", (Text("b>"), Use("c")))),
                SetVariable("v", "9"),
            ]
        )
        result4 = self.assert_build_matches_reference(
            self.engine, self.project, "p2", {"on"}
        )
        self.assertEqual(result4.topic("branchy").text, "a>b>c=9")


class TestProfileIsolationAndImmutability(EngineCase):
    def test_profiles_do_not_pollute_each_other(self):
        project = Project(
            topics={
                "t": Topic(
                    "t",
                    (
                        When("x", then=(Text("X"),), otherwise=(Text("-"),)),
                        When("y", then=(Text("Y"),), otherwise=(Text("-"),)),
                    ),
                )
            }
        )
        engine = Engine(project)
        for _ in range(3):
            rx = self.assert_build_matches_reference(engine, project, "px", {"x"})
            ry = self.assert_build_matches_reference(engine, project, "py", {"y"})
            rn = self.assert_build_matches_reference(engine, project, "pn", set())
        self.assertEqual(rx.topic("t").text, "X-")
        self.assertEqual(ry.topic("t").text, "-Y")
        self.assertEqual(rn.topic("t").text, "--")

    def test_snapshot_immutability(self):
        project = Project(
            topics={"t": Topic("t", (Var("v"),))},
            variables={"v": "old"},
        )
        engine = Engine(project)
        snap = self.assert_build_matches_reference(engine, project, "p", set())
        self.assertEqual(snap.topic("t").text, "old")

        changes = [SetVariable("v", "new")]
        engine.apply(changes)
        project = apply_to_project(project, changes)
        fresh = self.assert_build_matches_reference(engine, project, "p", set())
        self.assertEqual(fresh.topic("t").text, "new")
        self.assertEqual(snap.topic("t").text, "old")
        with self.assertRaises(AttributeError):
            snap.topic("t").text = "hacked"

    def test_topic_add_and_delete(self):
        project = Project(topics={"a": Topic("a", (Text("A"),))})
        engine = Engine(project)
        self.assert_build_matches_reference(engine, project, "p", set())

        changes = [SetTopic(Topic("b", (Text("B"),))), DeleteTopic("a")]
        engine.apply(changes)
        project = apply_to_project(project, changes)
        result = self.assert_build_matches_reference(engine, project, "p", set())
        self.assertEqual(result.topic_ids, ("b",))
        self.assertEqual(result.topic("b").text, "B")


if __name__ == "__main__":
    unittest.main()
