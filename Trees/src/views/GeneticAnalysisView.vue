<script setup lang="ts">
import { ref, computed } from 'vue'

const currentStep = ref(0)
const trait = ref('树高')
const modelType = ref('线性混合模型')
const fixedEffect = ref('区块')
const selectionIntensity = ref(10)
const analysisLog = ref<string[]>([])
const progress = ref(0)
const topN = ref(20)

const heritability = ref('0.000 ± 0.000')
const heritabilityDesc = ref('遗传控制程度: 未分析')
const geneticGain = ref('0.00%')
const geneticGainDesc = ref('选择效果: 未分析')
const response = ref('0.000')
const responseDesc = ref('育种进展: 未分析')

const geneticVar = ref('0.0%')
const envVar = ref('0.0%')
const residualVar = ref('0.0%')

const meanBV = ref('0.000')
const stdBV = ref('0.000')
const maxBV = ref('0.000')
const minBV = ref('0.000')

const breedingTable = ref<Array<{ rank: number; id: string; family: string; value: string }>>([])

const traits = ['树高', '冠幅', '树冠面积', '体积', '通直度']
const modelTypes = ['线性混合模型', '动物模型', '多性状模型']
const fixedEffects = ['区块', '年份', '区块+年份']

function runAnalysis() {
  analysisLog.value = []
  progress.value = 0
  const steps = [
    '正在加载表型数据...',
    '正在构建混合线性模型...',
    '正在估计方差组分...',
    '正在计算遗传力...',
    '正在估计个体育种值...',
    '分析完成！',
  ]
  let i = 0
  const t = setInterval(() => {
    if (i < steps.length) {
      analysisLog.value.push(steps[i]!)
      progress.value = Math.round(((i + 1) / steps.length) * 100)
      i++
    } else {
      clearInterval(t)
      heritability.value = '0.598 ± 0.015'
      heritabilityDesc.value = '该性状受中等强度遗传控制'
      geneticGain.value = '5.98%'
      geneticGainDesc.value = '选择效果: 中等遗传增益'
      response.value = '0.234 m'
      responseDesc.value = '育种进展: 每代提升 0.234m'
      geneticVar.value = '59.8%'
      envVar.value = '24.1%'
      residualVar.value = '16.1%'
      meanBV.value = '0.012'
      stdBV.value = '0.385'
      maxBV.value = '1.245'
      minBV.value = '-0.987'
      breedingTable.value = Array.from({ length: Math.min(topN.value, 20) }, (_, j) => ({
        rank: j + 1,
        id: `IND_${1000 + j}`,
        family: `FAM_${(j % 5) + 1}`,
        value: (0.5 + j * 0.03).toFixed(3),
      }))
    }
  }, 400)
}

const displayBreeding = computed(() =>
  breedingTable.value.length ? breedingTable.value : []
)
</script>

