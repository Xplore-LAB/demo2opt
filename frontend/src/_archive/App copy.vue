<template>
  <router-view></router-view>
</template>

<script setup>
</script>

<style>
html, body, #app {
  height: 100%;
}

body {
  margin: 0;
  padding: 0;
  background:
    radial-gradient(circle at top left, rgba(196, 220, 255, 0.4), transparent 24%),
    radial-gradient(circle at bottom right, rgba(208, 240, 227, 0.45), transparent 26%),
    #f7f7f3;
  font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  color: #202123;
  overflow: hidden;
}
</style>
