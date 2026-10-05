# 教育内容标签设计

## 1. 目标

标签用于检索过滤、题目推荐、难度解释、教材适配和准入检查。标签不是自由文本备注，而是内容对象的结构化字段和可追溯快照。

首版覆盖：

- 学段 `grade_band` 和精确年级 `grade_codes`；
- 知识点 `knowledge_point_codes`；
- 题型 `problem_type` / `problem_types`；
- 难度来源 `difficulty_factors`；
- 教材版本 `curriculum_version_id`；
- 内容类型 `content_type` / `content_types`。

`curriculum_version_id` 沿用现有 `CurriculumVersion` 对象。该对象既可以表示课程标准版本，也可以表示具有来源、出版方、区域和版本号的教材版本。

## 2. 三层标签

### KnowledgeDocument

文档保存整个来源范围的标签：学段、精确年级集合、知识点集合、题型集合、难度来源集合、教材版本和内容类型集合。这些标签描述文档允许被检索到的范围。

### DocumentChunk

切片保存独立标签快照：教材版本、学段、精确年级、知识点、题型、难度来源和内容类型。向量索引可以直接使用切片载荷过滤，不需要在检索时回查整份文档。

文档更新不会静默修改旧切片；新版本重新摄取并产生新的切片标签快照。

### KnowledgeProblem

题目保存教材版本、学段、精确年级、知识点、单一主题型、结构化难度来源和主内容类型。AI 变式题继承可信母题的教材版本和年级；修订题继承被修订题目的版本、年级与内容类型。

## 3. 难度来源

`difficulty_factors` 使用结构化对象，而不是简单字符串：

```json
{
  "factor_type": "method_selection",
  "level": 3,
  "rationale": "需要识别方程结构并选择合适方法",
  "related_knowledge_codes": ["MS.QE", "MS.QE.FACTORING"]
}
```

总难度仍使用 `difficulty=1..5` 做粗粒度排序，难度来源解释为什么难，并支持按认知障碍类型筛选。

## 4. 内容类型

标准内容类型包括文本、课程标准、教材、章节、课时、概念、定义、定理、公式、例题、练习、题目、题干、题集、解答、证明、提示、易错点和教学笔记。摄取解析器会为每个切片识别最具体的内容类型。

题目的默认内容类型为 `problem`，可信题库中的原始切片使用 `problem_statement`。

## 5. 摄取规则

摄取清单可以声明：

```json
{
  "grade_band": "middle",
  "grade_codes": ["grade_9"],
  "curriculum_version_id": "...",
  "knowledge_point_codes": ["MS.QE"],
  "problem_types": ["quadratic_equation"],
  "difficulty_factors": [],
  "content_types": ["problem_statement"]
}
```

Repository 会验证教材版本和知识点是否存在。文档级标签写入 `KnowledgeDocument`，并作为默认值复制到所有切片；解析器识别出的切片内容类型优先于文档默认类型。

## 6. 准入与查询

题目进入自动批准前必须具备：

- 非空学段；
- 至少一个精确年级标签；
- 非空知识点；
- 非空题型和内容类型；
- 至少一个结构化难度来源；
- 完整题意结构和求解目标。

教材版本保持可空，因为独立原创题、课程标准或合法题库内容不一定属于某一本教材。

题库管理查询支持 `grade_band`、`grade_code`、`problem_type`、`content_type`、`curriculum_version_id`、`knowledge_point_code` 和 `difficulty_source` 组合过滤。
