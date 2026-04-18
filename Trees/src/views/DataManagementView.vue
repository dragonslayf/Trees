<script setup lang="ts">
import { ref, onMounted } from 'vue'

const API_BASE = 'http://127.0.0.1:7999'

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
const error = ref('')
const apiStatus = ref<'unknown' | 'ok' | 'error'>('unknown')

async function checkHealth() {
  try {
    console.log('checkHealth', API_BASE)
    const r = await fetch(`${API_BASE}/health`)
    apiStatus.value = r.ok ? 'ok' : 'error'
    return r.ok
  } catch {
    apiStatus.value = 'error'
    return false
  }
}

function selectedDomFilename(): string | null {
  return domFile.value?.name ?? null
}

/** 若服务器上尚无切片则调用 split_tiff 切分，随后在新窗口打开切片画廊。 */
async function openTileThumbnails() {
  const domFilename = selectedDomFilename()
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams()
    params.set('data_dir', "Trees/data")
    if (domFilename) params.set('dom_filename', domFilename)
    const ensureUrl =
      params.toString().length > 0
        ? `${API_BASE}/api/tiles/ensure?${params}`
        : `${API_BASE}/api/tiles/ensure`
    const r = await fetch(ensureUrl, { method: 'POST' })
    const data = await r.json().catch(() => ({}))
    if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : r.statusText)
    const galleryParams = new URLSearchParams()
    if (data.dom_filename) galleryParams.set('dom_filename', data.dom_filename)
    else if (domFilename) galleryParams.set('dom_filename', domFilename)
    if (data.data_dir) galleryParams.set('data_dir', data.data_dir)
    const galleryQs = galleryParams.toString()
    const galleryUrl =
      galleryQs.length > 0
        ? `${API_BASE}/api/tiles/gallery?${galleryQs}`
        : `${API_BASE}/api/tiles/gallery`
    window.open(galleryUrl, '_blank', 'noopener,noreferrer')
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
}
function onChmInputChange(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  setChmFile(f ?? null)
  input.value = ''
}
function onCsvInputChange(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  setCsvFile(f ?? null)
  input.value = ''
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
  if (f && allowTif(f)) setDomFile(f)
}

function onChmDrop(e: DragEvent) {
  chmDragOver.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f && allowTif(f)) setChmFile(f)
}

function onCsvDrop(e: DragEvent) {
  csvDragOver.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f && allowCsv(f)) setCsvFile(f)
}

onMounted(() => {
  checkHealth()
})
</script>

<template>
  <div class="page">
    <h1 class="page-title">📁 数据管理</h1>

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

    <section class="group actions-row">
      <button
        type="button"
        class="btn btn-primary"
        :disabled="loading || apiStatus !== 'ok'"
        @click="openTileThumbnails"
      >
        {{ loading ? '准备中…' : '查看 DOM 切片缩略图' }}
      </button>
      <p v-if="error" class="error">{{ error }}</p>
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
  transition: border-color 0.15s, background 0.15s;
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

.muted {
  color: #888;
  font-size: 0.9rem;
}

.error {
  color: #f44336;
  font-size: 0.9rem;
}

.preview-area {
  padding: 1.5rem;
  background: #2b2b2b;
  border: 1px dashed #555;
  border-radius: 6px;
  min-height: 120px;
}

.code-inline {
  font-size: 0.85em;
  color: #9ccc9c;
}
</style>
