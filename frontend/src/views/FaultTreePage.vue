<template>
  <div class="fault-tree-page">
    <header class="page-header">
      <div>
        <h1>空分装置氮塞故障树管理</h1>
        <p>标准故障树存储、维护、推理调用配置</p>
      </div>
      <router-link to="/" class="back-link">返回首页</router-link>
    </header>
    <section class="workspace">
      <FaultTreeSidebar
        :trees="trees"
        :active-id="activeTreeId"
        @select="selectTree"
        @create="createTree"
        @duplicate="duplicateTree"
        @delete="removeTree"
      />
      <div class="center-shell">
        <FaultTreeViewer
          :tree="activeTree"
          :selected-id="selectedNodeId"
          :expanded-ids="expandedIds"
          @select-node="selectedNodeId = $event"
          @toggle-node="toggleNode"
          @add-child="addChild"
          @copy-node="copyNode"
          @move-node="moveNode"
          @delete-node="removeNode"
          @expand-all="expandAll"
          @collapse-all="collapseAll"
          @mermaid="openMermaid"
          @update-tree="saveTree"
        />
        <JsonImportExportPanel
          @save-local="persistCurrent"
          @load-local="loadTrees"
          @export-json="downloadJson"
          @import-json="handleImport"
        />
      </div>
      <FaultTreeNodeEditor :node="selectedNode" :child-count="selectedChildCount" @update="saveNode" />
    </section>
    <MermaidPreviewModal :visible="mermaidVisible" :source="mermaidSource" :tree="activeTree" @close="mermaidVisible = false" />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import FaultTreeSidebar from '../components/fault-tree/FaultTreeSidebar.vue'
import FaultTreeViewer from '../components/fault-tree/FaultTreeViewer.vue'
import FaultTreeNodeEditor from '../components/fault-tree/FaultTreeNodeEditor.vue'
import MermaidPreviewModal from '../components/fault-tree/MermaidPreviewModal.vue'
import JsonImportExportPanel from '../components/fault-tree/JsonImportExportPanel.vue'
import {
  createBlankNode,
  createBlankTree,
  createFaultTree,
  deleteFaultTree,
  deleteNode,
  exportFaultTree,
  getFaultTrees,
  importFaultTree,
  updateFaultTree,
  updateNode
} from '../services/faultTreeApi'

const trees = ref([])
const activeTreeId = ref('')
const selectedNodeId = ref('')
const expandedIds = reactive(new Set())
const mermaidVisible = ref(false)
const mermaidSource = ref('')

const activeTree = computed(() => trees.value.find((tree) => tree.tree_id === activeTreeId.value) || null)
const selectedNode = computed(() => activeTree.value?.nodes.find((node) => node.node_id === selectedNodeId.value) || null)
const selectedChildCount = computed(() => activeTree.value?.nodes.filter((node) => node.parent_id === selectedNodeId.value).length || 0)

onMounted(loadTrees)

async function loadTrees() {
  trees.value = await getFaultTrees()
  if (!activeTreeId.value || !trees.value.some((tree) => tree.tree_id === activeTreeId.value)) {
    activeTreeId.value = trees.value[0]?.tree_id || ''
  }
  selectedNodeId.value = activeTree.value?.nodes[0]?.node_id || ''
  expandAll()
}

function selectTree(treeId) {
  activeTreeId.value = treeId
  selectedNodeId.value = activeTree.value?.nodes[0]?.node_id || ''
  expandAll()
}

async function refreshTree(tree) {
  trees.value = trees.value.map((item) => item.tree_id === tree.tree_id ? tree : item)
}

async function createTree() {
  const tree = await createFaultTree(createBlankTree())
  trees.value.unshift(tree)
  selectTree(tree.tree_id)
}

async function duplicateTree() {
  if (!activeTree.value) return
  const suffix = Date.now().toString(36).toUpperCase()
  const copy = JSON.parse(JSON.stringify(activeTree.value))
  copy.tree_id = `${copy.tree_id}_COPY_${suffix}`
  copy.tree_name = `${copy.tree_name} 副本`
  copy.version = nextVersion(copy.version)
  copy.status = 'draft'
  const tree = await createFaultTree(copy)
  trees.value.unshift(tree)
  selectTree(tree.tree_id)
}

async function removeTree() {
  if (!activeTree.value || trees.value.length <= 1) return
  if (!window.confirm(`确认删除故障树：${activeTree.value.tree_name}？`)) return
  await deleteFaultTree(activeTreeId.value)
  await loadTrees()
}

async function saveTree(tree) {
  const updated = await updateFaultTree(tree.tree_id, tree)
  refreshTree(updated)
}

async function saveNode(node) {
  if (!activeTree.value) return
  const updated = await updateNode(activeTree.value.tree_id, node.node_id, node)
  refreshTree(updated)
}

async function addChild(parentId, type) {
  if (!activeTree.value) return
  const child = createBlankNode(parentId, type)
  const updated = await updateFaultTree(activeTree.value.tree_id, { nodes: [...activeTree.value.nodes, child] })
  refreshTree(updated)
  expandedIds.add(parentId)
  selectedNodeId.value = child.node_id
}

