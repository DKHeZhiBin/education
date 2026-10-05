# 本地 MySQL 与 Qdrant

项目使用隔离的本地服务目录，不依赖 Docker 或系统级包管理器。

## 已安装版本

- MySQL Community Server 8.4.11 LTS
- Qdrant 1.19.1

程序、数据、配置、日志和本地密钥均位于 `.local-services/`，该目录不会进入版本控制。

服务通过当前 macOS 用户的 LaunchAgent 持续运行，并在登录后自动启动。

## 管理命令

```bash
./scripts/local-services start
./scripts/local-services status
./scripts/local-services stop
./scripts/local-services restart
```

## 服务地址

- MySQL：`127.0.0.1:3306`
- Qdrant REST API：`http://127.0.0.1:6333`
- Qdrant Dashboard：`http://127.0.0.1:6333/dashboard`
- Qdrant gRPC：`127.0.0.1:6334`

项目 MySQL 账号和连接地址保存在本地 `.env`。MySQL root 密钥只保存在权限为 `600` 的 `.local-services/config/mysql-root-client.cnf`。

Qdrant 只监听本机回环地址，开发环境未配置 API Key。不要直接把 6333 或 6334 端口暴露到公网。
