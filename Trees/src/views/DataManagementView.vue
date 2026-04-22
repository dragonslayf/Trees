<script setup lang="ts">
import { ref, computed, onMounted, onActivated, nextTick } from 'vue'
import { useApiBase } from '@/composables/useApiBase'
import { fetchSessionInit } from '@/composables/sessionInit'
import { ensureDomTilesAndGalleryPath } from '@/lib/tilesGallery'

/** 与 BreederLayout 中 KeepAlive include 一致，切换路由时保留本地已选文件与会话状态 */
defineOptions({ name: 'DataManagementView' })

const { api, apiRootHint, toAbsoluteUrl } = useApiBase()

const domFile = ref<File | null>(null)
const chmFile = ref<File | null>(null)
const csvFile = ref<File | null>(null)

const domInputRef = ref<HTMLInputElement | null>(null)
const chmInputRef = ref<HTMLInputElement | null>(null)
const csvInputRef = ref<HTMLInputElement | null>(null)

const domDragOver = ref(false)
const chmDragOver = ref(false)
const csvDragOver = ref(false)

const loading = ref(false)
const uploading = ref(false)
const error = ref('')
const sessionError = ref('')
const apiStatus = ref<'unknown' | 'ok' | 'error'>('unknown')

/** 后端返回的 data_dir，形如 users/<32位hex> */
const userDataDir = ref<string | null>(null)
const sessionExpiresAt = ref<number | null>(null)
const slotsUsed = ref(0)
const slotsMax = ref(10)

const sessionHint = computed(() => {
  if (sessionError.value) return sessionError.value
  if (!userDataDir.value) return ''
  const exp = sessionExpiresAt.value
  if (exp == null) return `数据目录：${userDataDir.value}`
  const d = new Date(exp * 1000)
  return `数据目录：${userDataDir.value} · 会话至 ${d.toLocaleString()} 过期（Cookie 约 1 小时）`
})

async function checkHealth() {
  try {
    const r = await fetch(api('/health'), { credentials: 'include' })
    apiStatus.value = r.ok ? 'ok' : 'error'
    return r.ok
  } catch {
    apiStatus.value = 'error'
    return false
  }
}

function applySessionPayload(data: Record<string, unknown>) {
  if (data.data_dir) userDataDir.value = String(data.data_dir)
  sessionExpiresAt.value =
    typeof data.expires_at === 'number' ? data.expires_at : null
  slotsUsed.value = typeof data.slots_used === 'number' ? data.slots_used : 0
  slotsMax.value = typeof data.slots_max === 'number' ? data.slots_max : 10
}

/** 建立/恢复会话（不要在开头清空 userDataDir，避免闪烁与误伤已选目录） */
async function initSession() {
  sessionError.value = ''
  try {
    const out = await fetchSessionInit(api)
    if (!out.ok) {
      if (out.reason === 'full') userDataDir.value = null
      sessionError.value = out.detail
      return
    }
    applySessionPayload(out.data)
  } catch (e) {
    sessionError.value = e instanceof Error ? e.message : String(e)
  }
}

const syncPending = ref(false)
const PHENOTYPE_REFRESH_KEY = 'trees_phenotype_refresh_pending'

function buildUploadFormData(): FormData {
  const fd = new FormData()
  if (domFile.value) fd.append('dom', domFile.value)
  if (chmFile.value) fd.append('chm', chmFile.value)
  if (csvFile.value) fd.append('csv', csvFile.value)
  return fd
}

async function postUploadOnce(): Promise<void> {
  let r = await fetch(api('/api/user/upload'), {
    method: 'POST',
    credentials: 'include',
    body: buildUploadFormData(),
  })
  let up = (await r.json().catch(() => ({}))) as {
    detail?: string
    data_dir?: string
    saved?: string[]
    saved_keys?: string[]
  }

  if (r.status === 401) {
    await initSession()
    if (sessionError.value) throw new Error(sessionError.value)
    r = await fetch(api('/api/user/upload'), {
      method: 'POST',
      credentials: 'include',
      body: buildUploadFormData(),
    })
    up = (await r.json().catch(() => ({}))) as {
      detail?: string
      data_dir?: string
      saved?: string[]
      saved_keys?: string[]
    }
  }

  if (!r.ok) {
    throw new Error(typeof up.detail === 'string' ? up.detail : r.statusText)
  }
  if (up.data_dir) userDataDir.value = up.data_dir
  const keys = Array.isArray(up.saved_keys) ? up.saved_keys : []
  if (keys.length > 0) sessionStorage.setItem(PHENOTYPE_REFRESH_KEY, '1')
  if (keys.includes('dom') && userDataDir.value && domFile.value) {
    sessionStorage.setItem(
      'trees_tile_gallery_pending',
      JSON.stringify({
        data_dir: userDataDir.value,
        dom_filename: domFile.value.name,
      }),
    )
  }
}