async function copyNode(nodeId) {
  if (!activeTree.value) return
  const original = activeTree.value.nodes.find((node) => node.node_id === nodeId)
  if (!original) return
  const copy = JSON.parse(JSON.stringify(original))
  copy.node_id = `${original.node_id}_COPY_${Date.now().toString(36).toUpperCase()}`
  copy.node_name = `${original.node_name} 副本`
  const siblings = [...activeTree.value.nodes]
  const index = siblings.findIndex((node) => node.node_id === nodeId)
  siblings.splice(index + 1, 0, copy)
  const updated = await updateFaultTree(activeTree.value.tree_id, { nodes: siblings })
  refreshTree(updated)
  selectedNodeId.value = copy.node_id
}

async function moveNode(nodeId, direction) {
  if (!activeTree.value) return
  const nodes = [...activeTree.value.nodes]
  const index = nodes.findIndex((node) => node.node_id === nodeId)
  if (index < 0) return
  const parentId = nodes[index].parent_id
  let swapIndex = index + direction
  while (swapIndex >= 0 && swapIndex < nodes.length && nodes[swapIndex].parent_id !== parentId) {
    swapIndex += direction
  }
  if (swapIndex < 0 || swapIndex >= nodes.length) return
  ;[nodes[index], nodes[swapIndex]] = [nodes[swapIndex], nodes[index]]
  const updated = await updateFaultTree(activeTree.value.tree_id, { nodes })
  refreshTree(updated)
}

async function removeNode(nodeId) {
  if (!activeTree.value) return
  const node = activeTree.value.nodes.find((item) => item.node_id === nodeId)
  if (!node || node.node_type === 'top_event') return
  if (!window.confirm(`确认删除节点及其子节点：${node.node_name}？`)) return
  const updated = await deleteNode(activeTree.value.tree_id, nodeId)
  refreshTree(updated)
  selectedNodeId.value = updated.nodes[0]?.node_id || ''
}

function toggleNode(nodeId) {
  if (expandedIds.has(nodeId)) expandedIds.delete(nodeId)
  else expandedIds.add(nodeId)
}

function expandAll() {
  expandedIds.clear()
  activeTree.value?.nodes.forEach((node) => expandedIds.add(node.node_id))
}

function collapseAll() {
  expandedIds.clear()
}

async function persistCurrent() {
  if (!activeTree.value) return
  const updated = await updateFaultTree(activeTree.value.tree_id, activeTree.value)
  refreshTree(updated)
}

async function downloadJson() {
  if (!activeTree.value) return
  const tree = await exportFaultTree(activeTree.value.tree_id)
  const blob = new Blob([JSON.stringify(tree, null, 2)], { type: 'application/json;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `${tree.tree_id}.json`
  link.click()
  URL.revokeObjectURL(link.href)
}

async function handleImport(content) {
  try {
    const tree = await importFaultTree(content)
    await loadTrees()
    selectTree(tree.tree_id)
  } catch (error) {
    window.alert(`JSON导入失败：${error.message}`)
  }
}

function openMermaid() {
  mermaidSource.value = buildMermaid(activeTree.value)
  mermaidVisible.value = true
}

function buildMermaid(tree) {
  if (!tree) return 'flowchart TD'
  const lines = ['flowchart TD']
  const esc = (value) => String(value || '').replace(/"/g, "'")
  tree.nodes.forEach((node) => {
    const gate = node.gate_type && node.gate_type !== 'NONE'
      ? `\\n[${node.gate_type === 'K_OUT_OF_N' ? `${node.k || 0}/${tree.nodes.filter((item) => item.parent_id === node.node_id).length}` : node.gate_type}]`
      : ''
    lines.push(`  ${node.node_id}["${esc(node.node_name)}${gate}"]`)
  })
  tree.nodes.filter((node) => node.parent_id).forEach((node) => {
    lines.push(`  ${node.parent_id} --> ${node.node_id}`)
  })
  return lines.join('\n')
}

function nextVersion(version) {
  const parts = String(version || '0.1.0').split('.').map((item) => Number(item) || 0)
  parts[2] += 1
  return parts.join('.')
}
</script>

<style scoped>
.fault-tree-page {
  height: 100vh;
  display: grid;
  grid-template-rows: 54px minmax(0, 1fr);
  background: #d6d6d6;
  color: #1f2529;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 7px 12px;
  border-bottom: 2px solid #4f4f4f;
  background: #cfcfcf;
}

h1 {
  margin: 0;
  font-size: 21px;
}

p {
  margin: 3px 0 0;
  color: #50575d;
  font-size: 12px;
}

.back-link {
  padding: 6px 10px;
  border: 1px solid #586069;
  background: #e8ecef;
  color: #1f2529;
  text-decoration: none;
  font-size: 13px;
}

.workspace {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr) 380px;
  min-height: 0;
  border-top: 1px solid #9b9b9b;
}

.center-shell {
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  min-width: 0;
  min-height: 0;
}

@media (max-width: 1120px) {
  .fault-tree-page {
    height: auto;
    min-height: 100vh;
  }

  .workspace {
    grid-template-columns: 1fr;
  }
}
</style>
