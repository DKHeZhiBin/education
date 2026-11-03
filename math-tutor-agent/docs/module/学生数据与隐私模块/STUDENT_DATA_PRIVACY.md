# 学生数据导出、删除与家长授权撤销

## 数据导出

学生登录后可以调用 `GET /v1/auth/me/data-export` 下载 JSON 文件。接口只允许 `student` 角色导出自己的数据，不接受外部传入的学生 ID。

导出内容包括：

- 账号公开资料与学生档案；
- 家长授权关系及状态；
- 学习会话、学生与 Agent 消息；
- 结构化学习记录、知识点证据及复习记录；
- 上传文件元数据和 OCR 结果；
- 学生提交的内容错误报告；
- 已持久化的家长报告。

导出明确排除密码哈希、Access Token、Refresh Token、操作 Token、Provider API Key 和内部 Agent artifacts。响应使用 `Content-Disposition: attachment` 下载，不把导出副本存入服务器。

## 学生账号删除

学生调用 `DELETE /v1/auth/me`，请求体必须同时包含当前密码和固定确认值 `DELETE_MY_ACCOUNT`。前端要求学生手工输入“删除我的账号”，再提交固定确认值。

执行顺序：

1. 校验当前账号为学生并重新验证密码；
2. 取得需要清除的会话和上传文件范围；
3. 依次取得全部学习会话锁；会话正忙时返回 `409`，不强行破坏正在执行的轮次；
4. 在持锁期间删除 Redis 会话缓存和该会话的幂等结果；Redis 清除失败时不进入数据库删除；
5. 删除该学生的本地上传目录及其中全部题目图片；
6. 删除 MySQL 中的学习会话、消息、Agent 运行数据、学习记录、复习记录、媒体元数据、家长授权和家长报告；
7. 内容错误报告保留问题处理记录，但移除报告者身份和已删除会话引用；
8. 删除学生档案，并将用户行匿名化为不可登录的 `deleted` 墓碑；
9. 清除当前浏览器 Refresh Cookie 和 Access Token。

用户行使用匿名墓碑而非直接物理删除，是为了兼容审计表中的限制型外键。墓碑不保留邮箱、姓名、密码、登录时间或已验证状态。

## 家长授权撤销

现有 `DELETE /v1/auth/guardian-links/{link_id}` 支持学生和关联家长任一方撤销。Repository 查询同时要求调用者是该关联中的学生或家长，不能撤销第三方关联。

撤销后关联状态变为 `revoked`，`guardian_can_access` 只承认 `active` 状态，因此家长立即失去学生会话、学习记录和报告读取权限。个人页在执行前显示关系对象并要求二次确认。

账号删除会物理删除该学生的全部家长关联，避免遗留授权记录。

## 相关代码

- [隐私领域对象](../../../app/domain/data_privacy.py)
- [隐私 Repository](../../../app/repositories/data_privacy.py)
- [认证应用服务](../../../app/services/auth.py)
- [身份与授权模型](../../../app/models/identity.py)
- [学生端个人资料页](../../../../src/features/profile/ProfilePage.tsx)
