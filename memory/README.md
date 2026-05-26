# Project Memory

AI Workflow Hub 项目经验知识库。新 agent 进入项目时按需加载。

## 目录结构

```
memory/
  README.md              ← 本文件：分类说明、命名规范
  _template.md           ← 卡片模板
  gotcha_*.md            ← 踩过的坑和修复
  pattern_*.md           ← 稳定复用模式
  decision_*.md          ← 架构决策记录
```

## 分类

| 类型 | 前缀 | 内容 | 示例 |
|------|------|------|------|
| gotcha | `gotcha_` | 踩坑经验、修复方案、避免方法 | `gotcha_pipe_deadlock.md` |
| pattern | `pattern_` | 标准流程、字段规范、验收证据 | `pattern_backend_calls.md` |
| decision | `decision_` | 架构决策、为什么这么做、何时重新评估 | `decision_primary_claude.md` |

## 何时新增 memory

- 任何导致 workflow 失败或假阳性的 bug 修复后 → gotcha
- 任何经过 5+ 轮验证的标准做法 → pattern
- 任何涉及 backend/架构/安全策略的选择 → decision

## 命名规范

- 小写 + 下划线
- 前缀必须匹配分类
- 名字描述核心内容，不超过 40 字符

## 引用方式

在报告或 CLAUDE.md 中引用：

```markdown
See memory/gotcha_pipe_deadlock.md for root cause.
```

不要把所有 memory 内容塞进 CLAUDE.md。CLAUDE.md 只放入口。
