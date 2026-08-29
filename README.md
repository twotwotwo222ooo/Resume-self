# 多租户简历审查 Agent

当前版本：**V1.1**

上传 PDF 简历，系统走一条 LangGraph 链路生成审查报告：六维评分、整体评价。数据按企业隔离，后续可在 Agent 注册表中扩展新智能体。

## 技术栈

Python asyncio、FastAPI、Pydantic、LangChain、LangGraph、SQLAlchemy（AsyncSession）、PostgreSQL、DeepSeek。

## 本地运行

1. 先启动 Docker Desktop，再启动数据库：

```bash
docker compose up -d
```

2. 复制环境变量并填写 DeepSeek Key：

```bash
copy .env.example .env
```

3. 安装依赖并启动：

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

4. 浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)

首次启动会按 `.env` 中的 `PLATFORM_ADMIN_EMAIL` / `PLATFORM_ADMIN_PASSWORD` 创建平台管理员。

## 使用顺序

1. 用平台管理员登录。
2. 在「企业」页预置企业，系统会生成首位企业管理员邀请码。
3. 退出后用邀请码注册企业管理员。
4. 企业管理员可邀请成员；成员/管理员上传 PDF 进行审查。

## 说明

- 仅支持文本型 PDF；扫描件不做 OCR。
- 文件上限 8MB。
- 平台管理员不能查看各企业简历原文与报告。
- 无目标岗位时按通用软件研发岗评估。
