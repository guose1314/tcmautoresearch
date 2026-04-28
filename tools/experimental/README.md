# tools/experimental

非主链工具目录。此处的脚本不参与主链调用与 CI 主流程；运行需自行核对兼容性、依赖与数据库 schema 是否仍然匹配。

当前归档脚本：

- `innovation_incentives.py` —— 创新激励评估实验；保留单测 `tests/unit/test_innovation_incentives.py`，导入路径已迁移为 `tools.experimental.innovation_incentives`。
- `ingest_medical_sft.py` —— Medical SFT 数据摄入实验脚本，无主链消费。
- `migrate_kg_db.py` —— 旧版知识图谱 SQLite 迁移，已被现行 schema 取代。
- `migrate_orm_extras.py` —— ORM 扩展字段一次性迁移。
- `migrate_sqlite_to_dual_db.py` —— 单库到双库迁移历史脚本。
- `migrate_v2.py` —— v2 schema 迁移历史脚本。

约定：未来新增"非主链/一次性/实验性"脚本一律放入本目录，并在此 README 追加一行说明。
