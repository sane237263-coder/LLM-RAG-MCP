# 开放平台 API 接口规范 v2.3
> 文档编号：TECH-API-2026 | 版本：v2.3 | 更新：2026年5月20日 | 负责人：彭一鸣(产品)+郑雅文(研发) | 审核：陈志远 | 保密级别：对外(ISV合作伙伴)

## 一、概述
文件网盘开放平台API面向ISV和企业开发者，提供文件管理、用户管理、权限控制等标准化接口。v2.3版本向下兼容v2.0+。

基础信息：API URL https://openapi.filetech.com/v2 | 协议HTTPS | 格式JSON | 编码UTF-8 | 认证OAuth2.0+API Key+HMAC-SHA256签名 | 限流每Key 1000次/分钟 | Token有效期7200秒

## 二、核心接口
- POST /files/upload — 文件上传(单文件50GB，超100MB建议分块)
- POST /files/multipart/init|upload|complete — 分块上传三步走+断点续传(v2.2新增)
- GET /files/list — 文件列表(分页排序)
- POST /files/search — 文件搜索(关键词+语义检索，v2.3新增自然语言支持)
- DELETE /files/{file_id} — 软删除(回收站30天)/永久删除(permanent=true)

## 三、错误码
0:成功 | 1001:参数错误 | 1002:认证失败 | 1003:权限不足 | 1004:资源不存在 | 1005:超出配额 | 1006:频率限制 | 2001:文件大小超限 | 2002:文件类型不合法 | 5000:服务器内部错误

## 四、变更记录
v2.3(2026-05):新增AI智能分类接口+文件搜索支持语义检索 | v2.2(2026-02):分块上传恢复(断点续传) | v2.1(2025-11):OAuth2.0设备授权流程 | v2.0(2025-06):重构HMAC-SHA256签名

接入咨询：openapi@filetech.com