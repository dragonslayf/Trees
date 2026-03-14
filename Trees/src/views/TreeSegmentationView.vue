<script setup lang="ts">
import { ref } from 'vue'

const model = ref('PointNet++')
const confidence = ref(80)
const minArea = ref(10)
const progress = ref(0)

const models = ['PointNet++', 'Mask R-CNN', 'U-Net', '自定义模型']

function startSegmentation() {
  progress.value = 0
  const t = setInterval(() => {
    progress.value += 5
    if (progress.value >= 100) clearInterval(t)
  }, 100)
}
</script>

<template>
  <div class="page">
    <h1 class="page-title">🌳 单木分割</h1>

    <section class="group">
      <h2>分割参数设置</h2>
      <div class="form-grid">
        <label>选择模型:</label>
        <select v-model="model" class="input">
          <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
        </select>
        <label>置信度阈值:</label>
        <div class="slider-row">
          <input v-model.number="confidence" type="range" min="50" max="95" class="slider" />
          <span>{{ confidence }}%</span>
        </div>
        <label>最小树冠面积:</label>
        <input v-model.number="minArea" type="number" min="1" max="100" class="input narrow" />
      </div>
    </section>

    <div class="viz-row">
      <section class="group half">
        <h2>原始数据</h2>
        <div class="placeholder">原始影像/点云显示区域</div>
      </section>
      <section class="group half">
        <h2>分割结果</h2>
        <div class="placeholder">单木分割结果可视化</div>
      </section>
    </div>

    <div class="button-row">
      <button type="button" class="btn" @click="startSegmentation">开始分割</button>
      <div class="progress-wrap">
        <progress :value="progress" max="100" class="progress-bar" />
      </div>
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

.input.narrow {
  width: 80px;
}

.slider-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
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

.placeholder {
  min-height: 180px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #2b2b2b;
  border: 2px dashed #555;
  border-radius: 8px;
  color: #888;
}

.button-row {
  display: flex;
  align-items: center;
  gap: 1rem;
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

.progress-wrap {
  flex: 1;
}

.progress-bar {
  width: 100%;
  height: 24px;
  accent-color: #4a5b7c;
}
</style>
