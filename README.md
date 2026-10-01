# docassemble — 进程内增量文档装配库

纯 Python、零依赖、单进程内存内运行。项目由以 ID 寻址的**主题（Topic）**、
**片段（Fragment）** 和**字符串变量**组成；正文是节点序列：

| 节点 | 语义 |
| --- | --- |
| `Text(text)` | 原样输出文本 |
| `Var(name)` | 读取字符串变量，缺失则所在主题失败 |
| `Use(fragment_id)` | 展开片段，缺失或成环则所在主题失败 |
| `When(tag, then, otherwise)` | 按标签是否启用选择分支，只求值选中的分支 |

## 快速开始

```python
from docassemble import (
    Engine, Project, Topic, Fragment,
    Text, Var, Use, When,
    SetVariable, SetFragment, DeleteFragment,
)

project = Project(
    topics={
        "greeting": Topic("greeting", (
            Text("Hello, "), Var("user"), Text("! "),
            Use("footer"),
            When("beta", then=(Text(" [beta]"),), otherwise=()),
        )),
    },
    fragments={"footer": Fragment("footer", (Text("-- footer"),))},
    variables={"user": "ivan"},
)

engine = Engine(project)                 # 创建引擎时接收初始项目
result = engine.build("web", {"beta"})   # profile=稳定配置ID, tags=本次启用标签
print(result.topic("greeting").text)     # Hello, ivan! -- footer [beta]

# 增量修改：增删改主题 / 片段 / 变量
engine.apply([
    SetVariable("user", "ada"),
    SetFragment(Fragment("footer", (Text("-- v2"),))),
])
fresh = engine.build("web", {"beta"})
print(fresh.topic("greeting").text)      # Hello, ada! -- v2 [beta]
print(result.topic("greeting").text)     # 旧快照不变：Hello, ivan! -- footer [beta]
```

## API

- `Engine(project)`：以初始项目创建引擎。
- `engine.apply(changes)`：应用变更序列。变更为
  `SetTopic / DeleteTopic / SetFragment / DeleteFragment / SetVariable / DeleteVariable`。
- `engine.build(profile, tags) -> BuildResult`：对当前项目做一次构建。
  `profile` 是稳定配置 ID（缓存按配置隔离，互不污染）；`tags` 是本次启用的标签集合。
- `BuildResult`：不可变快照。`result.topic(topic_id) -> TopicResult`，
  `TopicResult.ok` 为真时 `text` 是输出字符串，否则 `error` 是失败原因。

## 语义保证

- 每次构建只展开活跃路径；未选中分支中的缺失变量、缺失片段、片段环不影响结果。
- 活跃路径上的缺失变量 / 缺失片段 / 片段环使对应主题失败，其余主题不受影响。
- 任意修改或标签切换后的构建，与当前源码的无缓存全量构建逐主题一致
  （正文与成败状态均一致）；补齐对象、断开环后自动恢复。
- 返回的 `BuildResult` / `TopicResult` 不可变，旧快照永不变化。

## 实现要点

- 引擎按 `(profile, fragment/topic)` 缓存展开结果，缓存项记录传递依赖
  （变量、片段、主题）与实际读取的标签及取值。
- `apply` 只失效依赖交集命中的缓存项；标签切换时按"读取过的标签取值是否一致"
  判定缓存是否可复用，因此隐藏分支的修改不会污染其它配置的输出。
- 环检测失败与路径相关，不写入缓存；缺失对象失败与上下文无关，可缓存并随修复自动失效。

## 运行测试

```bash
python3 -m unittest discover -s tests -v
```

测试包含一个无缓存参考展开器（`docassemble/reference.py`），
每个用例的每次构建都与参考展开器逐主题核对；`tests/test_fuzz.py`
以固定种子随机施加 300 步修改与标签切换做差分验证。