<template>
  <div class="page">
    <h1 class="page-title">🧬 遗传分析</h1>

    <div class="tabs-header">
      <button
        type="button"
        :class="['tab-btn', currentStep === 0 && 'active']"
        @click="currentStep = 0"
      >
        步骤1: 模型设置
      </button>
      <button
        type="button"
        :class="['tab-btn', currentStep === 1 && 'active']"
        @click="currentStep = 1"
      >
        步骤2: 运行分析
      </button>
      <button
        type="button"
        :class="['tab-btn', currentStep === 2 && 'active']"
        @click="currentStep = 2"
      >
        步骤3: 查看结果
      </button>
    </div>

    <div v-show="currentStep === 0" class="tab-panel">
      <div class="form-grid">
        <label>选择性状:</label>
        <select v-model="trait" class="input">
          <option v-for="t in traits" :key="t" :value="t">{{ t }}</option>
        </select>
        <label>遗传模型:</label>
        <select v-model="modelType" class="input">
          <option v-for="m in modelTypes" :key="m" :value="m">{{ m }}</option>
        </select>
        <label>固定效应:</label>
        <select v-model="fixedEffect" class="input">
          <option v-for="f in fixedEffects" :key="f" :value="f">{{ f }}</option>
        </select>
        <label>选择强度(%):</label>
        <input v-model.number="selectionIntensity" type="range" min="1" max="30" class="slider" />
        <span class="slider-value">{{ selectionIntensity }}%</span>
      </div>
    </div>

    <div v-show="currentStep === 1" class="tab-panel">
      <p class="mb">点击开始按钮运行遗传分析:</p>
      <button type="button" class="btn" @click="runAnalysis">开始分析</button>
      <div class="progress-wrap">
        <progress :value="progress" max="100" class="progress-bar" />
      </div>
      <div class="log-box">
        <div v-for="(line, i) in analysisLog" :key="i">{{ line }}</div>
      </div>
    </div>

    <div v-show="currentStep === 2" class="tab-panel">
      <div class="cards-row">
        <div class="card card-green">
          <h3>遗传力估计</h3>
          <p class="card-value">{{ heritability }}</p>
          <p class="card-desc">{{ heritabilityDesc }}</p>
        </div>
        <div class="card card-orange">
          <h3>遗传增益预测</h3>
          <p class="card-value">{{ geneticGain }}</p>
          <p class="card-desc">{{ geneticGainDesc }}</p>
        </div>
        <div class="card card-blue">
          <h3>选择响应</h3>
          <p class="card-value">{{ response }}</p>
          <p class="card-desc">{{ responseDesc }}</p>
        </div>
      </div>

      <section class="group">
        <h2>方差组分分析</h2>
        <div class="variance-row">
          <div class="variance-labels">
            <p class="color-green">遗传方差: {{ geneticVar }}</p>
            <p class="color-orange">环境方差: {{ envVar }}</p>
            <p class="color-blue">残差方差: {{ residualVar }}</p>
          </div>
          <div class="variance-placeholder">(方差组分饼图将显示在这里)</div>
        </div>
      </section>

      <div class="breeding-row">
        <section class="group half">
          <h2>育种值统计</h2>
          <div class="form-grid compact">
            <span>平均育种值:</span><span>{{ meanBV }}</span>
            <span>育种值标准差:</span><span>{{ stdBV }}</span>
            <span>最大育种值:</span><span>{{ maxBV }}</span>
            <span>最小育种值:</span><span>{{ minBV }}</span>
          </div>
        </section>
        <section class="group half">
          <h2>育种值分布</h2>
          <div class="placeholder">(育种值分布直方图将显示在这里)</div>
        </section>
      </div>

      <section class="group">
        <div class="table-control">
          <span>显示前</span>
          <input v-model.number="topN" type="number" min="10" max="100" class="input narrow" />
          <span>个个体</span>
          <button type="button" class="btn small">导出育种值</button>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th>排名</th>
              <th>个体ID</th>
              <th>家系</th>
              <th>育种值</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in displayBreeding" :key="row.id">
              <td>{{ row.rank }}</td>
              <td>{{ row.id }}</td>
              <td>{{ row.family }}</td>
              <td>{{ row.value }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>
  </div>
</template>

<style scoped>
.page-title {
  font-size: 1.25rem;
  font-weight: bold;
  margin-bottom: 1rem;
}

.tabs-header {
  display: flex;
  gap: 2px;
  margin-bottom: 1rem;
}

.tab-btn {
  padding: 8px 15px;
  background: #4a5b7c;
  color: #fff;
  border: none;
  cursor: pointer;
}

.tab-btn.active {
  background: #5a6b8c;
}

.tab-panel {
  background: #3c3f41;
  border: 1px solid #555;
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 1rem;
}

.form-grid {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 0.5rem 1rem;
  align-items: center;
}

.form-grid.compact {
  grid-template-columns: 1fr auto;
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

.input.narrow {
  width: 60px;
}

.slider {
  max-width: 200px;
}

.slider-value {
  grid-column: 2;
}

.mb {
  margin-bottom: 0.75rem;
}

.btn {
  padding: 8px 15px;
  background: #4a5b7c;
  color: #fff;
  border: none;
  border-radius: 4px;
  font-weight: bold;
  cursor: pointer;
  margin-bottom: 0.5rem;
}

.btn:hover {
  background: #5a6b8c;
}

.btn.small {
  padding: 4px 10px;
  font-size: 0.9rem;
}

.progress-wrap {
  margin-bottom: 0.5rem;
}

.progress-bar {
  width: 100%;
  height: 20px;
  accent-color: #4a5b7c;
}

.log-box {
  margin-top: 0.5rem;
  padding: 0.75rem;
  background: #2b2b2b;
  border: 1px solid #555;
  border-radius: 4px;
  min-height: 120px;
  font-family: monospace;
  font-size: 0.85rem;
}

.cards-row {
  display: flex;
  gap: 1rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}

.card {
  flex: 1;
  min-width: 160px;
  padding: 1rem;
  border-radius: 8px;
  border: 1px solid #555;
}

.card h3 {
  font-size: 0.9rem;
  margin-bottom: 0.5rem;
}

.card-value {
  font-size: 1.1rem;
  font-weight: bold;
  margin: 0.5rem 0;
}

.card-desc {
  font-size: 0.85rem;
  color: #bdbdbd;
}

.card-green .card-value {
  color: #4caf50;
}

.card-orange .card-value {
  color: #ff9800;
}

.card-blue .card-value {
  color: #2196f3;
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

.variance-row {
  display: flex;
  gap: 1rem;
  align-items: flex-start;
}

.variance-labels p {
  margin: 0.25rem 0;
}

.color-green {
  color: #4caf50;
}

.color-orange {
  color: #ff9800;
}

.color-blue {
  color: #2196f3;
}

.variance-placeholder,
.placeholder {
  flex: 1;
  min-height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #2b2b2b;
  border: 2px dashed #555;
  border-radius: 8px;
  color: #888;
}

.breeding-row {
  display: flex;
  gap: 1rem;
  margin-bottom: 1rem;
}

.group.half {
  flex: 1;
}

.table-control {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th,
.data-table td {
  padding: 8px 12px;
  border: 1px solid #555;
  text-align: left;
}

.data-table th {
  background: #4a5b7c;
  color: #fff;
}
</style>
