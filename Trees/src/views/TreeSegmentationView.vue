<script setup lang="ts">
import { ref, computed, onMounted, onActivated, watch } from 'vue'
import { useApiBase } from '@/composables/useApiBase'
import { fetchSessionInit } from '@/composables/sessionInit'
import { forEachNdjsonObject } from '@/lib/ndjson'
import { pickDomFromFiles } from '@/lib/userWorkspace'
import { ensureDomTilesAndGalleryPath } from '@/lib/tilesGallery'

/** 供布局中 KeepAlive include 匹配，切换路由时保留本页实例与进行中的分割/可视化任务 */
defineOptions({ name: 'TreeSegmentationView' })

const { api, apiRootHint, toAbsoluteUrl } = useApiBase()

const DEFAULT_DOM_FILENAME = 'DOMZone48.tif'

/** 仅使用 Mask R-CNN */
const model = ref('Mask R-CNN')
const models = ['Mask R-CNN'] as const

const confidence = ref(80)
/** 最小树冠面积（m²），与后端掩膜×像元面积一致；无地理坐标时像元面积按 1 等效为像素数 */
const minArea = ref(0)

/** Cookie 会话对应的数据目录（如 users/ 下 32 位 id），与数据管理上传位置一致 */
const userDataDir = ref<string | null>(null)

const domFilename = ref(DEFAULT_DOM_FILENAME)
const progress = ref(0)
const segmenting = ref(false)
const regeneratingVis = ref(false)
/** 可视化进度：n / total 张（仅 regenerate-vis 流式阶段） */
const visProgress = ref<{ n: number; total: number } | null>(null)
/** 分割进度：n / total 块（每块含推理 + 可视化，/api/segment/run流式阶段） */
const segmentProgress = ref<{ n: number; total: number } | null>(null)
const errorMsg = ref('')
const apiStatus = ref<'unknown' | 'ok' | 'error'>('unknown')

const scoreThr = computed(() => Math.min(0.99, Math.max(0.01, confidence.value / 100)))

/** 上次用于生成「分割结果」预览图的 DOM、score_thr、min树冠面积；未变化则跳过 regenerate-vis */
const lastResultVisDom = ref<string | null>(null)
const lastResultVisScoreThr = ref<number | null>(null)
const lastResultVisMinArea = ref<number | null>(null)

function scoresMatch(a: number, b: number): boolean {
  return Math.abs(a - b) < 1e-6
}

function minAreaMatch(a: number, b: number): boolean {
  return Math.abs(a - b) < 1e-9
}

