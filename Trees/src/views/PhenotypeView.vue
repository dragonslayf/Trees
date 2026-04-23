<script setup lang="ts">
import { computed, onActivated, onMounted, ref } from 'vue'
import { useApiBase } from '@/composables/useApiBase'
import { fetchSessionInit } from '@/composables/sessionInit'
import { pickDomFromFiles } from '@/lib/userWorkspace'

defineOptions({ name: 'PhenotypeView' })

type PhenotypeRow = {
  tree_id: string
  height_m: number | null
  crown_major_m: number | null
  crown_minor_m: number | null
  canopy_area_m2: number | null
  volume_m3: number | null
  dbh_cm: number | null
  lon: number | null
  lat: number | null
  index: number
}
type SortableKey = keyof Pick<
  PhenotypeRow,
  | 'tree_id'
  | 'height_m'
  | 'crown_major_m'
  | 'crown_minor_m'
  | 'canopy_area_m2'
  | 'volume_m3'
  | 'dbh_cm'
  | 'lon'
  | 'lat'
>

const { api, apiRootHint } = useApiBase()

const apiStatus = ref<'unknown' | 'ok' | 'error'>('unknown')
const errorMsg = ref('')
const loading = ref(false)
const userDataDir = ref<string | null>(null)
const availableFiles = ref<string[]>([])
const rows = ref<PhenotypeRow[]>([])
const count = ref(0)
const heightMissingCount = ref(0)
const currentDom = ref<string>('')
const currentChm = ref<string | null>(null)
const PHENOTYPE_REFRESH_KEY = 'trees_phenotype_refresh_pending'
const sortKey = ref<SortableKey>('tree_id')
const sortOrder = ref<'asc' | 'desc'>('asc')
const showHistogram = ref(false)

const histMetrics = [
  { key: 'canopy_area_m2', label: '树冠面积(m²)' },
  { key: 'height_m', label: '树高(m)' },
  { key: 'dbh_cm', label: '胸径DBH(cm)' },
] as const

function fmt(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return '—'
  return Number(v).toFixed(digits)
}

async function checkHealth() {
  try {
    const r = await fetch(api('/health'), { credentials: 'include' })
    apiStatus.value = r.ok ? 'ok' : 'error'
  } catch {
    apiStatus.value = 'error'
  }
}

async function hydrateSessionAndFiles() {
  const out = await fetchSessionInit(api)
  if (!out.ok) throw new Error(out.detail)
  const dd = out.data.data_dir
  userDataDir.value = typeof dd === 'string' ? dd : null

  const fr = await fetch(api('/api/user/files'), { credentials: 'include' })
  if (!fr.ok) throw new Error('读取用户文件列表失败')
  const fj = (await fr.json().catch(() => ({}))) as { files?: string[] }
  availableFiles.value = Array.isArray(fj.files) ? fj.files : []
  const picked = pickDomFromFiles(availableFiles.value)
  if (picked) currentDom.value = picked
  const chm = availableFiles.value.find((f) => /\.(tif|tiff)$/i.test(f) && /chm/i.test(f))
  currentChm.value = chm ?? null
}

async function extractPhenotypes() {
  errorMsg.value = ''
  if (!currentDom.value.trim()) {
    errorMsg.value = '未找到 DOM 文件，请先在数据管理页上传 DOM'
    return
  }
  if (!userDataDir.value) {
    errorMsg.value = '会话数据目录为空，请先回到数据管理页建立会话'
    return
  }
  loading.value = true
  try {
    const p = new URLSearchParams()
    p.set('dom_filename', currentDom.value.trim())
    p.set('data_dir', userDataDir.value)
    if (currentChm.value) p.set('chm_filename', currentChm.value)
    const r = await fetch(api(`/api/phenotype/extract?${p.toString()}`), {
      credentials: 'include',
    })
    const data = (await r.json().catch(() => ({}))) as {
      detail?: string
      rows?: PhenotypeRow[]
      count?: number
      height_missing_count?: number
    }
    if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : r.statusText)
    rows.value = Array.isArray(data.rows) ? data.rows : []
    count.value = typeof data.count === 'number' ? data.count : rows.value.length
    heightMissingCount.value =
      typeof data.height_missing_count === 'number' ? data.height_missing_count : 0
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

type HistogramItem = {
  label: string
  bins: Array<{ left: number; right: number; n: number }>
  xTicks: number[]
  yTicks: number[]
  yMax: number
}

function toggleSort(k: SortableKey) {
  if (sortKey.value === k) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = k
    sortOrder.value = 'asc'
  }
}

function sortIndicator(k: SortableKey): string {
  if (sortKey.value !== k) return '↕'
  return sortOrder.value === 'asc' ? '▲' : '▼'
}

