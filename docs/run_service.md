# 常驻运行

## 后台启动

```bash
python -m water_ledger start --port 8787
```

访问：

```text
http://127.0.0.1:8787
```

## 查看状态

```bash
python -m water_ledger status
```

## 停止

```bash
python -m water_ledger stop
```

## 前台调试

```bash
python -m water_ledger serve --port 8787
```

后台服务的日志在：

```text
private/logs/server.log
```

进程号在：

```text
private/logs/server.pid
```

目前这是轻量常驻：不会自动开机启动。若需要开机启动，可以用 macOS LaunchAgent 包一层 `python -m water_ledger start`。