watch(domFilename, () => {
  lastResultVisDom.value = null
  lastResultVisScoreThr.value = null
  lastResultVisMinArea.value = null
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

/** 读取 Cookie 会话与用户目录下已上传文件，自动填入 data_dir 与 DOM 文件名 */
async function hydrateFromSession() {
  try {
    const out = await fetchSessionInit(api)
    if (!out.ok) {
      userDataDir.value = null
      return
    }
    const data = out.data
    userDataDir.value = typeof data.data_dir === 'string' ? data.data_dir : null
    if (!userDataDir.value) return

    const fr = await fetch(api('/api/user/files'), { credentials: 'include' })
    if (!fr.ok) return
    const fj = (await fr.json().catch(() => ({}))) as { files?: string[] }
    const files = fj.files ?? []
    const pick = pickDomFromFiles(files)
    if (!pick) return
    const cur = domFilename.value.trim()
    if (!cur || cur === DEFAULT_DOM_FILENAME || !files.includes(cur)) {
      domFilename.value = pick
    }
  } catch {
    userDataDir.value = null
  }
}

const TILE_GALLERY_PENDING_KEY = 'trees_tile_gallery_pending'

/** 数据管理页上传 DOM 后写入 sessionStorage，进入本页时自动切分并打开切片画廊 */
async function tryOpenTilesAfterUploadIntent(): Promise<void> {
  const raw = sessionStorage.getItem(TILE_GALLERY_PENDING_KEY)
  if (!raw) return
  sessionStorage.removeItem(TILE_GALLERY_PENDING_KEY)
  let o: { data_dir?: string; dom_filename?: string }
  try {
    o = JSON.parse(raw) as { data_dir?: string; dom_filename?: string }
  } catch {
    return
  }
  const dd = o.data_dir?.trim()
  const dom = o.dom_filename?.trim()
  if (!dd || !dom) return
  await hydrateFromSession()
  if (userDataDir.value !== dd) return
  domFilename.value = dom
  try {
    const { tilesGalleryPath } = await ensureDomTilesAndGalleryPath(api, {
      data_dir: dd,
      dom_filename: dom,
    })
    window.open(toAbsoluteUrl(tilesGalleryPath), '_blank', 'noopener,noreferrer')
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  }
}

function galleryUrl(cacheBust?: number): string {
  const p = new URLSearchParams()
  if (domFilename.value.trim()) p.set('dom_filename', domFilename.value.trim())
  p.set('score_thr', String(scoreThr.value))
  p.set('min_canopy_area_m2', String(minArea.value))
  if (userDataDir.value) p.set('data_dir', userDataDir.value)
  if (cacheBust != null) p.set('t', String(cacheBust))
  const qs = p.toString()
  return qs.length > 0 ? api(`/api/segment/gallery?${qs}`) : api('/api/segment/gallery')
}

/** 原始数据区：查看 800×800 切片（与数据管理「DOM 切片缩略图」相同，不含树心标注） */
async function openSegmentedTileGallery() {
  errorMsg.value = ''
  const dom = domFilename.value.trim()
  if (!userDataDir.value) {
    errorMsg.value = '请先建立会话并在数据管理中上传 DOM'
    return
  }
  if (!dom) {
    errorMsg.value = '请填写 DOM 文件名'
    return
  }
  try {
    const { tilesGalleryPath } = await ensureDomTilesAndGalleryPath(api, {
      data_dir: userDataDir.value,
      dom_filename: dom,
    })
    window.open(toAbsoluteUrl(tilesGalleryPath), '_blank', 'noopener,noreferrer')
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  }
}

async function streamRegenerateVis(dom: string): Promise<void> {
  const payload: Record<string, unknown> = {
    dom_filename: dom,
    score_thr: scoreThr.value,
    min_canopy_area_m2: minArea.value,
  }
  if (userDataDir.value) payload.data_dir = userDataDir.value

  const r = await fetch(api('/api/segment/regenerate-vis'), {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/x-ndjson, application/json',
    },
    body: JSON.stringify(payload),
  })
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    const d = data.detail
    throw new Error(typeof d === 'string' ? d : r.statusText)
  }

  let sawDone = false
  await forEachNdjsonObject(r.body, (msg) => {
    if (msg.type === 'progress' && msg.total != null && msg.n != null) {
      visProgress.value = { n: msg.n as number, total: msg.total as number }
    } else if (msg.type === 'done') {
      sawDone = true
    } else if (msg.type === 'error') {
      throw new Error(typeof msg.detail === 'string' ? msg.detail : '可视化失败')
    }
  })
  if (!sawDone) throw new Error('可视化未完成：服务器提前结束响应')
}

/** 消费 /api/segment/run 的 NDJSON 流，更新 segmentProgress / progress，返回 processed */
async function consumeSegmentRunStream(r: Response): Promise<number> {
  let sawDone = false
  let processed = 0

  await forEachNdjsonObject(r.body, (msg) => {
    if (msg.type === 'progress' && msg.total != null && msg.n != null) {
      const n = msg.n as number
      const t = msg.total as number
      segmentProgress.value = { n, total: t }
      progress.value = t > 0 ? Math.min(100, Math.round((n / t) * 100)) : 0
    } else if (msg.type === 'done') {
      sawDone = true
      if (typeof msg.processed === 'number') processed = msg.processed
    } else if (msg.type === 'error') {
      throw new Error(typeof msg.detail === 'string' ? msg.detail : '分割失败')
    }
  })
  if (!sawDone) throw new Error('分割未完成：服务器提前结束响应')
  return processed
}

