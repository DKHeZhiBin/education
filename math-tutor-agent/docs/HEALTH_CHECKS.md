# 存活与就绪检查

## 1. 接口划分

服务提供两个用途不同的探针：

| 接口 | 外部依赖 | 用途 | 失败行为 |
| --- | --- | --- | --- |
| `GET /v1/health/live` | 不访问 | 判断 API 进程和事件循环是否仍在运行 | 进程可响应时固定返回 200 |
| `GET /v1/health/ready` | MySQL、Redis、LLM Provider、可选 RAG Provider | 判断实例是否具备接收新流量的条件 | 任一必需依赖失败时返回 503 |

RAG 默认关闭，并在就绪结果中显示 `disabled_by_configuration`。启用后由当前 `KnowledgeRetriever` 执行轻量检查；只有 `RAG_REQUIRED_FOR_READINESS=true` 时，RAG 故障才会使实例返回 503。
| `GET /v1/health` | 不访问 | 兼容原健康检查地址，等同于存活检查 | 进程可响应时固定返回 200 |

不能用就绪检查作为高频存活检查。依赖短暂抖动不应触发进程重启，只应让负载均衡器暂时停止向该实例分配新请求。

## 2. 依赖检查

### MySQL

MySQL 永远是必需依赖。检查通过应用共享 SQLAlchemy Engine 执行 `SELECT 1`，验证连接池可以取得有效连接并完成查询。失败或超时会使整个就绪检查返回 503。

### Redis

`REDIS_ENABLED=true` 时 Redis 是必需依赖，通过共享 Redis Client 执行 `PING`。失败或超时会使就绪检查返回 503，这与生产环境认证限流、会话锁和幂等读取的快速失败策略一致。

开发环境设置 `REDIS_ENABLED=false` 时，Redis 检查显示为 `disabled`，不影响整体就绪状态。

### LLM Provider

LLM Provider 不调用生成接口，不产生模型 token 或内容费用。配置 `LLM_BASE_URL` 和 `LLM_MODEL` 后，检查会请求：

```text
{LLM_BASE_URL}{LLM_READINESS_PATH}
```

默认路径为 `/models`。如果所用 OpenAI-compatible Provider 不支持该接口，可把 `LLM_READINESS_PATH` 配置为其轻量健康路径；设置为空字符串时只检查配置是否完整，不进行网络探测。

`LLM_REQUIRED_FOR_READINESS` 控制 LLM 是否阻止流量：

- `false`：LLM 未配置或暂时不可用时，服务仍然 ready；已配置但探测失败时返回 `degraded: true`，教学流程使用现有安全降级逻辑；
- `true`：LLM 未配置、连接失败、超时或返回非成功状态时，整个就绪检查返回 503。

### Qdrant RAG Provider

配置 `RAG_PROVIDER=qdrant` 后，RAG 探针同时检查 Embedding Provider 和 Qdrant 集合。配置 `RAG_PROVIDER=hybrid` 时还会检查 MySQL 连接。集合缺失、连接失败、命名向量不存在、维度不一致或距离不是 Cosine 都返回 `not_ready`。探针不执行向量写入，也不调用 Embedding 生成接口；Embedding 使用 `/models` 或配置的轻量路径检查。

## 3. 响应格式

所有必需依赖正常时返回 HTTP 200：

```json
{
  "status": "ready",
  "degraded": false,
  "checks": {
    "mysql": {"status": "ready", "required": true, "latency_ms": 4, "detail": "query_ok"},
    "redis": {"status": "ready", "required": true, "latency_ms": 1, "detail": "ping_ok"},
    "llm": {"status": "ready", "required": false, "latency_ms": 32, "detail": "reachable"}
  }
}
```

必需依赖失败时返回 HTTP 503，响应仍包含每个依赖的独立状态和耗时。响应不会包含数据库地址、Redis URL、API Key、原始异常或供应商响应正文。

## 4. 配置

```dotenv
LLM_READINESS_PATH=/models
LLM_REQUIRED_FOR_READINESS=false
READINESS_TIMEOUT_SECONDS=2
```

每项探测并行执行，单项最大等待时间由 `READINESS_TIMEOUT_SECONDS` 控制。MySQL 和 Redis 客户端自身还保留连接及命令超时配置。

高难题生产环境若没有可接受的无模型降级能力，应设置：

```dotenv
LLM_REQUIRED_FOR_READINESS=true
```

## 5. 部署探针示例

Kubernetes 可分别配置：

```yaml
livenessProbe:
  httpGet:
    path: /v1/health/live
    port: 8000
readinessProbe:
  httpGet:
    path: /v1/health/ready
    port: 8000
```

实际部署应增加合适的 `periodSeconds`、`timeoutSeconds` 和 `failureThreshold`，避免单次网络抖动频繁摘除实例。
