<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <div class="breeder-layout">
    <aside class="sidebar">
      <h1 class="sidebar-title">TreeGenetic AI</h1>
      <nav class="nav-list">
        <RouterLink to="/" class="nav-item" exact-active-class="active">🏠 项目总览</RouterLink>
        <RouterLink to="/data" class="nav-item" active-class="active">📁 数据管理</RouterLink>
        <RouterLink to="/segmentation" class="nav-item" active-class="active">🌳 单木分割</RouterLink>
        <RouterLink to="/phenotype" class="nav-item" active-class="active">📊 表型提取</RouterLink>
        <RouterLink to="/genetic" class="nav-item" active-class="active">🧬 遗传分析</RouterLink>
        <RouterLink to="/selection" class="nav-item" active-class="active">📈 选择预测</RouterLink>
        <RouterLink to="/visualization" class="nav-item" active-class="active">📋 可视化报告</RouterLink>
      </nav>
      <section class="status-group">
        <h3>系统状态</h3>
        <p>当前项目: 模拟数据</p>
        <p>数据状态: 已加载</p>
        <p>分析状态: 就绪</p>
      </section>
    </aside>
    <main class="main-content">
      <!-- 仅缓存单木分割：离开路由后组件不销毁，进度与流式请求继续在本实例上更新 -->
      <RouterView v-slot="{ Component }">
        <KeepAlive :include="['TreeSegmentationView']">
          <component :is="Component" />
        </KeepAlive>
      </RouterView>
    </main>
  </div>
</template>

<style scoped>
.breeder-layout {
  display: flex;
  min-height: 100vh;
  background: #2b2b2b;
  color: #fff;
}

.sidebar {
  width: 220px;
  min-width: 220px;
  background: #3c3f41;
  border-right: 1px solid #555;
  display: flex;
  flex-direction: column;
  padding: 1rem 0;
}

.sidebar-title {
  font-size: 1rem;
  font-weight: bold;
  text-align: center;
  margin-bottom: 1rem;
  padding: 0 0.5rem;
}

.nav-list {
  display: flex;
  flex-direction: column;
  flex: 1;
}

.nav-item {
  display: block;
  padding: 10px 16px;
  color: #fff;
  text-decoration: none;
  border-bottom: 1px solid #555;
  transition: background 0.2s;
}

.nav-item:hover {
  background: #45494b;
}

.nav-item.active {
  background: #4a5b7c;
  color: #fff;
}

.status-group {
  margin: 1rem;
  padding: 0.75rem;
  border: 2px solid #555;
  border-radius: 8px;
  margin-top: 10px;
}

.status-group h3 {
  font-size: 0.9rem;
  margin-bottom: 0.5rem;
}

.status-group p {
  font-size: 0.8rem;
  color: #bdbdbd;
  margin: 0.25rem 0;
}

.main-content {
  flex: 1;
  padding: 1.5rem;
  overflow: auto;
  background: #2b2b2b;
}
</style>