/** 分割结果区：仅在 score_thr 相对上次预览有变化时调用 visualize重绘，再打开画廊 */
async function openResultGallery() {
  errorMsg.value = ''
  if (apiStatus.value !== 'ok') return
  const dom = domFilename.value.trim()
  try {
    const hp = new URLSearchParams({ dom_filename: dom })
    if (userDataDir.value) hp.set('data_dir', userDataDir.value)
    const st = await fetch(api(`/api/segment/has-existing?${hp.toString()}`), {
      credentials: 'include',
    })
    const stJson = await st.json().catch(() => ({}))
    if (!st.ok) throw new Error(typeof stJson.detail === 'string' ? stJson.detail : st.statusText)

    if (!stJson.has_tiles) {
      errorMsg.value = '未找到 DOM 切片，请先在「数据管理」中完成切分。'
      return
    }

    if (stJson.has_any_pkl) {
      const skipRedraw =
        lastResultVisDom.value === dom &&
        lastResultVisScoreThr.value != null &&
        lastResultVisMinArea.value != null &&
        scoresMatch(lastResultVisScoreThr.value, scoreThr.value) &&
        minAreaMatch(lastResultVisMinArea.value, minArea.value)

      if (!skipRedraw) {
        regeneratingVis.value = true
        visProgress.value = null
        try {
          await streamRegenerateVis(dom)
          lastResultVisDom.value = dom
          lastResultVisScoreThr.value = scoreThr.value
          lastResultVisMinArea.value = minArea.value
        } finally {
          regeneratingVis.value = false
          visProgress.value = null
        }
      }
    }

    window.open(toAbsoluteUrl(galleryUrl(Date.now())), '_blank', 'noopener,noreferrer')
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
    regeneratingVis.value = false
    visProgress.value = null
  }
}

function onResultPanelKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    if (apiStatus.value === 'ok' && !regeneratingVis.value) openResultGallery()
  }
}

async function startSegmentation() {
  errorMsg.value = ''
  const dom = domFilename.value.trim()

  try {
    const hp = new URLSearchParams({ dom_filename: dom })
    if (userDataDir.value) hp.set('data_dir', userDataDir.value)
    const st = await fetch(api(`/api/segment/has-existing?${hp.toString()}`), {
      credentials: 'include',
    })
    const stJson = await st.json().catch(() => ({}))
    if (!st.ok) throw new Error(typeof stJson.detail === 'string' ? stJson.detail : st.statusText)

    if (!stJson.has_tiles) {
      errorMsg.value = '未找到 DOM 切片，请先在「数据管理」中完成切分后再分割。'
      return
    }

    let overwrite = false
    if (stJson.has_any_pkl) {
      const ok = window.confirm(
        '已存在分割结果（pkl），是否覆盖？\n选择「确定」将重新运行 run_model_from_config.py，结果写入 segmentation_result 目录。',
      )
      if (!ok) return
      overwrite = true
    }

    segmenting.value = true
    progress.value = 0
    segmentProgress.value = null

    const runBody: Record<string, unknown> = {
      dom_filename: dom,
      overwrite,
      score_thr: scoreThr.value,
      min_canopy_area_m2: minArea.value,
    }
    if (userDataDir.value) runBody.data_dir = userDataDir.value

    const r = await fetch(api('/api/segment/run'), {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/x-ndjson, application/json',
      },
      body: JSON.stringify(runBody),
    })
    if (!r.ok) {
      const data = await r.json().catch(() => ({}))
      const d = data.detail
      throw new Error(typeof d === 'string' ? d : r.statusText)
    }
    const processed = await consumeSegmentRunStream(r)
    progress.value = 100
    lastResultVisDom.value = dom
    lastResultVisScoreThr.value = scoreThr.value
    lastResultVisMinArea.value = minArea.value
    window.alert(`分割完成，已处理 ${processed} 块。可在「查看分割小图」中浏览。`)
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
    progress.value = 0
  } finally {
    segmenting.value = false
    segmentProgress.value = null
  }
}

