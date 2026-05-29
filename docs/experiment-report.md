# 数据库系统实验报告

项目名称：寻根溯源族谱管理系统  
课程主题：数据库设计、实现、查询优化与验收材料整理  
技术栈：Python、Django、PostgreSQL、React、Vite、React Query

## 1. 实验目的

本实验围绕族谱管理业务设计并实现一个完整的数据库应用系统，重点训练从需求分析到数据库建模、约束设计、SQL 查询、数据导入导出、性能分析和界面演示的完整流程。

系统以“族谱”为数据隔离边界，以“成员”和“亲子关系”为核心数据对象，支持族谱信息维护、成员档案管理、亲子/婚姻关系管理、协作权限控制、递归关系查询、统计分析、COPY 导入导出以及索引性能对比。

## 2. 需求分析

### 2.1 功能需求

| 模块 | 主要功能 |
| --- | --- |
| 用户与权限 | 用户注册、登录、退出；按创建者、编辑者、只读协作者控制族谱访问权限 |
| 族谱管理 | 创建、查看、编辑、删除族谱；展示族谱基本信息和统计规模 |
| 成员管理 | 成员增删改查；记录姓名、性别、生卒年、字辈、排行、分支、生平简介等信息 |
| 关系管理 | 维护父亲、母亲两类亲子关系；维护婚姻关系及状态 |
| 查询分析 | 查询成员配偶与子女、祖先树、两人亲缘路径、统计 SQL 结果 |
| 图形展示 | 使用树形预览和 React 工作台展示后代关系图，支持拖拽、缩放和视口加载 |
| 数据交换 | 使用 PostgreSQL COPY 实现成员导入和分支族谱导出 |
| 性能分析 | 使用 EXPLAIN ANALYZE 对比有索引与禁用索引扫描时的递归查询性能 |

### 2.2 非功能需求

- 数据一致性：亲子关系必须发生在同一族谱内，成员不能成为自己的父母。
- 可维护性：后端模型、表单、服务、命令行脚本和前端工作台分层实现。
- 可扩展性：成员事件、协作权限、婚姻关系等独立成表，便于后续扩展地点、来源和影像资料。
- 大规模能力：课程数据脚本支持生成 10 部族谱、约 10 万名成员，其中至少一部族谱超过 5 万名成员，并保留 30 代以上深度链路。

## 3. 数据库设计

### 3.1 实体与关系

系统识别出 8 个核心实体：

| 实体 | 说明 |
| --- | --- |
| `users` | 系统用户，负责认证、创建族谱和协作 |
| `genealogies` | 族谱主表，是权限和数据隔离边界 |
| `genealogy_invitations` | 协作邀请流程记录 |
| `genealogy_collaborators` | 已生效的族谱协作者关系 |
| `members` | 族谱成员主档案 |
| `member_events` | 成员事件档案，如迁徙、居住、成就、安葬等 |
| `parent_child_relations` | 成员之间的父母子女关系 |
| `marriages` | 成员之间的婚姻/配偶关系 |

ER 图源文件位于 [er-diagram.mmd](/g:/WHU-CSLab-DB-Genealogy/docs/er-diagram.mmd)，详细设计说明位于 [database-design.md](/g:/WHU-CSLab-DB-Genealogy/docs/database-design.md)。

### 3.2 关系模式

核心关系模式如下：

```text
genealogies(genealogy_id PK, title, surname, compiled_at, description, created_by FK)
members(member_id PK, genealogy_id FK, full_name, surname, given_name, gender,
        birth_year, death_year, is_living, generation_label, seniority_text, branch_name)
parent_child_relations(relation_id PK, genealogy_id FK, parent_member_id FK,
                       child_member_id FK, parent_role)
marriages(marriage_id PK, genealogy_id FK, member_a_id FK, member_b_id FK,
          status, start_year, end_year)
member_events(event_id PK, genealogy_id FK, member_id FK, event_type, event_year)
```

### 3.3 约束设计

- 主键：各实体使用稳定自增 ID 作为主键，避免姓名重复导致识别错误。
- 外键：成员、关系、事件均通过 `genealogy_id` 归属到具体族谱。
- 检查约束：限制性别、亲子角色、婚姻状态、年份范围等枚举或数值合法性。
- 唯一约束：同一族谱内同一父母子女边不能重复；每个子女最多一位父亲和一位母亲。
- 触发器：PostgreSQL 触发器用于校验亲子关系同谱、出生年份先后，以及阻止亲子关系形成环。

## 4. 系统实现

### 4.1 后端实现

后端使用 Django 实现，主要代码位于 `backend/apps/genealogy/`：

| 文件 | 作用 |
| --- | --- |
| `models.py` | 定义族谱、成员、亲子关系、婚姻关系、协作等模型与约束 |
| `views.py` | 实现传统 Django 页面视图 |
| `api.py` | 为 React 工作台提供 JSON API |
| `services.py` | 封装后代图视口加载等查询逻辑 |
| `coursework.py` | 封装课程数据生成、COPY 导入导出、性能基准逻辑 |
| `management/commands/` | 提供课程验收所需命令行入口 |

### 4.2 前端实现

前端工作台位于 `frontend/`，使用 React + Vite + React Query 实现。入口为：

```text
http://127.0.0.1:5173/app/
```

工作台展示可访问族谱列表、当前族谱指标、功能入口、课程验收材料汇总和性能分析按钮。后代地图页面支持选择根成员、调整深度、拖拽缩放以及按视口加载节点。

### 4.3 数据生成与导入导出

课程数据脚本支持：

