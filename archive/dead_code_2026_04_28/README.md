# archive/dead_code_2026_04_28

T1.6 死代码清理（保守版）。本目录归档全仓 grep 命中为 0 的纯孤儿脚本，不再作为构建/测试/运行时依赖；保留以便日后审计与考古回溯。

## 归档清单

| 归档文件 | 来源路径 | 最后一次提交 | 归档理由 |
|---|---|---|---|
| `_create_web_shims.py` | `tools/_create_web_shims.py` | `d3f8cca` feat: Phase 0-2 complete — debt cleanup, infra unification, orchestration decoupling | 全仓 grep 0 命中；Web shim 重建脚本，已被现行 `src/web/` 模块结构取代 |
| `_fix_observe_refs.py` | `tools/_fix_observe_refs.py` | `d3f8cca` feat: Phase 0-2 complete — debt cleanup, infra unification, orchestration decoupling | 全仓 grep 仅自身 docstring 命中；observe phase 引用一次性修补脚本，目标已固化 |

## 未归档但曾被审视

- `src/research/tcm_reasoning/` —— grep 命中 20+（架构文档与单测 `tests/unit/test_tcm_reasoning.py` 引用），属于已接入模块，**保留**。
- `tools/_extract_observe_phase.py` / `tools/_rebuild_observe_phase.py` —— 被 [tests/unit/test_architecture_regression_guard.py](../../tests/unit/test_architecture_regression_guard.py) 显式白名单引用，**保留在 `tools/`**。

## 复活流程

如需复活，请：
1. 先 grep 当前消费方与依赖；
2. `git mv` 还原回原路径；
3. 在主链 README 或对应模块文档登记其新角色。