/** 选择文件后自动：建会话 → 上传当前已选文件到 users/{id}/ */
async function syncSelectedFilesToServer() {
  if (!domFile.value && !chmFile.value && !csvFile.value) return
  if (uploading.value) {
    syncPending.value = true
    return
  }
  uploading.value = true
  error.value = ''
  try {
    const out = await fetchSessionInit(api)
    if (!out.ok) {
      if (out.reason === 'full') userDataDir.value = null
      sessionError.value = out.detail
      return
    }
    applySessionPayload(out.data)
    sessionError.value = ''

    await postUploadOnce()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    uploading.value = false
    if (syncPending.value) {
      syncPending.value = false
      void nextTick(() => syncSelectedFilesToServer())
    }
  }
}

function selectedDomFilename(): string | null {
  return domFile.value?.name ?? null
}

/** 若服务器上尚无切片则调用 split_tiff 切分，随后在新窗口打开切片画廊。 */
async function openTileThumbnails() {
  const domFilename = selectedDomFilename()
  if (!userDataDir.value && (domFile.value || chmFile.value || csvFile.value)) {
    await syncSelectedFilesToServer()
  }
  if (!userDataDir.value) {
    error.value = '请先选择 DOM 等文件并等待自动同步完成（或检查会话是否已满/过期）'
    return
  }
  if (!domFilename) {
    error.value = '请先选择 DOM 影像'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const { tilesGalleryPath } = await ensureDomTilesAndGalleryPath(api, {
      data_dir: userDataDir.value,
      dom_filename: domFilename,
    })
    window.open(toAbsoluteUrl(tilesGalleryPath), '_blank', 'noopener,noreferrer')
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

function openDomPicker() {
  domInputRef.value?.click()
}
function openChmPicker() {
  chmInputRef.value?.click()
}
function openCsvPicker() {
  csvInputRef.value?.click()
}

function setDomFile(file: File | null) {
  domFile.value = file
}
function setChmFile(file: File | null) {
  chmFile.value = file
}
function setCsvFile(file: File | null) {
  csvFile.value = file
}

function onDomInputChange(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  setDomFile(f ?? null)
  input.value = ''
  void syncSelectedFilesToServer()
}
function onChmInputChange(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  setChmFile(f ?? null)
  input.value = ''
  void syncSelectedFilesToServer()
}
function onCsvInputChange(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  setCsvFile(f ?? null)
  input.value = ''
  void syncSelectedFilesToServer()
}

function allowTif(file: File) {
  const n = file.name.toLowerCase()
  return n.endsWith('.tif') || n.endsWith('.tiff')
}
function allowCsv(file: File) {
  return file.name.toLowerCase().endsWith('.csv')
}

function onDomDrop(e: DragEvent) {
  domDragOver.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f && allowTif(f)) {
    setDomFile(f)
    void syncSelectedFilesToServer()
  }
}

function onChmDrop(e: DragEvent) {
  chmDragOver.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f && allowTif(f)) {
    setChmFile(f)
    void syncSelectedFilesToServer()
  }
}

function onCsvDrop(e: DragEvent) {
  csvDragOver.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f && allowCsv(f)) {
    setCsvFile(f)
    void syncSelectedFilesToServer()
  }
}

onMounted(async () => {
  await checkHealth()
  if (apiStatus.value === 'ok') await initSession()
})

/** 从其他页返回时同步会话信息（Cookie 仍有效则刷新 data_dir / 过期时间展示） */
onActivated(async () => {
  if (apiStatus.value === 'ok') await initSession()
})
</script>

