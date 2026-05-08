# 数据库设计审核与说明文档

## 1. 审核结论

当前数据库设计能够满足《“寻根溯源”族谱管理系统》课程实验要求，也能够支撑下一步 Django + PostgreSQL 应用开发。现有设计已经覆盖课程要求中的 ER 图、关系模式、3NF/BCNF 分析、主键/外键/CHECK 约束、索引设计、递归查询、大规模数据生成、COPY 导入导出和性能对比等关键验收点。

本次审核未发现必须调整表结构、ER 图或索引设计的问题，因此不修改现有 schema、models、migrations 或 ER 图。应用运行时以 Django migrations 为准；[sql/001_initial_schema.sql](/g:/WHU-CSLab-DB-Genealogy/sql/001_initial_schema.sql) 可作为课程 DDL 展示和独立初始化参考，不建议在已经由 Django migrations 初始化的同一个数据库中重复执行。

已核对的主要材料包括：

- [docs/project-spec.md](/g:/WHU-CSLab-DB-Genealogy/docs/project-spec.md)：课程要求整理
- [docs/database-design.md](/g:/WHU-CSLab-DB-Genealogy/docs/database-design.md)：数据库设计主文档
- [docs/er-diagram.mmd](/g:/WHU-CSLab-DB-Genealogy/docs/er-diagram.mmd)：ER 图 Mermaid 源文件
- [sql/001_initial_schema.sql](/g:/WHU-CSLab-DB-Genealogy/sql/001_initial_schema.sql)：PostgreSQL DDL
- `backend/apps/genealogy/models.py` 与 migrations：Django ORM 和迁移实现

现有测试验证结果：`scripts\dev\test.cmd` 已通过，结果为 `39 tests OK`。

## 2. 表设计说明

系统当前识别出 8 张核心业务表。这组表的粒度比较克制，既覆盖课程功能，又避免过早引入来源、媒体、地点等二期实体，适合当前实验阶段。

| 表 | 职责 | 设计评价 |
| --- | --- | --- |
| `users` | 系统用户、登录身份、族谱创建者和协作者身份来源 | 满足注册、登录、权限识别要求；通过 `username` 和 `email` 唯一约束避免账户重复 |
| `genealogies` | 族谱主档，作为权限和数据隔离边界 | 以 `genealogy_id` 隔离不同族谱，适合多用户、多族谱场景 |
| `genealogy_invitations` | 协作邀请流转记录 | 保留邀请发起人、被邀请人、状态和时间，便于追踪协作来源 |
| `genealogy_collaborators` | 已生效的族谱协作者授权 | 将“邀请过程”和“授权结果”拆开，权限语义清晰 |
| `members` | 家族成员主档 | 使用 `member_id` 作为稳定唯一标识，解决同名同姓和不同辈分成员识别问题 |
| `member_events` | 成员扩展事件档案 | 与 `members` 分离，避免主表过宽，同时支持迁徙、任职、成就、安葬等档案扩展 |
| `parent_child_relations` | 父母与子女的基础血缘边 | 只存基础亲子关系，祖先、后代、兄弟等关系通过递归查询推导 |
| `marriages` | 婚姻/配偶关系边 | 使用成员双端关系表达配偶事实，支持配偶查询和亲缘路径查询 |

这个设计的核心优点是“事实少而稳定”。数据库只落库成员、亲子边、婚姻边等基础事实，兄弟姐妹、祖孙、叔侄、姻亲、代际层级等派生关系都通过 SQL 或应用服务计算。这样可以减少冗余，避免基础关系变更后派生数据失效。

## 3. ER 图设计说明

当前 ER 图能够覆盖课程要求的实体、属性和联系基数。主要关系如下：

| ER 联系 | 基数 | 说明 |
| --- | --- | --- |
| `USERS -> GENEALOGIES` | 1:N | 一个用户可创建多个族谱，一个族谱只有一个创建者 |
| `GENEALOGIES -> MEMBERS` | 1:N | 一个族谱包含多个成员，每个成员只属于一个族谱 |
| `MEMBERS -> MEMBER_EVENTS` | 1:N | 一个成员可拥有多条扩展事件档案 |
| `USERS <-> GENEALOGIES` | M:N | 通过 `genealogy_collaborators` 表实现协作授权 |
| `MEMBERS <-> MEMBERS` | M:N | 通过 `parent_child_relations` 表表达自关联亲子关系 |
| `MEMBERS <-> MEMBERS` | M:N | 通过 `marriages` 表表达自关联婚姻关系 |
| `GENEALOGY_INVITATIONS -> GENEALOGY_COLLABORATORS` | 1:0..1 | 一条已接受邀请最多激活一个协作者关系 |

ER 图中将亲子关系和婚姻关系建模为独立关系表，而不是在 `members` 表中放 `father_id`、`mother_id` 或 `spouse_id` 字段，这是合理的。原因是：

