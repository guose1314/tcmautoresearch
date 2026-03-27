# 示例提示词库（统一格式版）

## 通用调用规则
- 明确范围（全仓库或具体路径）。
- 明确重点维度（可靠性/性能/安全/测试）。
- 明确是否需要执行命令或仅只读分析。
- 要求按统一模板输出：`docs/agent-standards/unified-output-template.md`。

## Risk Audit Readonly（只读审计）
1. 对 `src/` 与 `config.yml` 做只读风险审计，重点检查可靠性与安全风险。不要改代码，按统一模板输出，并给出按 HIGH/MEDIUM/LOW 排序的风险清单。
2. 仅审计 `integration_tests/` 与 `tests/`，识别测试缺口与可观测性缺口。不要改动文件，按统一模板输出，给出前 10 条修复优先级建议。
3. 对全仓库进行发布前只读审计，重点关注配置错误、日志泄露与异常处理缺陷。输出必须包含证据路径 `path:line`。

## Test Hardening Engineer（测试强化）
1. 针对 `src/research` 与 `src/llm` 做测试强化：补齐关键分支单测并处理 flaky 问题，目标覆盖率 >=90%，按统一模板输出。
2. 仅处理当前失败率最高的 5 个 flaky 测试，定位根因并修复。输出包含修复前后多轮运行统计，按统一模板输出。
3. 对 `tests/` 与 `integration_tests/` 做稳定性治理，优先消除时间依赖和外部服务不确定性。覆盖率与稳定性结果按统一模板输出。

## Security Critical Engineer（安全专用）
1. 对 `src/` 进行高危安全治理，重点检查注入、反序列化、密钥与配置泄露。修复后按统一模板输出证据、改动与验证结果。
2. 仅针对命令执行与输入边界做安全加固，要求最小改动。按统一模板输出，风险分级必须使用 HIGH/MEDIUM/LOW。
3. 对可能处理敏感数据的模块做安全审计与修复，补充必要安全测试，按统一模板输出残余风险与缓解建议。

## 组合场景（建议）
1. 先运行 Risk Audit Readonly 输出风险清单，再把 HIGH 风险交给 Security Critical Engineer 修复，最后由 Test Hardening Engineer 做回归与稳定性加固。
2. 每周例行：先做只读审计，再做测试强化，月末做安全专项。
