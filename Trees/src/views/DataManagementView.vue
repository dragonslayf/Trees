<script setup lang="ts">
import { ref, onMounted } from 'vue'

// 后端 API 地址（可改为 .env 中 VITE_API_BASE_URL）
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

const remoteDataPath = ref('')
const dataDir = ref('')
const files = ref<string[]>([])
const thumbnailFilename = ref<string | null>(null)
const previewKey = ref(0)
const loading = ref(false)
const error = ref('')
const apiStatus = ref<'unknown' | 'ok' | 'error'>('unknown')

async function checkHealth() {
  try {
    const r = await fetch(`${API_BASE}/health`)
    apiStatus.value = r.ok ? 'ok' : 'error'
    return r.ok
  } catch {
    apiStatus.value = 'error'
    return false
  }
}

async function fetchList() {
  error.value = ''
  try {
    const r = await fetch(`${API_BASE}/api/data/list`)
    if (!r.ok) throw new Error(await r.text())
    const data = await r.json()
    dataDir.value = data.data_dir ?? ''
    files.value = data.files ?? []
    thumbnailFilename.value = files.value.includes('DOMZone48_thumb_800x800.tif')
      ? 'DOMZone48_thumb_800x800.tif'
      : null
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    files.value = []
    thumbnailFilename.value = null
  }
}

async function generateThumbnail() {
  loading.value = true
  error.value = ''
  try {
    const r = await fetch(`${API_BASE}/api/thumbnail/generate?thumb_size=800`, {
      method: 'POST',
    })
    const data = await r.json().catch(() => ({}))
    if (!r.ok) throw new Error(data.detail ?? r.statusText)
    thumbnailFilename.value = data.filename ?? 'DOMZone48_thumb_800x800.tif'
    previewKey.value = Date.now()
    await fetchList()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

function thumbnailPreviewUrl(): string {
  const t = thumbnailFilename.value ? `?t=${previewKey.value}` : ''
  return `${API_BASE}/api/thumbnail/preview.png${t}`
}

function thumbnailDownloadUrl(): string {
  const name = thumbnailFilename.value ?? 'DOMZone48_thumb_800x800.tif'
  return `${API_BASE}/api/thumbnail/file?filename=${encodeURIComponent(name)}`
}

onMounted(async () => {
  const ok = await checkHealth()
  if (ok) await fetchList()
})
</script>

<template>
  <div class="page">
    <h1 class="page-title">📁 数据管理</h1>

    <section class="group">
      <h2>后端连接</h2>
      <div class="form-row">
        <span class="status" :class="apiStatus">
          {{ apiStatus === 'ok' ? '已连接' : apiStatus === 'error' ? '未连接' : '检测中…' }}
        </span>
        <span class="api-url muted">{{ API_BASE }}</span>
        <button type="button" class="btn" @click="checkHealth">检测</button>
        <button type="button" class="btn" @click="fetchList">刷新列表</button>
      </div>
      <p v-if="dataDir" class="muted small">数据目录: {{ dataDir }}</p>
      <p v-if="error" class="error">{{ error }}</p>
    </section>

    <section class="group">
      <h2>数据导入</h2>
      <div class="form-row">
        <label>图像数据:</label>
        <input v-model="remoteDataPath" type="text" class="input" placeholder="选择遥感影像或点云数据..." />
        <button type="button" class="btn">浏览</button>
      </div>
    </section>

    <section class="group">
      <h2>数据文件列表</h2>
      <p v-if="apiStatus !== 'ok'" class="muted">请先启动 FastAPI 服务（uvicorn fastapi_example:app --port 8000）并刷新。</p>
      <ul v-else-if="files.length" class="file-list">
        <li v-for="f in files" :key="f">{{ f }}</li>
      </ul>
      <p v-else class="muted">暂无 .tif / .tfw / .ovr 等文件。</p>
      <div class="form-row actions">
        <button
          type="button"
          class="btn btn-primary"
          :disabled="loading || apiStatus !== 'ok'"
          @click="generateThumbnail"
        >
          {{ loading ? '生成中…' : '生成 DOM 缩略图 (800×800)' }}
        </button>
      </div>
    </section>

    <section class="group">
      <h2>数据预览</h2>
      <div class="preview-area">
        <template v-if="thumbnailFilename">
          <img
            :src="thumbnailPreviewUrl()"
            alt="DOM 缩略图"
            class="preview-img"
          />
          <p class="preview-actions">
            <a :href="thumbnailDownloadUrl()" target="_blank" rel="noopener" class="link">下载 TIFF 缩略图</a>
          </p>
        </template>
        <template v-else>
          <p>图像数据预览区域</p>
          <p class="muted">请先点击「生成 DOM 缩略图」或确保 20260114 目录下已有 DOMZone48.tif。</p>
        </template>
      </div>
    </section>
  </div>
</template>

<style scoped>
.page-title {
  font-size: 1.25rem;
  font-weight: bold;
  margin-bottom: 1rem;
}

.group {
  background: #3c3f41;
  border: 2px solid #555;
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 1rem;
}

.group h2 {
  font-size: 0.95rem;
  margin: -0.5rem 0 0.75rem 0;
  padding: 0 4px;
}

.form-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.form-row label {
  min-width: 80px;
}

.form-row.actions {
  margin-top: 0.5rem;
}

.input {
  flex: 1;
  min-width: 200px;
  padding: 8px 12px;
  background: #2b2b2b;
  border: 1px solid #555;
  border-radius: 4px;
  color: #fff;
}

.btn {
  padding: 8px 15px;
  background: #4a5b7c;
  color: #fff;
  border: none;
  border-radius: 4px;
  font-weight: bold;
  cursor: pointer;
}

.btn:hover:not(:disabled) {
  background: #5a6b8c;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background: #2d5a3d;
}

.btn-primary:hover:not(:disabled) {
  background: #3d6a4d;
}

.status {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.9rem;
}

.status.ok {
  background: #2d5a3d;
  color: #c8e6c9;
}

.status.error {
  background: #5a2d2d;
  color: #ffcdd2;
}

.api-url {
  font-size: 0.85rem;
}

.muted {
  color: #888;
  font-size: 0.9rem;
}

.small {
  font-size: 0.85rem;
}

.error {
  color: #f44336;
  margin-top: 0.5rem;
}

.file-list {
  list-style: none;
  padding: 0;
  margin: 0 0 0.5rem 0;
  max-height: 160px;
  overflow-y: auto;
  background: #2b2b2b;
  padding: 8px;
  border-radius: 4px;
}

.file-list li {
  padding: 2px 0;
  font-size: 0.9rem;
}

.preview-area {
  padding: 1.5rem;
  background: #2b2b2b;
  border: 1px dashed #555;
  border-radius: 6px;
  min-height: 120px;
}

.preview-img {
  max-width: 100%;
  max-height: 400px;
  display: block;
  border-radius: 4px;
}

.preview-actions {
  margin-top: 0.75rem;
}

.link {
  color: #64b5f6;
}

.link:hover {
  text-decoration: underline;
}
</style>