- 亲子关系天然是成员到成员的自关联，独立关系表更适合递归查询。
- 婚姻关系可能带有状态、开始年份、结束年份和备注，独立表可以保存关系属性。
- 关系表可以增加唯一约束、组合外键和索引，数据库层更容易保证同族谱内连边。
- 后续若要扩展历史婚姻、婚配说明或关系审计，不需要改造 `members` 主表。

因此，当前 [er-diagram.mmd](/g:/WHU-CSLab-DB-Genealogy/docs/er-diagram.mmd) 可以直接用于实验报告中的 ER 图部分。

## 4. 关系模式设计说明

ER 图转换为关系模式后，当前设计采用单列代理主键作为实体标识，并用外键表达实体之间的引用关系。核心关系模式可概括为：

```text
users(user_id PK, username UK, email UK, password_hash, display_name, ...)
genealogies(genealogy_id PK, created_by FK, title, surname, compiled_at, ...)
genealogy_invitations(invitation_id PK, genealogy_id FK, inviter_user_id FK, invitee_user_id FK, status, ...)
genealogy_collaborators(collaborator_id PK, genealogy_id FK, user_id FK, source_invitation_id FK, role, ...)
members(member_id PK, genealogy_id FK, full_name, gender, birth_year, death_year, ...)
member_events(event_id PK, genealogy_id FK, member_id FK, event_type, event_year, ...)
parent_child_relations(relation_id PK, genealogy_id FK, parent_member_id FK, child_member_id FK, parent_role, ...)
marriages(marriage_id PK, genealogy_id FK, member_a_id FK, member_b_id FK, status, ...)
```

范式层面，当前关系模式至少满足 `3NF`：

- 每张表都有明确主键，非主属性直接描述该主键对应的实体或关系事实。
- 没有使用姓名作为成员主键，因此避免了“姓名 -> 成员事实”的错误函数依赖。
- `members` 表没有存储可由亲子关系推导出的代数、祖先、后代等派生字段。
- `member_events` 将扩展档案拆出，避免把可重复事件塞入成员主表形成非原子字段。
- `genealogy_collaborators` 将多用户与多族谱的 M:N 关系单独成表，避免在 `users` 或 `genealogies` 中存储列表型字段。

除 `members` 保留了 `generation_label`、`seniority_text`、`branch_name` 等展示/档案字段外，其余主表基本可以按 `BCNF` 解释。`members` 中这些字段仍直接依赖 `member_id`，不引入传递依赖，因此满足 `3NF` 没有问题。

## 5. 约束设计说明

当前约束设计覆盖了课程要求中的主键、外键和 CHECK 约束，也额外补充了同族谱关系校验和触发器规则，适合后续开发。

### 5.1 主键与唯一约束

- 所有核心表使用 `BIGINT` 代理主键，便于大规模数据生成和引用。
- `users.username`、`users.email` 唯一，保证账户身份唯一。
- `genealogy_collaborators(genealogy_id, user_id)` 唯一，避免同一用户在同一族谱中重复授权。
- `genealogy_collaborators.source_invitation_id` 唯一，保证一条邀请最多激活一个协作关系。
- `parent_child_relations(genealogy_id, parent_member_id, child_member_id, parent_role)` 唯一，避免重复亲子边。
- `marriages(genealogy_id, member_a_id, member_b_id)` 在有效婚姻状态下唯一，避免重复婚姻边。

### 5.2 外键与组合外键

普通外键用于保证实体存在性，例如成员必须属于某个族谱，族谱必须有创建者。更关键的是，设计中使用了 `members(genealogy_id, member_id)` 的组合唯一键，并让事件、亲子关系和婚姻关系通过组合外键引用它：

- `member_events(genealogy_id, member_id)`
- `parent_child_relations(genealogy_id, parent_member_id)`
- `parent_child_relations(genealogy_id, child_member_id)`
- `marriages(genealogy_id, member_a_id)`
- `marriages(genealogy_id, member_b_id)`

这能在数据库层阻止跨族谱成员被错误连接，是多族谱系统里非常重要的完整性设计。

### 5.3 CHECK 约束

当前 CHECK 约束覆盖以下关键规则：

- 出生年份、死亡年份在合理范围内。
- 死亡年份不能早于出生年份。
- `is_living = true` 时不能填写死亡年份。
- 性别限制为 `male`、`female`、`unknown`。
- 亲子关系中的父母和子女不能是同一个成员。
- 婚姻关系两端不能是同一个成员。
- 婚姻关系强制 `member_a_id < member_b_id`，用规范顺序避免 A-B 与 B-A 重复。
- 邀请状态、协作者角色、成员事件类型、婚姻状态限制在固定枚举中。

### 5.4 触发器约束

触发器补充了单行 CHECK 难以表达的跨行、跨表规则：

- 父亲必须对应男性成员，母亲必须对应女性成员。
- 父母出生年份必须早于子女出生年份。
- 新增或更新亲子关系时不能造成祖先环。
- 发起邀请者必须是族谱创建者或具备编辑权限的协作者。
- 协作者关系必须来源于同一族谱中一条已接受的邀请。
- 同一成员不能同时拥有多条 `married` 状态的有效婚姻。

