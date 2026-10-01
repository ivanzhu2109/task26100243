# docforge：进程内增量文档装配库

纯 Python、零依赖的文档装配库。项目由以 ID 寻址的**主题（Topic）**、
**片段（Fragment）**和**字符串变量**组成；调用串行，输出可放入内存。
任意修改或标签切换后的增量构建，与当前源码的无缓存全量构建逐主题一致。

## 正文节点

正文是节点序列，支持四种节点（见 `docforge/model.py`）：

| 节点 | 语义 |
| --- | --- |
| `Text(text)` | 原样输出文本 |
| `Var(name)` | 读取字符串变量 |
| `Use(fragment)` | 展开片段 |
| `When(tag, then, otherwise)` | 按标签是否启用选择分支，只求值选中的分支 |

## 快速开始

```python
from docforge import (
    Engine, Project, Topic, Fragment,
    Text, Var, Use, When,
    UpsertFragment, SetVariable, RemoveVariable,
)

project = Project(
    topics={"greeting": Topic((Text("你好，"), Var("user"), Use("suffix")))},
    fragments={
        "suffix": Fragment((
            When("formal", then=(Text("，您好。"),), otherwise=(Text("！"),)),
        )),
    },
    variables={"user": "世界"},
)

engine = Engine(project)                 # 创建引擎时接收初始项目

s1 = engine.build("web", tags=[])        # profile 是稳定配置 ID
print(s1.results["greeting"].text)       # 你好，世界！

s2 = engine.build("web", tags=["formal"])
print(s2.results["greeting"].text)       # 你好，世界，您好。

engine.apply([                           # 增删改主题、片段或变量
    SetVariable("user", "月球"),
    UpsertFragment("suffix", Fragment((Text("～"),))),
])
s3 = engine.build("web", tags=[])
print(s3.results["greeting"].text)       # 你好，月球～

assert s1.results["greeting"].text == "你好，世界！"   # 旧快照不可变
```

## API

- `Engine(project)`：以初始项目创建引擎。
- `engine.apply(changes)`：应用一批变更，可选
  `UpsertTopic` / `RemoveTopic` / `UpsertFragment` / `RemoveFragment` /
  `SetVariable` / `RemoveVariable`（见 `docforge/changes.py`）。
- `engine.build(profile, tags)`：`profile` 为稳定配置 ID，`tags`
  为本次启用的标签集合；返回不可变 `Snapshot`，其
  `results[topic_id]` 为 `TopicResult(ok, text, error)`。

## 语义保证

- **一致性**：增量构建与无缓存全量构建逐主题一致（正文与成败状态）。
- **快照不可变**：`Snapshot` 及其结果映射只读，旧快照永不变化。
- **配置隔离**：各 `profile` 的缓存相互独立，标签切换不互相污染。
- **失败隔离**：活跃路径上的缺失变量、缺失片段或片段环只使该主题失败，
  无关主题照常成功；补齐对象、断开环后自动恢复。
- **惰性分支**：未选分支中的错误不影响结果；重新启用分支时使用最新内容，
  失败结果同样自动失效。

引擎内部按配置缓存片段/主题展开结果，并用依赖反向索引做精确失效：
`apply` 只清除依赖于被改对象的缓存项。

## 运行测试

```bash
python3 -m pytest tests/ -q
```

测试包含：`tests/test_engine.py` 的场景化用例（双配置交替构建与隐藏分支
修改、预热链上的缺失引用与环的制造/修复、快照不可变、主题增删），以及
`tests/test_differential.py` 的随机差分测试。所有构建都与
`tests/reference.py` 中独立实现的无缓存参考展开器逐主题核对。
