# 题目图片上传与处理状态

最后更新：2026-10-10

## 目标

学生可以在创建学习会话前上传题目图片，持续展示上传和处理状态。图片上传与 OCR 解耦：上传成功后立即返回 `pending`，后台任务再调用可替换的 OCR Provider。

## 接口

### 上传图片

```http
POST /v1/tutoring/problem-images
Authorization: Bearer <access-token>
Content-Type: multipart/form-data
```

表单字段：`file`。

约束：

- 只允许学生账号上传。
- 支持通过文件头确认的 JPEG、PNG、WebP。
- 默认最大 10 MB，由 `PROBLEM_IMAGE_MAX_BYTES` 配置。
- 不信任浏览器提供的扩展名和 MIME 类型。
- 文件名只作为展示元数据，不参与存储路径。

成功返回 HTTP 201：

```json
{
  "id": "uuid",
  "status": "pending",
  "original_filename": "question.png",
  "mime_type": "image/png",
  "size_bytes": 123456,
  "extracted_text": null,
  "error_code": null,
  "ocr_provider": null,
  "ocr_model": null,
  "ocr_confidence": null,
  "recognized_formulas": [],
  "created_at": "2026-10-10T12:00:00",
  "updated_at": "2026-10-10T12:00:00",
  "expires_at": "2026-10-17T12:00:00",
  "status_message": "图片已上传，正在等待 OCR 识别。你也可以先手动输入题目文字。"
}
```

### 查询状态

```http
GET /v1/tutoring/problem-images/{asset_id}
Authorization: Bearer <access-token>
```

学生只能读取自己的图片。不存在、已清理或不属于当前账号时统一返回 404，避免泄露资源是否存在。

## 状态机

| 状态 | 含义 | 前端行为 |
| --- | --- | --- |
| `pending` | 已上传，等待 OCR Provider | 显示“已上传 · 等待识别”，允许刷新或手动录入 |
| `processing` | OCR 正在处理 | 显示进行中状态，保留本地预览 |
| `ready` | OCR 成功且完成公式结构检查 | 展示正文、公式及问题，等待学生修正和确认 |
| `failed` | OCR 失败 | 显示可理解的失败状态，允许重新上传或手动录入 |

上传接口返回后，FastAPI 后台任务会将状态推进为 `processing`，调用 OCR Provider，并写入 `extracted_text`、`recognized_formulas`、置信度和模型来源。前端自动轮询状态，将成功结果放入可编辑文本框，学生确认后才开始辅导。

## OCR Provider

`app/providers/ocr.py` 定义统一接口：

- `recognize(OCRRequest) -> OCRResult`：输入受控图片字节、真实 MIME 和展示文件名；输出完整题目文本、LaTeX 公式列表、置信度、Provider 与模型名称。
- `check_readiness()`：供 `/health/ready` 展示 OCR 的独立就绪状态。
- `DisabledOCRProvider`：未配置视觉服务时安全降级，文字题流程继续工作。
- `OpenAICompatibleOCRProvider`：通过兼容 `/chat/completions` 的视觉模型识别正文与数学公式。

Provider 的系统提示明确禁止求解、补条件和猜测遮挡字符。公式使用 LaTeX，识别结果只是学生可修正的候选文本，不能直接作为标准答案或题库内容。

### Gemini 配置示例

```dotenv
OCR_PROVIDER=gemini
OCR_MODEL=gemini-3.8-flash
OCR_TIMEOUT_SECONDS=45
OCR_REQUIRED_FOR_READINESS=false
GEMINI_API_KEY=<server-side-secret>
```

`OCR_BASE_URL` 与 `OCR_API_KEY` 为空时，Gemini 适配器复用 `GEMINI_BASE_URL` 和 `GEMINI_API_KEY`。若接入其他兼容服务，使用 `OCR_PROVIDER=openai-compatible`，并显式配置 `OCR_BASE_URL`、`OCR_API_KEY`、`OCR_MODEL`。密钥只保存在服务端环境变量中。

### 失败行为

- Provider 未配置：`failed / ocr_not_configured`，原图和手工输入仍保留。
- 请求超时：`failed / ocr_timeout`。
- 上游 HTTP 错误：`failed / ocr_http_<status>`。
- 返回为空或结构无效：`failed / ocr_empty_result` 或 `ocr_invalid_response`。

供应商原始响应和密钥不会返回前端。OCR 不作为 API 整体就绪的强依赖，除非生产环境显式设置 `OCR_REQUIRED_FOR_READINESS=true`。

## 公式结构检查与学生确认

OCR 成功后，服务端用确定性规则检查：

- 正文中的 `$...$` 与 `$$...$$` 是否成对闭合；
- `()`、`[]`、LaTeX `{}` 是否按顺序闭合；
- `\left` 与 `\right` 是否配对；
- `\frac` 的分子、分母结构和 `\sqrt` 的被开方范围；
- 是否包含 `�`、`□`、`<?>` 等无法确认的 OCR 占位符；
- 重复公式和可疑的重复等号。

检查状态为：

- `valid`：结构检查通过，仍需学生对照原图确认语义；
- `needs_review`：存在警告，学生核对后可以确认；
- `invalid`：存在未闭合结构或未知符号，必须修正后才能确认；
- `not_checked`：尚未得到 OCR 结果。

学生在前端可以编辑完整题目，逐项修改、删除或补充 LaTeX 公式。确认接口为：

```http
PUT /v1/tutoring/problem-images/{asset_id}/confirmation
Content-Type: application/json

{
  "text": "修正后的完整题目",
  "formulas_latex": ["x^2-2x-3=0"]
}
```

服务端会重新检查修正内容。存在 `error` 时返回 `invalid_formula_structure`；检查通过或仅有警告时，保存修正内容和 `student_confirmed_at`。数据库同时保留 `ocr_original_text`，便于以后分析 OCR 误差，辅导流程只使用学生确认后的 `extracted_text`。

## 存储与数据对象

- 二进制文件保存在 `PROBLEM_IMAGE_STORAGE_DIR`，默认 `.local-uploads/problem-images/`。
- 文件按 `owner_user_id/asset_id.ext` 保存，不使用用户原始文件名作为路径。
- MySQL `media_assets` 保存归属、存储键、原文件名、真实 MIME、大小、SHA-256、原始 OCR 文本、学生修正文本、公式列表、结构检查结果、确认时间、OCR 来源、置信度、错误码和过期时间。
- 上传发生在建会话之前，因此 `session_id` 可以为空；创建图片题会话后再绑定会话。
- 默认原图保留 7 天，由 `PROBLEM_IMAGE_RETENTION_DAYS` 配置。
- API 不返回本地存储路径，也不提供未鉴权的公开图片 URL。

## 错误

图片接口沿用辅导 API 的 `code + message + retryable` 格式：

- `problem_image_too_large`：HTTP 413。
- `unsupported_problem_image`：HTTP 415。
- `problem_image_not_found`：HTTP 404。
- `problem_image_not_ready`：HTTP 409，识别尚未完成。
- `invalid_formula_structure`：HTTP 422，修正内容仍存在阻断性结构问题。
- 登录失效、角色错误和数据库不可用使用现有统一错误合约。

## 相关代码

- [图片题目领域对象](../../../app/domain/problem_image.py)
- [图片处理服务](../../../app/services/problem_images.py)
- [图片元数据 Repository](../../../app/repositories/problem_images.py)
- [OCR Provider](../../../app/providers/ocr.py)
- [图片存储 Provider](../../../app/providers/problem_image_storage.py)
- [学生端题目输入页](../../../../src/features/learning/StartLearningPage.tsx)
