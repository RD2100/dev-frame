# Codegraph-First Rule

> 状态: active
> 范围: ai-workflow-hub 项目内所有代码探索、重构、修改

## 规则

修改任何 Python 文件前，**必须先查 codegraph**。禁止直接 grep/read 盲目翻代码。

## 强制使用场景

| 场景 | 用这个 | 不用这个 |
|------|--------|----------|
| "这个函数在哪定义的" | `codegraph_search` | Grep |
| "谁调用了这个函数" | `codegraph_callers` | 人工翻 import |
| "这个模块做什么的" | `codegraph_context` | Read 多个文件 |
| "改这个会影响什么" | `codegraph_impact` | 猜测 + grep |
| "这个符号的源码" | `codegraph_node` 或 `codegraph_explore` | Read |
| "这个目录有什么" | `codegraph_files` | ls/find |

## 反模式

```python
# 不要这样 —— 盲目查
grep "executor_node" -r src/
read executor.py  # 不知道里面有什么

# 应该这样 —— 先查 codegraph
codegraph_context(pattern="executor_node")
# 拿到函数签名、调用者、被调用者，再决定读哪个文件
```

## 例外

以下场景可以直接 Grep/Read，不需要 codegraph：
- 读已知文件的具体行（已经知道文件和行号）
- 查配置文件的键值（yaml/json/toml）
- 找字符串常量/错误消息（不是符号）
- 少于 3 次搜索的简单定位

## 审计

2026-05-24 | RD | 初始创建：强制使用 codegraph 做代码探索
