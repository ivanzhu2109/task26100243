"""引擎与无缓存参考展开器逐主题核对的自动化测试。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docforge import (
    Engine,
    Fragment,
    Project,
    RemoveFragment,
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
from docforge.changes import RemoveTopic
import reference


class Mirror:
    """把同一批变更同时应用到一份普通 Project 上，供参考展开器使用。"""

    def __init__(self, project: Project):
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
            else:
                raise TypeError(change)


def apply_both(engine, mirror, changes):
    changes = list(changes)
    engine.apply(changes)
    mirror.apply(changes)


def check(engine, mirror, profile, tags):
    """引擎构建结果必须与参考展开器逐主题一致（正文与成败状态）。"""
    snapshot = engine.build(profile, tags)
    expected = reference.expand_all(mirror.project, frozenset(tags))
    assert set(snapshot.results) == set(expected)
    for topic_id, (ok, value) in expected.items():
        result = snapshot.results[topic_id]
        assert result.ok == ok, f"{profile}/{topic_id}: ok 不一致"
        if ok:
            assert result.text == value, f"{profile}/{topic_id}: 正文不一致"
            assert result.error is None
        else:
            assert result.error == value, f"{profile}/{topic_id}: 错误不一致"
            assert result.text is None
    return snapshot


def nested_project():
    """嵌套片段项目：show 标签控制 hidden 分支，hidden 引用 fh 与变量 vh。"""
    return Project(
        topics={
            "main": Topic((Text("["), Use("outer"), Text("]"))),
            "other": Topic((Text("plain "), Var("vbase"))),
        },
        fragments={
            "outer": Fragment(
                (
                    Text("O"),
                    Use("inner"),
                    When(
                        "show",
                        then=(Text("H"), Use("fh"), Var("vh")),
                        otherwise=(Text("-"),),
                    ),
                )
            ),
            "inner": Fragment((Text("I"), Var("vbase"))),
            "fh": Fragment((Text("fh"), Var("vh"))),
        },
        variables={"vbase": "B", "vh": "v1"},
    )


def test_two_profiles_alternating_hidden_branch_updates():
    engine = Engine(nested_project())
    mirror = Mirror(nested_project())

    # 两个配置以不同标签集合交替构建同一嵌套片段。
    snap_a1 = check(engine, mirror, "alpha", [])
    snap_b1 = check(engine, mirror, "beta", ["show"])
    assert snap_a1.results["main"].text == "[OIB-]"
    assert snap_b1.results["main"].text == "[OIBHfhv1v1]"

    # 修改仅被隐藏分支引用的片段和变量：对 alpha 而言该分支未选中。
    apply_both(engine, mirror, [
        UpsertFragment("fh", Fragment((Text("FH2"), Var("vh")))),
        SetVariable("vh", "v2"),
    ])
    snap_a2 = check(engine, mirror, "alpha", [])
    snap_b2 = check(engine, mirror, "beta", ["show"])
    assert snap_a2.results["main"].text == "[OIB-]"
    assert snap_b2.results["main"].text == "[OIBHFH2v2v2]"

    # alpha 启用该分支：必须使用最新内容。
    snap_a3 = check(engine, mirror, "alpha", ["show"])
    assert snap_a3.results["main"].text == "[OIBHFH2v2v2]"

    # 切回隐藏后再次修改，再启用：仍是最新内容。
    snap_a4 = check(engine, mirror, "alpha", [])
    apply_both(engine, mirror, [
        UpsertFragment("fh", Fragment((Text("FH3"),))),
        SetVariable("vh", "v3"),
    ])
    snap_a5 = check(engine, mirror, "alpha", ["show"])
    snap_b3 = check(engine, mirror, "beta", ["show"])
    assert snap_a5.results["main"].text == "[OIBHFH3v3]"
    assert snap_b3.results["main"].text == "[OIBHFH3v3]"

    # 旧快照不得变化。
    assert snap_a1.results["main"].text == "[OIB-]"
    assert snap_b1.results["main"].text == "[OIBHfhv1v1]"
    assert snap_a2.results["main"].text == "[OIB-]"
    assert snap_b2.results["main"].text == "[OIBHFH2v2v2]"
    assert snap_a3.results["main"].text == "[OIBHFH2v2v2]"
    assert snap_a4.results["main"].text == "[OIB-]"

    # 配置互不污染：beta 从未受 alpha 的标签切换影响。
    assert snap_b3.results["other"].text == "plain B"


def test_missing_and_cycle_in_warmed_chain_then_repair():
    project = Project(
        topics={
            "chain": Topic((Use("f1"),)),
            "safe": Topic((Text("ok"),)),
            "branchy": Topic(
                (
                    When(
                        "risky",
                        then=(Use("gone"), Use("loop")),
                        otherwise=(Text("calm"),),
                    ),
                )
            ),
        },
        fragments={
            "f1": Fragment((Text("1"), Use("f2"))),
            "f2": Fragment((Text("2"), Use("f3"))),
            "f3": Fragment((Text("3"), Var("tail"))),
        },
        variables={"tail": "T"},
    )
    engine = Engine(project)
    mirror = Mirror(project)

    # 预热片段链。
    warm = check(engine, mirror, "p", [])
    assert warm.results["chain"].text == "123T"

    # 制造缺失引用（变量与片段）。
    apply_both(engine, mirror, [
        RemoveVariable("tail"),
        UpsertFragment("f2", Fragment((Text("2"), Use("missing")))),
    ])
    broken = check(engine, mirror, "p", [])
    assert not broken.results["chain"].ok
    assert broken.results["chain"].error == "missing fragment: missing"
    assert broken.results["safe"].text == "ok"

    # 补齐片段后暴露出缺失变量，仍失败。
    apply_both(engine, mirror, [
        UpsertFragment("missing", Fragment((Text("M"),))),
    ])
    still_broken = check(engine, mirror, "p", [])
    assert still_broken.results["chain"].ok
    # f2 不再引用 f3，tail 缺失不再影响 chain。
    assert still_broken.results["chain"].text == "12M"

    # 恢复 f2 引用 f3，此时 tail 仍缺失：失败。
    apply_both(engine, mirror, [
        UpsertFragment("f2", Fragment((Text("2"), Use("f3")))),
    ])
    missing_var = check(engine, mirror, "p", [])
    assert not missing_var.results["chain"].ok
    assert missing_var.results["chain"].error == "missing variable: tail"

    # 制造环：f3 -> f1。
    apply_both(engine, mirror, [
        SetVariable("tail", "T"),
        UpsertFragment("f3", Fragment((Text("3"), Use("f1")))),
    ])
    cycled = check(engine, mirror, "p", [])
    assert not cycled.results["chain"].ok
    assert cycled.results["chain"].error.startswith("fragment cycle:")
    assert cycled.results["safe"].text == "ok"

    # 断开环后自动恢复。
    apply_both(engine, mirror, [
        UpsertFragment("f3", Fragment((Text("3"), Var("tail")))),
    ])
    healed = check(engine, mirror, "p", [])
    assert healed.results["chain"].text == "123T"

    # 未选分支中的同类错误（缺失片段 + 环）不得报错。
    apply_both(engine, mirror, [
        UpsertFragment("loop", Fragment((Use("loop"),))),
    ])
    calm = check(engine, mirror, "p", [])
    assert calm.results["branchy"].text == "calm"

    # 启用该分支则报错；失败结果缓存后，修复即自动失效恢复。
    risky1 = check(engine, mirror, "p", ["risky"])
    assert not risky1.results["branchy"].ok
    apply_both(engine, mirror, [
        UpsertFragment("gone", Fragment((Text("G"),))),
        UpsertFragment("loop", Fragment((Text("L"),))),
    ])
    risky2 = check(engine, mirror, "p", ["risky"])
    assert risky2.results["branchy"].text == "GL"

    # 旧快照不变。
    assert warm.results["chain"].text == "123T"
    assert not broken.results["chain"].ok
    assert not cycled.results["chain"].ok
    assert not risky1.results["branchy"].ok


def test_snapshot_is_immutable():
    engine = Engine(nested_project())
    snapshot = engine.build("p", [])
    with pytest.raises(TypeError):
        snapshot.results["main"] = None
    with pytest.raises(AttributeError):
        snapshot.profile = "q"


def test_topic_add_and_remove():
    engine = Engine(nested_project())
    mirror = Mirror(nested_project())
    check(engine, mirror, "p", [])
    apply_both(engine, mirror, [
        UpsertTopic("extra", Topic((Text("E"), Var("vbase")))),
    ])
    snap = check(engine, mirror, "p", [])
    assert snap.results["extra"].text == "EB"
    apply_both(engine, mirror, [RemoveTopic("extra")])
    snap2 = check(engine, mirror, "p", [])
    assert "extra" not in snap2.results
