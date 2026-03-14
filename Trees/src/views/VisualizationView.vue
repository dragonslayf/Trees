<script setup lang="ts">
import { ref } from 'vue'

const reportFormat = ref<'pdf' | 'html'>('pdf')

function generateReport() {
  alert(`${reportFormat.value.toUpperCase()}报告生成完成！`)
}
</script>

<template>
  <div class="page">
    <h1 class="page-title">📋 可视化与报告</h1>

    <div class="viz-tabs">
      <div class="viz-panel">
        <h3>🌍 优良个体空间位置可视化</h3>
        <div class="placeholder">DEM展示</div>
      </div>
      <div class="viz-panel">
        <h3>📊 优良个体育种值结果展示</h3>
        <div class="placeholder">优良个体</div>
      </div>
    </div>

    <section class="group">
      <h2>报告生成</h2>
      <div class="report-options">
        <label>
          <input v-model="reportFormat" type="radio" value="pdf" />
          PDF
        </label>
        <label>
          <input v-model="reportFormat" type="radio" value="html" />
          HTML
        </label>
        <button type="button" class="btn" @click="generateReport">生成分析报告</button>
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

.viz-tabs {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-bottom: 1rem;
}

.viz-panel {
  background: #3c3f41;
  border: 1px solid #555;
  border-radius: 8px;
  padding: 1rem;
}

.viz-panel h3 {
  font-size: 1rem;
  margin-bottom: 0.75rem;
}

.placeholder {
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #2b2b2b;
  border: 2px dashed #555;
  border-radius: 8px;
  color: #888;
}

.group {
  background: #3c3f41;
  border: 2px solid #555;
  border-radius: 8px;
  padding: 1rem;
}

.group h2 {
  font-size: 0.95rem;
  margin: -0.5rem 0 0.75rem 0;
}

.report-options {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.report-options label {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  cursor: pointer;
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
