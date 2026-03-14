<script setup lang="ts">
import { ref } from 'vue'

const breedingRank = ref(
  Array.from({ length: 10 }, (_, i) => ({
    rank: i + 1,
    id: `IND_${1000 + i}`,
    value: (0.85 - i * 0.05).toFixed(2),
  }))
)
</script>

<template>
  <div class="page">
    <h1 class="page-title">项目总览</h1>

    <div class="tabs">
      <div class="tab-panel">
        <h3>📊 表型性状育种值分布 (模拟)</h3>
        <p class="trait-summary">
          树高: 15.72 | 冠幅: 8.58 | 树冠面积: 40.65 | 体积: 80.68 | 通直度: 0.81
        </p>
      </div>
      <div class="tab-panel">
        <h3>🏆 综合育种值排名TOP 10 (模拟)</h3>
        <table class="data-table">
          <thead>
            <tr>
              <th>排名</th>
              <th>个体ID</th>
              <th>综合育种值</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in breedingRank" :key="row.id">
              <td>{{ row.rank }}</td>
              <td>{{ row.id }}</td>
              <td>{{ row.value }}</td>
            </tr>
          </tbody>
        </table>
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

.tabs {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.tab-panel {
  background: #3c3f41;
  border: 1px solid #555;
  border-radius: 8px;
  padding: 1rem;
}

.tab-panel h3 {
  font-size: 1rem;
  margin-bottom: 0.75rem;
}

.trait-summary {
  color: #bdbdbd;
  font-size: 0.9rem;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  background: #3c3f41;
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