<template>
  <div class="page">
    <h1 class="page-title">📁 数据管理</h1>

    <p v-if="sessionHint" class="session-line">{{ sessionHint }}</p>
    <p v-if="!sessionError && userDataDir" class="slots-line">
      当前活跃会话：{{ slotsUsed }} / {{ slotsMax }}
    </p>

    <section class="group">
      <h2>DOM影像</h2>
      <input
        ref="domInputRef"
        type="file"
        class="file-input-hidden"
        accept=".tif,.tiff"
        @change="onDomInputChange"
      />
      <div
        class="drop-zone"
        :class="{ 'drop-zone-active': domDragOver, 'drop-zone-filled': domFile }"
        @click="openDomPicker()"
        @dragover.prevent="domDragOver = true"
        @dragleave="domDragOver = false"
        @drop.prevent="onDomDrop"
      >
        <template v-if="domFile">
          <span class="drop-zone-file">{{ domFile.name }}</span>
        </template>
        <template v-else>
          <span class="drop-zone-hint">拖拽上传</span>
          <span class="drop-zone-sub">或点击选择 .tif</span>
        </template>
      </div>
    </section>

    <section class="group">
      <h2>CHM影像</h2>
      <input
        ref="chmInputRef"
        type="file"
        class="file-input-hidden"
        accept=".tif,.tiff"
        @change="onChmInputChange"
      />
      <div
        class="drop-zone"
        :class="{ 'drop-zone-active': chmDragOver, 'drop-zone-filled': chmFile }"
        @click="openChmPicker()"
        @dragover.prevent="chmDragOver = true"
        @dragleave="chmDragOver = false"
        @drop.prevent="onChmDrop"
      >
        <template v-if="chmFile">
          <span class="drop-zone-file">{{ chmFile.name }}</span>
        </template>
        <template v-else>
          <span class="drop-zone-hint">拖拽上传</span>
          <span class="drop-zone-sub">或点击选择 .tif</span>
        </template>
      </div>
    </section>

    <section class="group">
      <h2>经纬度CSV</h2>
      <input
        ref="csvInputRef"
        type="file"
        class="file-input-hidden"
        accept=".csv"
        @change="onCsvInputChange"
      />
      <div
        class="drop-zone"
        :class="{ 'drop-zone-active': csvDragOver, 'drop-zone-filled': csvFile }"
        @click="openCsvPicker()"
        @dragover.prevent="csvDragOver = true"
        @dragleave="csvDragOver = false"
        @drop.prevent="onCsvDrop"
      >
        <template v-if="csvFile">
          <span class="drop-zone-file">{{ csvFile.name }}</span>
        </template>
        <template v-else>
          <span class="drop-zone-hint">拖拽上传</span>
          <span class="drop-zone-sub">或点击选择 .csv</span>
        </template>
      </div>
    </section>

    <p v-if="uploading" class="upload-hint">正在同步到服务器…</p>

    <section class="group actions-row">
      <button
        type="button"
        class="btn btn-primary"
        :disabled="loading || apiStatus !== 'ok' || !!sessionError || !userDataDir"
        @click="openTileThumbnails"
      >
        {{ loading ? '准备中…' : '查看 DOM 切片缩略图' }}
      </button>
      <p v-if="error" class="error">{{ error }}</p>
    </section>

    <p v-if="apiStatus !== 'ok'" class="api-warn">
      API 未就绪（{{ apiRootHint }}）。开发环境请将 <code class="code-inline">VITE_API_BASE_URL</code> 留空以走 Vite 代理，避免会话 Cookie 丢失。
    </p>
  </div>
</template>

<style scoped>
.page-title {
  font-size: 1.25rem;
  font-weight: bold;
  margin-bottom: 1rem;
}

.session-line {
  font-size: 0.88rem;
  color: #9ccc9c;
  margin: 0 0 0.35rem 0;
  line-height: 1.4;
  word-break: break-all;
}

.slots-line {
  font-size: 0.82rem;
  color: #888;
  margin: 0 0 1rem 0;
}

.upload-hint {
  font-size: 0.88rem;
  color: #ffb74d;
  margin: 0 0 0.75rem 0;
}

.code-inline {
  font-size: 0.85em;
  color: #9ccc9c;
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

.file-input-hidden {
  position: absolute;
  width: 0;
  height: 0;
  opacity: 0;
  overflow: hidden;
  pointer-events: none;
}

.drop-zone {
  min-height: 88px;
  border: 2px dashed #555;
  border-radius: 8px;
  background: #2b2b2b;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.25rem;
  cursor: pointer;
  transition:
    border-color 0.15s,
    background 0.15s;
}

.drop-zone:hover {
  border-color: #666;
  background: #333;
}

.drop-zone-active {
  border-color: #4a5b7c;
  background: #363d4a;
}

.drop-zone-filled {
  border-style: solid;
  border-color: #555;
}

.drop-zone-hint {
  font-size: 0.95rem;
  color: #ccc;
}

.drop-zone-sub {
  font-size: 0.85rem;
  color: #888;
}

.drop-zone-file {
  font-size: 0.9rem;
  color: #c8e6c9;
  word-break: break-all;
  text-align: center;
  padding: 0 0.5rem;
}

.actions-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.btn {
  padding: 8px 15px;
  color: #fff;
  border: none;
  border-radius: 4px;
  font-weight: bold;
  cursor: pointer;
}

.btn:hover:not(:disabled) {
  filter: brightness(1.08);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: #4a5b7c;
}

.btn-primary {
  background: #2d5a3d;
}

.error {
  color: #f44336;
  font-size: 0.9rem;
}

.api-warn {
  font-size: 0.85rem;
  color: #ffb74d;
  margin-top: 0.5rem;
}
</style>
