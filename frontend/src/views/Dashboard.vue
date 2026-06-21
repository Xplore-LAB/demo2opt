<template>
  <div class="dashboard dcs-page">
    <header class="dashboard-header">
      <div>
        <h1>空分装置智能运行优化</h1>
        <p>工业运行监视与分析入口</p>
      </div>
      <div class="header-status">
        <span class="state-label ok"><i></i>系统就绪</span>
        <span>数据质量：待接入</span>
      </div>
    </header>

    <main class="dashboard-main">
      <section class="dcs-panel">
        <div class="panel-title">功能模块</div>
        <div class="module-table">
          <router-link to="/pi-analysis" class="module-row primary">
            <span>PI 数据运行分析</span>
            <strong>导入历史数据、查看趋势、执行统计分析和预警分析</strong>
            <em>进入</em>
          </router-link>
          <router-link to="/nitrogen-plug-demo" class="module-row primary">
            <span>氮塞监测 Demo</span>
            <strong>滑动窗口扫描、疑似氮塞检测、故障树溯源和证据建议展示</strong>
            <em>进入</em>
          </router-link>
          <router-link to="/analysis" class="module-row">
            <span>智能分析流程</span>
            <strong>运行语义分析、报告生成和建议操作输出</strong>
            <em>进入</em>
          </router-link>
          <router-link to="/fault-tree" class="module-row">
            <span>故障树管理</span>
            <strong>维护氮塞标准故障树、证据规则、逻辑门和JSON导入导出</strong>
            <em>进入</em>
          </router-link>
        </div>
      </section>

      <section class="dcs-panel status-panel">
        <div class="panel-title">系统概览</div>
        <div class="overview-grid">
          <div><span>当前装置</span><strong>ASU-1 号空分装置</strong></div>
          <div><span>数据源状态</span><strong>历史数据模拟 / 实时预留</strong></div>
          <div><span>当前状态</span><strong>正常</strong></div>
          <div><span>预警数量</span><strong>0</strong></div>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
</script>

<style scoped>
.dashboard {
  min-height: 100vh;
  background: #d6d6d6;
}

.dashboard-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 14px;
  border-bottom: 2px solid #4f4f4f;
  background: #cfcfcf;
}

.dashboard-header h1 {
  margin: 0;
  font-size: 24px;
}

.dashboard-header p {
  margin: 4px 0 0;
  color: #4b4b4b;
  font-size: 13px;
}

.header-status {
  display: flex;
  gap: 14px;
  align-items: center;
  padding: 7px 10px;
  border: 1px solid #7a7a7a;
  background: #e3e3e3;
  font-size: 12px;
}

.state-label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-weight: 700;
}

.state-label i {
  width: 9px;
  height: 9px;
  border: 1px solid #4f4f4f;
  background: #1fa64a;
}

.dashboard-main {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(280px, .8fr);
  gap: 8px;
  padding: 8px;
}

.dcs-panel {
  border: 1px solid #7a7a7a;
  background: #e3e3e3;
}

.panel-title {
  min-height: 28px;
  display: flex;
  align-items: center;
  padding: 0 8px;
  border-bottom: 1px solid #7a7a7a;
  background: #d0d0d0;
  font-size: 14px;
  font-weight: 700;
}

.module-table {
  display: grid;
  gap: 0;
}

.module-row {
  display: grid;
  grid-template-columns: 180px 1fr 56px;
  gap: 10px;
  align-items: center;
  min-height: 46px;
  padding: 0 10px;
  border-bottom: 1px solid #a0a0a0;
  color: #1f1f1f;
  text-decoration: none;
}

.module-row:last-child {
  border-bottom: none;
}

.module-row:hover,
.module-row.primary {
  background: #dcdcdc;
}

.module-row span,
.module-row em {
  font-weight: 700;
  font-style: normal;
}

.module-row strong {
  color: #4b4b4b;
  font-size: 13px;
  font-weight: 400;
}

.module-row em {
  justify-self: end;
  min-width: 44px;
  padding: 4px 0;
  border: 1px solid #4f4f4f;
  background: #2e75b6;
  color: #fff;
  text-align: center;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  padding: 8px;
}

.overview-grid div {
  min-height: 54px;
  padding: 7px;
  border: 1px solid #a0a0a0;
  background: #dcdcdc;
}

.overview-grid span,
.overview-grid strong {
  display: block;
}

.overview-grid span {
  margin-bottom: 6px;
  color: #4b4b4b;
  font-size: 12px;
}

.overview-grid strong {
  font-size: 16px;
}

@media (max-width: 860px) {
  .dashboard-header,
  .dashboard-main,
  .module-row {
    grid-template-columns: 1fr;
  }

  .dashboard-header {
    align-items: flex-start;
  }
}
</style>