function buildHistogram(values: number[], bins = 10): Array<{ left: number; right: number; n: number }> {
  if (!values.length) return []
  const min = Math.min(...values)
  const max = Math.max(...values)
  if (Math.abs(max - min) < 1e-12) return [{ left: min, right: max, n: values.length }]
  const step = (max - min) / bins
  const arr = Array.from({ length: bins }, (_, i) => ({
    left: min + i * step,
    right: i === bins - 1 ? max : min + (i + 1) * step,
    n: 0,
  }))
  for (const v of values) {
    let idx = Math.floor((v - min) / step)
    if (idx < 0) idx = 0
    if (idx >= bins) idx = bins - 1
    arr[idx]!.n += 1
  }
  return arr
}

function buildLinearTicks(min: number, max: number, segments = 4): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return []
  if (Math.abs(max - min) < 1e-12) return [min]
  const out: number[] = []
  for (let i = 0; i <= segments; i += 1) {
    out.push(min + ((max - min) * i) / segments)
  }
  return out
}

function buildYTicks(maxN: number, segments = 4): number[] {
  const m = Math.max(1, maxN)
  const out: number[] = []
  for (let i = segments; i >= 0; i -= 1) {
    out.push(Math.round((m * i) / segments))
  }
  return out
}

const histograms = computed<HistogramItem[]>(() => {
  return histMetrics.map((m) => {
    const values = rows.value
      .map((r) => r[m.key] as number | null)
      .filter((v): v is number => typeof v === 'number' && Number.isFinite(v))
    const bins = buildHistogram(values, 12)
    const xMin = bins.length ? bins[0]!.left : 0
    const xMax = bins.length ? bins[bins.length - 1]!.right : 0
    const yMax = bins.length ? Math.max(...bins.map((b) => b.n), 1) : 1
    return {
      label: m.label,
      bins,
      xTicks: buildLinearTicks(xMin, xMax, 4),
      yTicks: buildYTicks(yMax, 4),
      yMax,
    }
  })
})

const sortedRows = computed(() => {
  const k = sortKey.value
  const dir = sortOrder.value === 'asc' ? 1 : -1
  return [...rows.value].sort((a, b) => {
    const av = a[k]
    const bv = b[k]
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir
    return String(av).localeCompare(String(bv), 'zh-CN') * dir
  })
})

async function initPage() {
  await checkHealth()
  if (apiStatus.value !== 'ok') return
  await hydrateSessionAndFiles()
  if (!currentDom.value) {
    rows.value = []
    count.value = 0
    heightMissingCount.value = 0
    return
  }
  const force = sessionStorage.getItem(PHENOTYPE_REFRESH_KEY) === '1'
  if (force) sessionStorage.removeItem(PHENOTYPE_REFRESH_KEY)
  if (force || rows.value.length === 0) await extractPhenotypes()
}

onMounted(() => {
  void initPage()
})
onActivated(() => {
  void initPage()
})
</script>

