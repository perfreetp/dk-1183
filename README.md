# 公共 API 开放平台

基于 FastAPI 构建的公共 API 后端服务，面向合作伙伴开放订单、客户、商品和售后等基础能力。

## 功能特性

### 服务端能力
- **应用登记** - 合作方注册应用，获取 app_code 和 app_secret
- **接口目录** - 提供标准化的 API 接口目录，支持按类别查询
- **调用凭证** - 支持 Token 和签名两种认证方式
- **参数校验** - 统一的请求参数验证机制
- **额度控制** - 每日调用配额和接口级别限流
- **调用日志** - 完整的 API 调用记录
- **错误说明** - 标准化的错误码和解决方案
- **回调通知** - 异步事件推送能力

### 合作方能力
- 查询可用接口列表
- 申请访问权限
- 获取测试数据
- 按订单号/客户号拉取信息
- 提交状态变更
- 接收处理结果回调

### 管理端能力
- 停用/激活应用
- 调整每日额度
- 查看失败原因
- 重放回调
- 发布接口变更公告
- 按合作方统计调用量、成功率、高频错误

## 技术栈

- **框架**: FastAPI
- **数据库**: MySQL (SQLAlchemy ORM)
- **缓存**: Redis
- **认证**: JWT (access_token/refresh_token)
- **定时任务**: APScheduler

## 项目结构

```
├── config/
│   └── database.py          # 数据库配置
├── models/
│   └── database.py          # 数据库模型
├── schemas/
│   └── schemas.py           # Pydantic 模型
├── services/
│   ├── auth_service.py      # 认证授权服务
│   ├── rate_limit_service.py # 限流和日志服务
│   ├── callback_service.py  # 回调服务
│   ├── error_service.py     # 错误处理服务
│   └── callback_scheduler.py # 回调调度器
├── routers/
│   ├── partner_router.py    # 合作方自助服务
│   ├── business_router.py   # 业务接口
│   └── admin_router.py      # 管理端接口
├── main.py                  # 应用入口
└── requirements.txt        # 依赖
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
export DATABASE_URL="mysql+pymysql://root:password@localhost:3306/api_platform"
export REDIS_URL="redis://localhost:6379/0"
```

### 3. 初始化数据库

```bash
python main.py
```

服务启动时自动创建数据库表和初始化 API 端点。

### 4. 启动服务

```bash
python main.py
```

服务将运行在 http://localhost:8000

## API 文档

启动服务后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 认证方式

### 1. Token 认证

```
POST /api/v1/auth/token
Content-Type: application/json

{
  "app_code": "YOUR_APP_CODE",
  "app_secret": "YOUR_APP_SECRET"
}
```

获取 access_token 后，在请求头中使用：

```
Authorization: Bearer <access_token>
```

### 2. 签名认证

```
GET /api/v1/business/order/query
X-App-Code: YOUR_APP_CODE
X-Signature: sha256签名
X-Timestamp: 1609459200
X-Nonce: random_string
```

签名算法：
```
signature = sha256(app_code + timestamp + nonce + app_secret)
```

## API 接口

### 认证授权

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/auth/app/register` | POST | 应用登记 |
| `/api/v1/auth/token` | POST | 获取访问令牌 |
| `/api/v1/auth/refresh` | POST | 刷新令牌 |

### 合作方自助服务

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/partner/apis` | GET | 查询可用接口 |
| `/api/v1/partner/apis/{api_code}` | GET | 获取接口详情 |
| `/api/v1/partner/access/request` | POST | 申请访问权限 |
| `/api/v1/partner/access/list` | GET | 查看我的权限 |
| `/api/v1/partner/quota` | GET | 查询剩余配额 |
| `/api/v1/partner/calls/logs` | GET | 查看调用日志 |

### 业务接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/business/order/query` | GET | 订单查询 |
| `/api/v1/business/customer/query` | GET | 客户查询 |
| `/api/v1/business/product/query` | GET | 商品查询 |
| `/api/v1/business/aftersale/create` | POST | 售后创建 |
| `/api/v1/business/aftersale/query` | GET | 售后查询 |
| `/api/v1/business/order/status/update` | POST | 订单状态更新 |

### 管理端接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/admin/applications` | GET | 应用列表 |
| `/api/v1/admin/applications/{id}/suspend` | POST | 停用应用 |
| `/api/v1/admin/applications/{id}/activate` | POST | 激活应用 |
| `/api/v1/admin/applications/{id}/quota` | PUT | 调整配额 |
| `/api/v1/admin/access-requests` | GET | 权限申请列表 |
| `/api/v1/admin/access-requests/{id}/approve` | POST | 审批权限 |
| `/api/v1/admin/logs/failed` | GET | 失败日志 |
| `/api/v1/admin/callbacks/failed` | GET | 失败回调 |
| `/api/v1/admin/callbacks/{id}/replay` | POST | 重放回调 |
| `/api/v1/admin/announcements` | POST | 发布公告 |
| `/api/v1/admin/statistics/overview` | GET | 统计概览 |
| `/api/v1/admin/statistics/by-partner` | GET | 按合作方统计 |

## 错误码

| 错误码 | 说明 |
|--------|------|
| AUTH_001 | 无效的凭证 |
| AUTH_002 | Token 过期 |
| AUTH_003 | 签名错误 |
| AUTH_004 | 应用已停用 |
| AUTH_005 | 应用未激活 |
| ACCESS_001 | 无访问权限 |
| ACCESS_002 | 权限未审批 |
| RATE_001 | 每日配额超限 |
| RATE_002 | 接口限流 |
| VALIDATION_001 | 参数校验失败 |
| RESOURCE_001 | 资源不存在 |
| SYSTEM_001 | 系统错误 |

## 回调机制

回调服务会自动重试失败的通知：

1. 首次发送失败后，5 分钟后重试
2. 每次重试间隔递增：5min, 10min, 15min
3. 最多重试 3 次
4. 超过最大重试次数标记为失败

## 定时任务

- **回调处理器**: 每 30 秒检查并处理待发送的回调
