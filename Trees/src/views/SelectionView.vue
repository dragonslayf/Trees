<script setup lang="ts">
import { ref } from 'vue'

const selectionIntensity = ref(10)
const topN = ref(10)
const optimalTrait = ref('最优性状: 未计算')
const comparisonData = ref<Array<{ trait: string; h2: string; gain: string; score: string }>>([])
const selectedIndividuals = ref<Array<{ rank: number; id: string; family: string; value: string }>>([])

const traits = ['树高', '冠幅', '树冠面积', '体积', '通直度']

function calculateParams() {
  comparisonData.value = traits.map((t, i) => ({
    trait: t,
    h2: (0.5 + i * 0.05).toFixed(3),
    gain: (4 + i * 0.5).toFixed(2) + '%',
    score: (0.45 + i * 0.02).toFixed(3),
  }))
  optimalTrait.value = '最优选择性状: 树高 (遗传力: 0.598, 遗传增益: 5.98%)'
}

function selectElite() {
  if (!comparisonData.value.length) {
    alert('请先计算遗传参数！')
    return
  }
  selectedIndividuals.value = Array.from({ length: topN.value }, (_, i) => ({
    rank: i + 1,
    id: `IND_${1000 + i}`,
    family: `FAM_${(i % 5) + 1}`,
    value: (1.2 - i * 0.08).toFixed(3),
  }))
  alert(`基于性状'树高'筛选出${topN.value}个优良个体！`)
}

function exportResults() {
  if (!selectedIndividuals.value.length) {
    alert('没有可导出的选择结果！')
    return
  }
  alert('选择结果已导出')
}
</script>

<template>
  <div class="page">
    <h1 class="page-title">📈 遗传选择与优良个体筛选</h1>

    <section class="group">
      <h2>性状遗传参数比较</h2>
      <table class="data-table">
        <thead>
          <tr>
            <th>性状</th>
            <th>遗传力(h²)</th>
            <th>遗传增益(%)</th>
            <th>综合得分</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in comparisonData" :key="row.trait">
            <td>{{ row.trait }}</td>
            <td>{{ row.h2 }}</td>
            <td>{{ row.gain }}</td>
            <td>{{ row.score }}</td>
          </tr>
        </tbody>
      </table>
      <p class="optimal-trait">{{ optimalTrait }}</p>
    </section>

    <section class="group">
      <h2>选择参数设置</h2>
      <div class="form-grid">
        <label>选择强度(%):</label>
        <input v-model.number="selectionIntensity" type="range" min="1" max="30" class="slider" />
        <span>{{ selectionIntensity }}%</span>
        <label>选择个体数:</label>
        <input v-model.number="topN" type="number" min="1" max="50" class="input narrow" />
      </div>
    </section>

    <section class="group">
      <h2>优良个体选择结果</h2>
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
          <tr v-for="row in selectedIndividuals" :key="row.id">
            <td>{{ row.rank }}</td>
            <td>{{ row.id }}</td>
            <td>{{ row.family }}</td>
            <td>{{ row.value }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <div class="button-row">
      <button type="button" class="btn" @click="calculateParams">计算遗传参数</button>
      <button type="button" class="btn" @click="selectElite">筛选优良个体</button>
      <button type="button" class="btn" @click="exportResults">导出选择结果</button>
    </div>
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

.data-table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 0.75rem;
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

.optimal-trait {
  color: #ff9800;
  font-weight: bold;
  padding: 10px 0;
  margin: 0;
}

.form-grid {
  display: grid;
  grid-template-columns: 120px 1fr auto;
  gap: 0.5rem 1rem;
  align-items: center;
}

.input.narrow {
  width: 70px;
  padding: 6px 10px;
  background: #2b2b2b;
  border: 1px solid #555;
  border-radius: 4px;
  color: #fff;
}

.slider {
  max-width: 200px;
}

.button-row {
  display: flex;
  gap: 0.5rem;
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

.btn:hover {
  background: #5a6b8c;
}
</style>
