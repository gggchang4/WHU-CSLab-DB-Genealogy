# 课程验收产物生成说明

本文档说明如何生成课程验收需要的本地产物，包括 COPY 导入样例、分支导出 CSV、四代后代查询 `EXPLAIN ANALYZE` 报告和产物清单。

## 产物目录

默认产物目录为：

```text
output/coursework/
```

该目录已被 `.gitignore` 忽略。真实大规模 CSV、导出文件和基准报告保留在本机，不进入 Git 仓库。

## 小规模 Smoke 流程

用于快速验证命令链路是否完整：

```powershell
.\scripts\dev\coursework-artifacts.cmd
```

该脚本会执行：

```powershell
.\.venv\Scripts\python.exe backend\manage.py prepare_coursework_artifacts --create-smoke-data
```

默认会生成一个小规模演示族谱，然后输出：

- `output/coursework/sample-import/members.csv`
- `output/coursework/branch-export/branch_members.csv`
- `output/coursework/branch-export/branch_parent_child_relations.csv`
- `output/coursework/branch-export/branch_marriages.csv`
- `output/coursework/benchmarks/parent_lookup.md`
- `output/coursework/artifact-manifest.md`

`artifact-manifest.md` 会记录数据库名、用户、主机、端口、产物路径和复现命令，但不会记录数据库密码。

## 只生成材料骨架

如果不希望写入任何业务数据，只生成样例导入 CSV 和 manifest：

```powershell
.\.venv\Scripts\python.exe backend\manage.py prepare_coursework_artifacts
```

这种模式不会自动运行分支导出和性能基准，因为缺少明确的族谱 ID 与根成员 ID。

## 针对已有数据生成产物

如果数据库中已经有可演示族谱，直接指定族谱和根成员：

```powershell
.\.venv\Scripts\python.exe backend\manage.py prepare_coursework_artifacts --genealogy-id 1 --root-member-id 1
```

这会基于指定成员生成分支导出 CSV，并生成四代后代查询的有索引 / 无索引 `EXPLAIN ANALYZE` 对比报告。

## 完整课程规模数据

课程要求的完整规模为 `10` 个族谱、总计 `100000` 成员、至少一个族谱 `50000+` 成员，并保留 `30` 代链路深度。执行：

```powershell
.\.venv\Scripts\python.exe backend\manage.py generate_course_dataset
```

生成完成后，从命令输出中选取 `genealogy_id` 和适合的根成员 ID，再执行：

```powershell
.\.venv\Scripts\python.exe backend\manage.py prepare_coursework_artifacts --genealogy-id <genealogy_id> --root-member-id <root_member_id>
```

## 单独命令

COPY 成员导入：

```powershell
.\.venv\Scripts\python.exe backend\manage.py import_members_copy --genealogy-id <genealogy_id> --csv output\coursework\sample-import\members.csv
```

分支导出：

```powershell
.\.venv\Scripts\python.exe backend\manage.py export_branch_copy --genealogy-id <genealogy_id> --root-member-id <root_member_id> --output-dir output\coursework\branch-export
```

四代后代查询基准：

```powershell
.\.venv\Scripts\python.exe backend\manage.py benchmark_parent_lookup --genealogy-id <genealogy_id> --root-member-id <root_member_id> --output output\coursework\benchmarks\parent_lookup.md
```

## 自检

生成产物前后建议运行：

```powershell
.\scripts\dev\check.cmd
.\scripts\dev\lint.cmd
.\scripts\dev\test.cmd
```
