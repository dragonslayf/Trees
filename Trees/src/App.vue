<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>

<template>
  <div id="app" class="app-breeder">
    <RouterView />
  </div>
</template>

<style>
.app-breeder {
  min-height: 100vh;
  background: #2b2b2b;
  color: #fff;
}
</style>