onMounted(async () => {
  await checkHealth()
  if (apiStatus.value === 'ok') {
    await hydrateFromSession()
    await tryOpenTilesAfterUploadIntent()
  }
})

onActivated(async () => {
  if (apiStatus.value === 'ok') {
    await hydrateFromSession()
    await tryOpenTilesAfterUploadIntent()
  }
})
</script>

<template>
  <div class="page">
    <h1 class="page-title">单木分割</h1>

    <section class="group">
      <h2>分割参数设置</h2>
      <div class="form-grid">
        <label>选择模型:</label>
        <select v-model="model" class="input" disabled>
          <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
        </select>
        <label>DOM 文件名:</label>
        <input
          v-model="domFilename"
          type="text"
          class="input"
          placeholder="与数据管理上传的 DOM 同名；有会话时将自动填入"
        />
        <label>置信度阈值:</label>
        <div class="slider-row">
          <input v-model.number="confidence" type="range" min="50" max="95" class="slider" />
          <span>{{ confidence }}%（score_thr = {{ scoreThr.toFixed(2) }}）</span>
        </div>
        <label>最小树冠面积 (m²):</label>
        <input
          v-model.number="minArea"
          type="number"
          min="0"
          step="0.01"
          class="input narrow"
        />
      </div>
      <p v-if="apiStatus !== 'ok'" class="api-warn">
        API 未就绪（{{ apiRootHint }}）。开发环境建议 VITE_API_BASE_URL 留空以走代理。
      </p>
    </section>

    <div class="viz-row">
      <section class="group half">
        <h2>原始数据</h2>
        <div class="tile-panel">
          <p class="panel-hint">
            对应 DOM 切分后的 800×800 影像块（与 pkl 同在服务器目录
            <code class="code">segmentation_result/</code>）；本按钮仅浏览原始切片，不含树心标注。上传新 DOM
            后进入本页会自动切分并打开缩略图画廊。
          </p>
          <button
            type="button"
            class="btn btn-secondary"
            :disabled="apiStatus !== 'ok'"
            @click="openSegmentedTileGallery"
          >
            查看 DOM 切片缩略图
          </button>
        </div>
      </section>
      <section class="group half">
        <h2>分割结果</h2>
        <div
          class="tile-panel tile-panel--clickable"
          role="button"
          tabindex="0"
          :aria-busy="regeneratingVis"
          :aria-disabled="apiStatus !== 'ok' || regeneratingVis"
          @click="apiStatus === 'ok' && !regeneratingVis && openResultGallery()"
          @keydown="onResultPanelKeydown"
        >
          <p class="panel-hint">
            点击本区域查看标明<strong>每棵树中心</strong>的子图（读取
            <code class="code">segmentation_result/marked_result/</code>；pkl 与切片同在
            <code class="code">segmentation_result/</code>）。
          </p>
          <p class="panel-sub">
            拖动<strong>置信度阈值</strong>或修改<strong>最小树冠面积</strong>后，若与上次预览参数不同，再次点击才会调用
            <code class="code">visualize_pkl_mask_centers.py</code>
            重绘；参数未变则直接打开画廊。输出文件带参数后缀，已存在则跳过生成。
          </p>
          <span v-if="regeneratingVis && !visProgress" class="panel-status">正在准备可视化…</span>
          <span v-else-if="!regeneratingVis" class="panel-cta">点击打开预览</span>
        </div>
      </section>
    </div>

    <div v-if="regeneratingVis && visProgress" class="vis-progress-block">
      <p class="vis-progress-label">
        已可视化 {{ visProgress.n }} / {{ visProgress.total }} 张图片
      </p>
      <progress
        class="progress-bar vis-progress-bar"
        :value="visProgress.total > 0 ? visProgress.n : 0"
        :max="Math.max(visProgress.total, 1)"
      />
    </div>

    <div v-if="segmenting && segmentProgress" class="vis-progress-block">
      <p class="vis-progress-label">
        已处理 {{ segmentProgress.n }} / {{ segmentProgress.total }} 块（推理 + 可视化）
      </p>
      <progress
        class="progress-bar vis-progress-bar"
        :value="segmentProgress.total > 0 ? segmentProgress.n : 0"
        :max="Math.max(segmentProgress.total, 1)"
      />
    </div>

    <div class="button-row">
      <button
        type="button"
        class="btn btn-primary"
        :disabled="segmenting || apiStatus !== 'ok'"
        @click="startSegmentation"
      >
        {{ segmenting ? '分割中（调用 run_model_from_config.py）…' : '开始分割' }}
      </button>
      <div class="progress-wrap">
        <progress :value="progress" max="100" class="progress-bar" />
      </div>
    </div>
    <p v-if="errorMsg" class="error">{{ errorMsg }}</p>
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
}

