# RAG 文档摄取流程

## 1. 目标

这条流水线把已经完成权利核验的本地知识文档转换为可审核、可追踪、可重复生成的 `KnowledgeDocument` 和 `DocumentChunk`。摄取完成只表示内容已经解析，不能直接进入生产检索。

流程固定为：

```text
摄取清单
  → 原文件哈希校验
  → 文档解析
  → 文本清洗
  → 公式规范化
  → 结构化切片
  → 内容哈希与去重
  → 版本冲突检查
  → MySQL 事务写入
  → 内容审核与后续索引
```

核心实现位于 `app/ingestion/`，命令入口为 `math-tutor-ingest`。

## 2. 输入清单

每个文档必须有 JSON 清单。原文件只允许 UTF-8，单文件上限 20 MiB。首版支持：

- `text/plain`；
- `text/markdown`；
- `text/html`。

清单中的 `source_sha256` 必须在文件固定后计算，例如 macOS 可使用 `shasum -a 256 <文件路径>`。后续任何字节变化都要求重新核验来源并更新清单。

PDF、扫描件、Word、EPUB、图片和远程 URL 不做隐式解析。它们需要先经过独立、可审计的提取步骤，生成 UTF-8 中间文件及新的 SHA-256，再进入本流程。

示例：

```json
{
  "schema_version": "1.0",
  "input_path": "../documents/algebra-section-7-2.html",
  "source_sha256": "替换为原文件的64位小写SHA-256",
  "source_fingerprint": "替换为source_references.fingerprint",
  "document_key": "orcca-ed2-section-7-2",
  "title": "Algebra Section 7.2",
  "version_label": "edition-2-snapshot-2026-10-03",
  "document_type": "chapter",
  "media_type": "text/html",
  "language": "en",
  "subject": "math",
  "grade_band": "middle",
  "grade_codes": ["grade_9"],
  "curriculum_version_id": "替换为curriculum_versions.id",
  "knowledge_point_codes": ["MS.QE"],
  "problem_types": ["quadratic_equation"],
  "difficulty_factors": [
    {
      "factor_type": "method_selection",
      "level": 3,
      "rationale": "需要根据方程结构选择解法",
      "related_knowledge_codes": ["MS.QE"]
    }
  ],
  "content_types": ["problem_statement"],
  "chunking": {
    "target_tokens": 420,
    "max_tokens": 560,
    "overlap_tokens": 60
  }
}
```

来源必须通过 `source_reference_id`、`source_fingerprint` 或 `source_external_id` 中的一个精确定位。推荐使用 fingerprint；若 external ID 对应多条来源，导入会拒绝。`document_key` 是同一逻辑文档跨版本不变的机器标识，例如教材章节可以使用 `orcca-ed2-section-7-2`。

## 3. 解析和清洗

解析器输出带标题路径、原始位置和内容类型的块：

- Markdown 使用标题层级和行号；
- HTML 忽略脚本、样式、导航和页脚，保留标题、段落、列表、表格单元及预格式文本；
- 纯文本按空行划分段落。

清洗规则保持语义保守：使用 Unicode NFC、统一换行、删除零宽字符和控制字符、收敛多余空白。不会自动改写句意、翻译内容、推断缺失公式或执行 HTML 中的脚本。

## 4. 公式规范化

首版识别 `$...$`、`$$...$$`、`\\(...\\)` 和 `\\[...\\]`。规范化只执行可逆性较高的操作：

- 去除 `\\left`、`\\right`；
- 将 `\\dfrac`、`\\tfrac` 统一为 `\\frac`；
- 统一减号与公式内部空白；
- 将分隔符统一为行内 `$...$` 或块级 `$$...$$`。

公式原文、规范形式和所在块序号都会在准备结果中保留；写入时，每个切片 metadata 保存其规范公式及对应原始写法。无法可靠识别的 Unicode 裸公式保留原文，不猜测其数学结构。

## 5. 切片

切片优先保持标题层级，同一标题下按目标 token 数合并段落。超长段落先按中英文句号等边界拆分，再按原字符位置硬切。公式被视为原子内容，不会为了满足上限从公式内部截断；极端超长的单个公式因此可能超过 `max_tokens`。

重叠文本取自上一片段的原始尾部，不重新拼写公式。每个切片保存：

- 稳定顺序；
- 清洗后正文和 SHA-256；
- token 估算值；
- 标题路径与定位；
- 教材版本、学段、精确年级、内容类型、题型、知识点、难度来源和公式列表。

## 6. 哈希与去重

系统保留三层哈希：

1. `source_sha256`：原始文件字节哈希，用来确认抓取快照没有变化；
2. `content_checksum`：清洗后的块结构、标题路径、内容类型和正文哈希；
3. `content_hash`：最终切片正文哈希。

去重规则：

- 同一文档内规范正文相同的切片只保留一次；
- 同一来源、同一逻辑文档、同一版本和同一内容返回 `duplicate_version`；
- 同一来源、同一逻辑文档的不同版本若规范内容完全相同，仍登记新版并返回 `created_duplicate_content`，同时记录旧文档 ID，供后续索引复用向量；
- 不同文档的相同切片继续保留，以维持各自引用，但在 metadata 中记录 `duplicate_of_chunk_id`；
- 评估集文档必须在进入该流程前隔离，不能用普通清单导入。

## 7. 版本管理

`source_reference_id + document_key + version_label` 在数据库中唯一。同一逻辑文档的版本标签一旦对应某个内容哈希，不能再指向其他内容；发生变化时必须使用新的版本标签。一本教材的不同章节使用不同 `document_key`，可以共享相同的教材版本标签。

新版本 metadata 记录：

- 流水线、解析器、清洗和公式规则版本；
- 摄取实现文件合并计算得到的 `pipeline_fingerprint`；
- 清单规范 JSON 计算得到的 `manifest_fingerprint`；
- 原文件与规范内容哈希；
- 切片参数和统计；
- `supersedes_document_id` 与前一版本标签。

新版本写入后保持 `review_status=unreviewed`、`lifecycle_status=draft`、`ingestion_status=parsed`。系统不会自动停用旧版本，也不会自动批准或索引新版本。审核通过并完成索引后，管理流程再将旧版本设为 `superseded`。

## 8. 运行方式

只执行确定性准备流程，不连接 MySQL：

```bash
math-tutor-ingest --manifest path/to/manifest.json --validate-only
```

事务写入 MySQL：

```bash
alembic upgrade head
math-tutor-ingest --manifest path/to/manifest.json
```

离线输出包括解析器版本、原文件哈希、规范内容哈希、块数、切片数、公式数和删除的重复切片数。任何校验、解析、版本或数据库错误都会使整个导入失败，不会留下半批切片。