- `generate_course_dataset`：生成大规模族谱数据。
- `import_members_copy`：通过 PostgreSQL COPY 导入成员 CSV。
- `export_branch_copy`：导出指定根成员分支的成员、亲子关系和婚姻关系 CSV。
- `prepare_coursework_artifacts`：统一生成验收材料清单、样例 CSV、分支导出和性能报告。

验收材料说明见 [coursework-artifacts.md](/g:/WHU-CSLab-DB-Genealogy/docs/coursework-artifacts.md)。

## 5. 关键查询

### 5.1 祖先/后代递归查询

系统使用 PostgreSQL Recursive CTE 沿 `parent_child_relations` 递归展开族谱关系。例如四代后代查询：

```sql
WITH RECURSIVE descendant_levels AS (
    SELECT pcr.child_member_id AS member_id, 1 AS depth
    FROM parent_child_relations pcr
    WHERE pcr.genealogy_id = :genealogy_id
      AND pcr.parent_member_id = :root_member_id

    UNION ALL

    SELECT pcr.child_member_id AS member_id, dl.depth + 1 AS depth
    FROM descendant_levels dl
    INNER JOIN parent_child_relations pcr
        ON pcr.genealogy_id = :genealogy_id
       AND pcr.parent_member_id = dl.member_id
    WHERE dl.depth < 4
)
SELECT m.member_id, m.full_name, dl.depth
FROM descendant_levels dl
INNER JOIN members m ON m.member_id = dl.member_id
WHERE dl.depth = 4
ORDER BY m.member_id;
```

### 5.2 统计查询

统计分析页面覆盖成员总数、性别比例、寿命统计、代际深度、特殊成员筛选等需求，并在页面中展示关键 SQL，便于验收时说明查询来源。

## 6. 性能分析

### 6.1 索引设计

针对高频查询建立以下关键索引：

| 索引 | 作用 |
| --- | --- |
| `pcr_parent_lookup_idx(genealogy_id, parent_member_id)` | 支持从父节点快速查找子节点，是后代递归查询的核心索引 |
| `pcr_child_lookup_idx(genealogy_id, child_member_id)` | 支持从子节点回溯父母 |
| `members_genealogy_name_idx(genealogy_id, full_name)` | 支持族谱内成员姓名检索 |
| `members_genealogy_gender_idx(genealogy_id, gender)` | 支持统计分析中的性别过滤 |
| `members_full_name_trgm_idx(full_name gin_trgm_ops)` | 支持模糊姓名检索 |

### 6.2 界面内性能对比

本次补充了可视化性能分析入口：

```text
React 工作台首页 -> 选择族谱 -> 性能分析 -> 运行对比
```

点击按钮后，前端调用：

```text
GET /api/genealogies/<genealogy_id>/benchmarks/parent-lookup/
```

后端会对同一条四代后代递归查询执行两次 `EXPLAIN ANALYZE`：

1. 有索引：使用数据库正常执行计划。
2. 禁用索引扫描：在事务内执行 `SET LOCAL enable_indexscan = off`、`enable_bitmapscan = off`、`enable_indexonlyscan = off`，模拟无索引扫描效果。

该方法不会删除真实索引，也不会破坏数据库结构，适合课堂验收时反复点击演示。

界面会展示：

- 根成员 ID
- 命中的索引名称
- 有索引执行时间
- 禁用索引扫描执行时间
- 加速倍数
- 扫描类型，例如 `Index Scan`、`Bitmap Index Scan`、`Seq Scan`
- 执行计划摘要和完整 SQL

### 6.3 预期结论

在大规模亲子关系表上，递归查询每一层都需要根据 `parent_member_id` 找到子节点。若存在 `(genealogy_id, parent_member_id)` 复合索引，数据库可以快速定位当前父节点的子女集合；禁用索引扫描后，执行计划通常会退化为顺序扫描，扫描范围扩大，执行时间明显上升。

因此，`pcr_parent_lookup_idx` 对后代树、祖先追溯、分支导出和四代后代查询均具有直接优化作用。

## 7. 测试与验证

项目提供以下验证方式：

```powershell
.\scripts\dev\check.cmd
.\scripts\dev\test.cmd
cd frontend
npm run build
```

测试覆盖内容包括：

- 用户访问控制和协作权限。
- 族谱、成员、关系、事件的增删改查。
- 关系合法性校验。
- JSON API 路由 smoke test。
- 后代地图视口 API。
- 课程数据生成、COPY 导入导出和性能基准命令。

## 8. 验收材料清单

| 材料 | 路径 |
| --- | --- |
| 实验报告 | `docs/experiment-report.md` |
| 数据库设计文档 | `docs/database-design.md` |
| 数据库设计复核 | `docs/database-design-review.md` |
| ER 图源文件 | `docs/er-diagram.mmd` |
| 课程验收材料说明 | `docs/coursework-artifacts.md` |
| 演示自检清单 | `docs/course-demo-checklist.md` |
| 初始建表 SQL | `sql/001_initial_schema.sql` |
| 后端核心实现 | `backend/apps/genealogy/` |
| 前端工作台 | `frontend/src/` |
| 生成的本地验收产物 | `output/coursework/` |

## 9. 总结

本实验完成了一个面向族谱管理场景的数据库应用系统，覆盖 ER 建模、关系模式转换、范式与约束设计、Django 后端实现、React 前端展示、递归 SQL 查询、COPY 数据交换和索引性能分析。系统既能满足课程要求中的功能演示，也能通过大规模数据生成和 `EXPLAIN ANALYZE` 证明索引设计对递归查询性能的优化效果。