这些约束能显著降低后续开发阶段由表单、批量导入或脚本误写造成的数据污染风险。

## 6. 索引设计说明

当前索引设计能够覆盖课程明确要求的两个场景：姓名模糊查询、根据父节点 ID 查询子节点。同时，它也支撑了应用中的祖先查询、配偶查询、Dashboard 统计和性能对比实验。

| 索引 | 支撑场景 | 审核评价 |
| --- | --- | --- |
| `members(genealogy_id, full_name)` | 同族谱内姓名排序、精确查找、前缀检索 | 符合成员列表和普通搜索需求 |
| `GIN(full_name gin_trgm_ops)` | 姓名模糊查询 | 满足课程要求的“按人名模糊查找”，适合 PostgreSQL |
| `members(genealogy_id, gender)` | Dashboard 男女比例统计 | 有利于单族谱聚合筛选 |
| `parent_child_relations(genealogy_id, parent_member_id)` | 父节点查子节点、后代树、四代查询 | 直接覆盖课程索引要求和性能对比要求 |
| `parent_child_relations(genealogy_id, child_member_id)` | 子女追溯父母、祖先递归 CTE | 支撑人物祖先查询 |
| `marriages(genealogy_id, member_a_id)` | 从成员 A 查询婚姻 | 支撑配偶查询 |
| `marriages(genealogy_id, member_b_id)` | 从成员 B 查询婚姻 | 支撑配偶查询 |
| `member_events(genealogy_id, member_id, event_type, event_year)` | 成员事件时间线、事件筛选 | 支撑档案详情页和后续扩展 |
| `genealogy_collaborators(user_id)` | 查询用户参与的族谱 | 支撑“我的族谱”和权限过滤 |
| `genealogy_invitations(invitee_user_id, status)` | 查询待处理邀请 | 支撑协作邀请功能 |

对于课程要求的“有索引/无索引性能对比”，项目中已经有 `benchmark_parent_lookup` 相关命令逻辑，会围绕父节点查子节点索引执行四代后代查询的 `EXPLAIN ANALYZE` 对比。这个设计与课程要求匹配。

需要注意的是，PostgreSQL trigram 模糊索引依赖 `pg_trgm` 扩展。项目已经在 SQL 和 Django migration 中处理该扩展，因此在 PostgreSQL 环境下可以正常使用。

## 7. 对课程要求的覆盖情况

| 课程要求 | 当前设计覆盖方式 | 结论 |
| --- | --- | --- |
| ER 图 | `docs/er-diagram.mmd` 描述 8 个核心实体和联系基数 | 已满足 |
| 关系模型 | `docs/database-design.md` 和 DDL 给出完整关系模式 | 已满足 |
| 3NF 分析 | 文档说明各表至少满足 3NF，主要表可按 BCNF 解释 | 已满足 |
| 主键、外键、CHECK 约束 | DDL、models、migrations 中均有实现 | 已满足 |
| 姓名模糊查询索引 | `members_full_name_trgm_idx` / `idx_members_full_name_trgm` | 已满足 |
| 父节点查子节点索引 | `pcr_parent_lookup_idx` / `idx_parent_child_relations_parent` | 已满足 |
| 祖先递归查询 | 基于 `parent_child_relations(genealogy_id, child_member_id)` 的 Recursive CTE | 已满足 |
| 两人亲缘路径查询 | 亲子边 + 婚姻边组成图路径 | 已满足 |
| Dashboard 统计 | `members` 聚合与性别索引支撑 | 已满足 |
| 大规模数据生成 | `generate_course_dataset` 支持 10 族谱、100000+ 成员、30 代链路 | 已满足 |
| COPY 导入导出 | `import_members_copy`、`export_branch_copy` 命令支撑 | 已满足 |
| 四代查询性能对比 | `benchmark_parent_lookup` 生成有/无索引 `EXPLAIN ANALYZE` 报告 | 已满足 |

## 8. 后续开发建议

当前数据库模型可以作为后续开发的稳定基础。建议后续实现继续遵守以下原则：

- 所有成员定位、关系维护、查询入口均使用 `member_id`，不要使用姓名作为唯一条件。
- 新增关系数据时继续保持同族谱约束，避免跨谱连边。
- 不新增派生亲属关系表，优先用递归 CTE 或应用层图搜索推导。
- 如果要扩展地点、史料来源、扫描件、媒体文件，再作为二期实体新增，不混入当前核心表。
- 大规模导入、数据生成、性能测试优先通过已有命令完成，便于复现实验材料。
- 实验报告可直接引用本文件中的表设计说明、ER 图说明、关系模式说明、约束说明和索引说明。

## 9. 总结

本项目当前数据库设计是合格且可继续开发的。它在概念设计上保持了清晰的实体边界，在逻辑设计上满足至少 `3NF`，在物理设计上针对课程要求的关键查询建立了有效索引，并通过组合外键与触发器补足了复杂业务一致性约束。

因此，下一步开发可以继续围绕现有模型推进界面完善、课程 SQL 展示、实验报告截图、执行计划分析和演示材料整理，而不需要先重构数据库结构。
