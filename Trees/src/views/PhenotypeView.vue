<script setup lang="ts">
import { ref } from 'vue'

const traits = ref({
  height: true,
  crown: true,
  crownArea: true,
  volume: false,
  straightness: false,
})

const tableData = ref<Array<Record<string, string>>>([])

function extractPhenotypes() {
  tableData.value = Array.from({ length: 10 }, (_, i) => ({
    id: `TREE_${i + 1}`,
    height: (15 + i * 0.5).toFixed(1),
    crown: (8 + i * 0.3).toFixed(1),
    crownArea: (50 + i * 5).toFixed(1),
    volume: (120 + i * 10).toFixed(1),
    straightness: (0.85 + i * 0.01).toFixed(2),
    family: `FAM_${Math.floor(i / 2) + 1}`,
  }))
}

function autoMatch() {
  alert('家系自动匹配完成！')
}

function exportData() {
  alert('数据已导出')
}
</script>

<template>
  <div class="page">
    <h1 class="page-title">📊 表型提取与整理</h1>

    <section class="group">
      <h2>选择表型性状</h2>
      <div class="traits-row">
        <label><input v-model="traits.height" type="checkbox" /> 树高 (m)</label>
        <label><input v-model="traits.crown" type="checkbox" /> 冠幅 (m)</label>
        <label><input v-model="traits.crownArea" type="checkbox" /> 树冠面积 (m²)</label>
        <label><input v-model="traits.volume" type="checkbox" /> 体积 (m³)</label>
        <label><input v-model="traits.straightness" type="checkbox" /> 通直度 (0-1)</label>
      </div>
    </section>

    <section class="group">
      <h2>表型数据表格</h2>
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>树木ID</th>
              <th>树高(m)</th>
              <th>冠幅(m)</th>
              <th>树冠面积(m²)</th>
              <th>体积(m³)</th>
              <th>通直度</th>
              <th>家系匹配</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in tableData" :key="row.id">
              <td>{{ row.id }}</td>
              <td>{{ row.height }}</td>
              <td>{{ row.crown }}</td>
              <td>{{ row.crownArea }}</td>
              <td>{{ row.volume }}</td>
              <td>{{ row.straightness }}</td>
              <td>{{ row.family }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <div class="button-row">
      <button type="button" class="btn" @click="extractPhenotypes">提取表型</button>
      <button type="button" class="btn" @click="autoMatch">自动匹配家系</button>
      <button type="button" class="btn" @click="exportData">导出数据</button>
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

.traits-row {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
}

.traits-row label {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  cursor: pointer;
}

.table-wrap {
  overflow-x: auto;
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