<template>
  <div class="page">
    <h1 class="page-title">📊 表型提取与整理</h1>

    <section class="group">
      
      <p class="hint">DOM: {{ currentDom || '未找到' }}</p>
      <p class="hint">CHM: {{ currentChm || '未提供（树高留空）' }}</p>
      <p class="hint" v-if="apiStatus !== 'ok'">API 未就绪（{{ apiRootHint }}）</p>
      <div class="btn-row">
        <button type="button" class="btn" :disabled="loading || apiStatus !== 'ok'" @click="extractPhenotypes">
          {{ loading ? '更新中…' : '立即刷新表型' }}
        </button>
        <button type="button" class="btn btn-secondary" @click="showHistogram = !showHistogram">
          {{ showHistogram ? '收起直方图' : '查看直方图' }}
        </button>
      </div>
      <div v-if="showHistogram" class="hist-inline">
        <h2>分布可视化（直方图）</h2>
        <div class="hist-grid">
          <div v-for="h in histograms" :key="h.label" class="hist-card">
            <h3>{{ h.label }}</h3>
            <div v-if="h.bins.length" class="hist-axis-label">区间由左到右递增</div>
            <div v-if="h.bins.length" class="hist-chart">
              <div class="y-axis-scale">
                <span v-for="(yt, idx) in h.yTicks" :key="`${h.label}-y-${idx}`">{{ yt }}</span>
              </div>
              <div class="plot-wrap">
                <div class="bars">
                  <div
                    v-for="(b, idx) in h.bins"
                    :key="`${h.label}-${idx}`"
                    class="bar-col"
                    :title="`${b.left.toFixed(2)} ~ ${b.right.toFixed(2)}: ${b.n}`"
                  >
                    <div class="bar" :style="{ height: `${(b.n / h.yMax) * 120}px` }" />
                  </div>
                </div>
              </div>
            </div>
            <div v-if="h.bins.length" class="x-ticks">
              <span v-for="(xt, idx) in h.xTicks" :key="`${h.label}-x-${idx}`">{{ xt.toFixed(1) }}</span>
            </div>
            <div v-if="h.bins.length" class="x-axis-title">{{ h.label }}</div>
            <p v-else class="hint">暂无可用数据</p>
          </div>
        </div>
      </div>
    </section>

    <section class="group">
      <h2>表型结果表</h2>
      <p class="hint">总树木数：{{ count }}；树高缺失：{{ heightMissingCount }}（未提供 CHM 或 CHM 无值）</p>
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th><button type="button" class="th-btn" @click="toggleSort('tree_id')">树木ID(经纬度) {{ sortIndicator('tree_id') }}</button></th>
              <th><button type="button" class="th-btn" @click="toggleSort('height_m')">树高(m) {{ sortIndicator('height_m') }}</button></th>
              <th><button type="button" class="th-btn" @click="toggleSort('crown_major_m')">冠幅主轴(m) {{ sortIndicator('crown_major_m') }}</button></th>
              <th><button type="button" class="th-btn" @click="toggleSort('crown_minor_m')">冠幅次轴(m) {{ sortIndicator('crown_minor_m') }}</button></th>
              <th><button type="button" class="th-btn" @click="toggleSort('canopy_area_m2')">树冠面积(m²) {{ sortIndicator('canopy_area_m2') }}</button></th>
              <th><button type="button" class="th-btn" @click="toggleSort('volume_m3')">体积(m³) {{ sortIndicator('volume_m3') }}</button></th>
              <th><button type="button" class="th-btn" @click="toggleSort('dbh_cm')">DBH(cm) {{ sortIndicator('dbh_cm') }}</button></th>
              <th><button type="button" class="th-btn" @click="toggleSort('lon')">经度 {{ sortIndicator('lon') }}</button></th>
              <th><button type="button" class="th-btn" @click="toggleSort('lat')">纬度 {{ sortIndicator('lat') }}</button></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in sortedRows" :key="row.tree_id">
              <td>{{ row.tree_id }}</td>
              <td>{{ fmt(row.height_m, 2) }}</td>
              <td>{{ fmt(row.crown_major_m, 2) }}</td>
              <td>{{ fmt(row.crown_minor_m, 2) }}</td>
              <td>{{ fmt(row.canopy_area_m2, 2) }}</td>
              <td>{{ fmt(row.volume_m3, 2) }}</td>
              <td>{{ fmt(row.dbh_cm, 2) }}</td>
              <td>{{ fmt(row.lon, 7) }}</td>
              <td>{{ fmt(row.lat, 7) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="errorMsg" class="error">{{ errorMsg }}</p>
    </section>

  </div>
</template>

<style scoped>
.page-title { font-size: 1.25rem; font-weight: bold; margin-bottom: 1rem; }
.group { background: #3c3f41; border: 2px solid #555; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }
.group h2 { font-size: 0.95rem; margin: -0.5rem 0 0.75rem 0; }
.hint { color: #aaa; font-size: 0.85rem; margin: 0.3rem 0; }
.table-wrap { overflow-x: auto; }
.data-table { width: 100%; border-collapse: collapse; }
.data-table th, .data-table td { padding: 8px 10px; border: 1px solid #555; text-align: left; white-space: nowrap; }
.data-table th { background: #4a5b7c; color: #fff; }
.th-btn { width: 100%; padding: 0; margin: 0; border: 0; background: transparent; color: inherit; font: inherit; text-align: left; cursor: pointer; font-weight: 700; }
.btn { padding: 8px 15px; background: #4a5b7c; color: #fff; border: none; border-radius: 4px; font-weight: bold; cursor: pointer; }
.btn-row { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.btn-secondary { background: #455a64; }
.btn-secondary:hover:not(:disabled) { background: #546e7a; }
.btn:hover:not(:disabled) { background: #5a6b8c; }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.error { color: #f44336; font-size: 0.9rem; margin-top: 0.5rem; }
.hist-inline { margin-top: 1rem; border-top: 1px solid #555; padding-top: 0.8rem; }
.hist-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1rem; }
.hist-card { background: #25282b; border: 1px solid #4f5a67; border-radius: 8px; padding: 0.9rem; box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.03); }
.hist-card h3 { margin: 0 0 0.6rem 0; font-size: 0.9rem; color: #ddd; }
.hist-axis-label { color: #9aa7b5; font-size: 0.78rem; margin-bottom: 0.45rem; letter-spacing: 0.02em; }
.hist-chart { display: flex; align-items: stretch; gap: 0.45rem; }
.y-axis-scale { width: 26px; min-height: 140px; display: flex; flex-direction: column; justify-content: space-between; align-items: flex-end; color: #7f8a95; font-size: 0.7rem; }
.plot-wrap { flex: 1; border-left: 1px solid #6b7481; border-bottom: 1px solid #6b7481; padding: 0 4px 0 6px; }
.bars { display: flex; align-items: flex-end; gap: 4px; min-height: 140px; margin-bottom: 0; }
.bar-col { flex: 1; display: flex; align-items: flex-end; justify-content: center; }
.bar { width: 100%; background: linear-gradient(180deg, #6f8fc8 0%, #5577b2 100%); border-radius: 3px 3px 0 0; min-height: 2px; }
.x-ticks { display: flex; justify-content: space-between; font-size: 0.68rem; color: #7f8a95; margin: 2px 0 0 30px; }
.x-axis-title { text-align: center; font-size: 0.74rem; color: #9aa7b5; margin-top: 4px; letter-spacing: 0.02em; }
</style>
