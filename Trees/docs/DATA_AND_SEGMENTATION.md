# 数据目录、会话与单木分割流程

本文说明前端（`Trees/Trees`）与后端（`backend/fastapi_example.py`）如何配合：**Cookie 会话**、**用户数据目录 `data_dir`**、**数据管理上传**与**单木分割 / 可视化**请求。阅读代码时可对照 `src/composables/useApiBase.ts`、`sessionInit.ts`、`lib/ndjson.ts`、`lib/userWorkspace.ts` 与两个视图 `DataManagementView.vue`、`TreeSegmentationView.vue`。

## 开发环境与 API 基址

- 环境变量 **`VITE_API_BASE_URL`**：留空时，前端使用**相对路径**（如 `/api/...`），请求与页面**同源**，浏览器会带上 `Set-Cookie` 下发的会话 Cookie。
- **`vite.config.ts`** 将 `/api` 与 `/health` **代理**到 `VITE_PROXY_TARGET`（默认 `http://127.0.0.1:7000`）。因此开发时通常 **不要** 把 API 写成与页面不同的 host（例如页面是 `localhost`、API 是 `127.0.0.1`），否则 Cookie 可能被视为跨站而丢失。
- **`useApiBase()`** 统一提供 `api(path)`、`apiRootHint`（界面提示）、`toAbsoluteUrl(href)`（新窗口打开画廊等相对地址时拼完整 URL）。

## 会话与用户目录

1. **`POST /api/session/init`**  
   建立或恢复会话；响应体含 **`data_dir`**（该用户在服务器上的工作目录路径）。  
   前端通过 **`fetchSessionInit(api)`**（`sessionInit.ts`）解析：成功则得到 `data`；429 表示活跃会话达上限；其它错误为 `ok: false`。

2. **会话持久化与清理（`backend/user_session.py`）**  
   - 过期时间写入 **`data/.trees_sessions.json`**，**进程重启后仍会按时间删除** `users/<32hex>/`。  
   - 每次 **`/api/session/init`**、上传、列文件、**`GET /health`** 会执行 **`maintenance_cleanup()`**：删除已过期会话目录、会话数超过 10 时按最早过期优先裁撤、删除磁盘上不在表内的孤儿目录。  
   - 恢复会话时 **`refresh_session_expiry`** 将过期时间**滑动续期** 1 小时（与 Cookie `max_age` 一致）。  
   - 若首次启用持久化且 **`users/`** 下已有子目录但无 JSON：按目录 **mtime 只保留最新 10 个**并登记，其余目录立即删除。

3. **数据管理页**与**单木分割页**在挂载/激活时会调用会话初始化（数据管理用于同步状态；分割页 **`hydrateFromSession`** 会写入 `userDataDir` 并尝试从 **`GET /api/user/files`** 列表里自动选中第一个 `.tif`/`.tiff` 作为 DOM 文件名——逻辑在 **`pickDomFromFiles`**）。

## 数据管理（上传与列表）

- **`POST /api/user/upload`**：上传文件到当前会话对应的用户目录（需已建立会话，Cookie 随请求发送）。响应含 **`saved`**（文件名列表）、**`saved_keys`**（本次包含的字段：`dom` / `chm` / `csv`），便于前端判断是否为 DOM 上传。
- 服务端在 **`users/<id>/.upload_manifest.json`** 中记录最近一次各类型文件名。再次上传**不同类型的新文件**时：删除该类型上一份原始文件；**上传新 DOM** 时还会清空 **`segmentation_result`** 并删除遗留的 **`tile_result`** 目录（切分与分割派生结果），避免与旧 DOM 混用。
- **`GET /api/user/files`**：列出已上传文件（不含点文件），用于界面展示与分割页的默认 DOM 选择。

## 磁盘布局（`data_dir` 下）

- **`segmentation_result/`**：800×800 切片 TIFF、各块 **`_result.pkl`**、以及 **`marked_result/`**（树心可视化 PNG）。不再单独使用与 `segmentation_result` 平级的 **`tile_result/`**；若仍存在旧目录，上传新 DOM 时会删除，且 **`POST /api/tiles/ensure`** 在缺切片时会尝试把旧 `tile_result` 中同名切片**移动**到 `segmentation_result`。

## 上传后自动打开切片画廊

- 数据管理页在成功上传且 **`saved_keys` 含 `dom`** 时，向 **`sessionStorage`** 写入 `trees_tile_gallery_pending`。
- **单木分割页**在 **`onMounted` / `onActivated`** 中读取该标记（读后即删），调用 **`POST /api/tiles/ensure`** 并在新标签打开 **`/api/tiles/gallery`**，与手动点击「查看 DOM 切片缩略图」一致。逻辑封装在 **`src/lib/tilesGallery.ts`** 的 **`ensureDomTilesAndGalleryPath`**。

## 单木分割与 NDJSON 流

分割相关接口多返回 **`application/x-ndjson`**：每行一个 JSON 对象。前端用 **`forEachNdjsonObject`** 统一解析，避免在多个组件里重复 `ReadableStream` + 按行缓冲逻辑。

主要接口（与 UI 对应关系）：

| 用途 | 方法 | 说明 |
|------|------|------|
| 是否已有分割结果 | `GET /api/segment/has-existing` | 用于提示或跳过重复跑全流程 |
| 执行分割 | `POST /api/segment/run` | NDJSON：`progress` → `done`（可含 `processed`）/ `error` |
| 按阈值重算可视化 | `POST /api/segment/regenerate-vis` | NDJSON：`progress` → `done` / `error` |
| 可视化 PNG | `GET /api/segment/vis.png` | 查询参数含数据目录、DOM 名、阈值等 |
| 分割结果画廊页 | `GET /api/segment/gallery` | HTML；前端用 `toAbsoluteUrl` 打开新标签 |
| 原始瓦片画廊 | `GET /api/tiles/gallery` | 同上 |
| 瓦片预览 | `GET /api/tile/preview.png` | 小图预览 |
| 确保瓦片 | `POST /api/tiles/ensure` | 需要时触发生成 |

具体查询参数以后端 `fastapi_example.py` 中各路由为准。

## 路由缓存（KeepAlive）

**`BreederLayout.vue`** 对 **`TreeSegmentationView`** 与 **`DataManagementView`** 使用 `<KeepAlive>`，切换侧边栏路由时**不销毁**这两个页面实例，从而保留进行中的分割进度、已选文件与表单状态。两组件均使用 **`defineOptions({ name: '...' })`** 与 `include` 名称一致。

## 代码分层小结

- **`useApiBase`**：唯一入口构造请求 URL 与绝对链接。  
- **`fetchSessionInit`**：唯一入口解析 `session/init`。  
- **`forEachNdjsonObject`**：唯一入口消费 NDJSON 流。  
- **`pickDomFromFiles`**：从文件列表中选默认 DOM 文件名。  
- **`ensureDomTilesAndGalleryPath`**：ensure 切分并拼好 **`/api/tiles/gallery`** 查询串。

在此之上，视图文件只描述交互与业务步骤，避免重复实现上述机制。