.form-grid {
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: 0.5rem 1rem;
  align-items: center;
}

.form-grid label {
  grid-column: 1;
}

.input {
  padding: 6px 10px;
  background: #2b2b2b;
  border: 1px solid #555;
  border-radius: 4px;
  color: #fff;
}

.input:disabled {
  opacity: 0.85;
  cursor: not-allowed;
}

.input.narrow {
  width: 80px;
}

.slider-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.slider {
  flex: 1;
  max-width: 200px;
}

.viz-row {
  display: flex;
  gap: 1rem;
  margin-bottom: 1rem;
}

.group.half {
  flex: 1;
}

.tile-panel {
  min-height: 140px;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: center;
  gap: 0.75rem;
  background: #2b2b2b;
  border: 2px dashed #555;
  border-radius: 8px;
  padding: 1rem;
}

.tile-panel--clickable {
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.tile-panel--clickable:hover:not([aria-disabled='true']) {
  border-color: #6a8a6a;
  background: #323a32;
}

.tile-panel--clickable:focus-visible {
  outline: 2px solid #81c784;
  outline-offset: 2px;
}

.tile-panel--clickable[aria-disabled='true'] {
  cursor: not-allowed;
  opacity: 0.65;
}

.panel-sub {
  margin: 0;
  font-size: 0.82rem;
  color: #888;
  line-height: 1.45;
}

.panel-cta {
  font-size: 0.88rem;
  font-weight: bold;
  color: #81c784;
}

.panel-status {
  font-size: 0.88rem;
  color: #ffb74d;
}

.vis-progress-block {
  background: #3c3f41;
  border: 2px solid #555;
  border-radius: 8px;
  padding: 0.85rem 1rem;
  margin-bottom: 1rem;
}

.vis-progress-label {
  margin: 0 0 0.5rem 0;
  font-size: 0.92rem;
  color: #c8e6c9;
  font-weight: 600;
}

.vis-progress-bar {
  width: 100%;
  height: 22px;
  accent-color: #2d5a3d;
}

.panel-hint {
  margin: 0;
  font-size: 0.88rem;
  color: #aaa;
  line-height: 1.45;
}

.code {
  font-size: 0.85em;
  color: #9ccc9c;
}

.api-warn {
  margin: 0.75rem 0 0 0;
  font-size: 0.85rem;
  color: #ffb74d;
}

.button-row {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.btn {
  padding: 8px 15px;
  color: #fff;
  border: none;
  border-radius: 4px;
  font-weight: bold;
  cursor: pointer;
}

.btn-secondary {
  background: #4a5b7c;
}

.btn-secondary:hover:not(:disabled) {
  background: #5a6b8c;
}

.btn-primary {
  background: #2d5a3d;
}

.btn-primary:hover:not(:disabled) {
  background: #3d6a4d;
}

.btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.progress-wrap {
  flex: 1;
}

.progress-bar {
  width: 100%;
  height: 24px;
  accent-color: #4a5b7c;
}

.error {
  color: #f44336;
  font-size: 0.9rem;
  margin-top: 0.75rem;
}
</style>
