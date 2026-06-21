const STORAGE_KEY = 'demo2opt_fault_trees_v1'

const now = () => new Date().toISOString().slice(0, 19).replace('T', ' ')

const rule = (rule_id, tag, variable_name, statistic, operator, threshold, trend, description, window = '30min', unit = '') => ({
  rule_id,
  tag,
  variable_name,
  window,
  statistic,
  operator,
  threshold,
  unit,
  trend,
  description
})

const node = (node_id, node_name, node_type, parent_id, gate_type = 'NONE', extra = {}) => ({
  node_id,
  node_name,
  node_type,
  branch: extra.branch || '',
  parent_id,
  gate_type,
  k: extra.k ?? null,
  related_tags: extra.related_tags || [],
  evidence_rules: extra.evidence_rules || [],
  mechanism: extra.mechanism || '',
  recommended_action: extra.recommended_action || '',
  risk_note: extra.risk_note || '',
  missing_data_note: extra.missing_data_note || '',
  source: extra.source || '氮塞问答集',
  remark: extra.remark || '',
  enabled: extra.enabled ?? true
})

export const createDefaultFaultTrees = () => ([
  {
    tree_id: 'FT_ASU_N2_BLOCKAGE_V1',
    tree_name: '空分装置氮塞故障树',
    version: '1.0.0',
    description: '用于检测到疑似氮塞后进行原因溯源和诊断推理的标准故障树。',
    domain: '空分装置 / 粗氩系统',
    top_event_name: '疑似氮塞',
    created_at: now(),
    updated_at: now(),
    status: 'draft',
    nodes: [
      node('T0', '疑似氮塞', 'top_event', null, 'OR', { branch: '顶事件', risk_note: '疑似氮塞成立后应避免粗暴调节，优先核对氩馏分含氮量和粗氩塔趋势。' }),
      node('D0', '直接证据：氩馏分含氮量 > 0.1%', 'evidence', 'T0', 'NONE', {
        branch: '检测证据',
        related_tags: ['AN_N2_AR_FRACTION'],
        evidence_rules: [rule('R_D0', 'AN_N2_AR_FRACTION', '氩馏分含氮量', 'last', '>', 0.1, 'high', '氩馏分含氮量超过0.1%', '10min', '%')]
      }),
      node('I0', '间接证据组合成立', 'intermediate_event', 'T0', 'AND', { branch: '检测证据' }),
      node('E_AI705_DOWN', 'AI705持续下降', 'evidence', 'I0', 'NONE', {
        branch: '检测证据',
        related_tags: ['AI705'],
        evidence_rules: [rule('R_S1', 'AI705', '粗氩纯度', 'slope', '<', 0, 'down', 'AI705近30分钟持续下降')]
      }),
      node('G_AUX', '粗氩侧辅助证据满足', 'gate', 'I0', 'K_OUT_OF_N', { branch: '检测证据', k: 2 }),
      node('E_PDI701_DOWN', 'PDI701粗氩塔阻力下降', 'evidence', 'G_AUX', 'NONE', {
        branch: '检测证据',
        related_tags: ['PDI701'],
        evidence_rules: [rule('R_PDI701', 'PDI701', '粗氩塔阻力', 'slope', '<', 0, 'down', 'PDI701近30分钟下降')]
      }),
      node('E_LIC702_UP', 'LIC702液空液位上涨', 'evidence', 'G_AUX', 'NONE', {
        branch: '检测证据',
        related_tags: ['LIC702'],
        evidence_rules: [rule('R_LIC702', 'LIC702', '液空液位', 'slope', '>', 0, 'up', 'LIC702近30分钟上涨')]
      }),
      node('E_FI701_DOWN', 'FI701氩馏分流量下降', 'evidence', 'G_AUX', 'NONE', {
        branch: '检测证据',
        related_tags: ['FI701'],
        evidence_rules: [rule('R_FI701', 'FI701', '氩馏分流量', 'slope', '<', 0, 'down', 'FI701近30分钟下降')]
      }),
      node('E_FIC701_DOWN', 'FIC701粗氩流量下降', 'evidence', 'G_AUX', 'NONE', {
        branch: '检测证据',
        related_tags: ['FIC701'],
        evidence_rules: [rule('R_FIC701', 'FIC701', '粗氩流量', 'slope', '<', 0, 'down', 'FIC701近30分钟下降')]
      }),
      node('R0', '原因溯源', 'intermediate_event', 'T0', 'OR', { branch: '原因溯源' }),
      node('A', '主塔工况异常', 'cause', 'R0', 'OR', { branch: '主塔工况异常', mechanism: '主塔物料、负荷或阀位扰动会改变上塔精馏工况，使富氩区位置和组成发生偏移。' }),
      node('A1', '氧气取出量过大', 'cause', 'A', 'AND', {
        branch: '主塔工况异常',
        related_tags: ['FIQC102', 'AIAS102', 'AI705'],
        mechanism: '氧气取出量过大导致上塔精馏工况变化，富氩区下移，氩馏分含氮量升高，最终诱发氮塞。',
        recommended_action: '适当降低氧气取出量，分步调整，观察AIAS102、AI705、PDI701是否恢复。',
        risk_note: '避免一次性大幅降低氧气取出量，防止主塔和粗氩塔工况进一步波动。'
      }),
      node('A1_E1', 'FIQC102偏高', 'evidence', 'A1', 'NONE', { branch: '主塔工况异常', related_tags: ['FIQC102'], evidence_rules: [rule('R_A1_1', 'FIQC102', '氧气取出量', 'mean', '>', '', 'high', 'FIQC102高于额定值或历史稳态上限', '15min')] }),
      node('A1_E2', 'AIAS102氧气纯度下降', 'evidence', 'A1', 'NONE', { branch: '主塔工况异常', related_tags: ['AIAS102'], evidence_rules: [rule('R_A1_2', 'AIAS102', '氧气纯度', 'slope', '<', 0, 'down', 'AIAS102持续下降')] }),
      node('A1_E3', 'AI705随后下降', 'evidence', 'A1', 'NONE', { branch: '主塔工况异常', related_tags: ['AI705'], evidence_rules: [rule('R_A1_3', 'AI705', '粗氩纯度', 'slope', '<', 0, 'down', 'AI705随后下降')] }),
      node('A2', 'V3阀开度过大', 'cause', 'A', 'AND', {
        branch: '主塔工况异常',
        related_tags: ['V3', 'AIAS102', 'AI705'],
        mechanism: 'V3阀开度过大可能破坏上塔气液平衡，造成氧纯度和粗氩纯度联动下降。',
        recommended_action: '核对近期V3调节记录，按操作规程小幅回调并跟踪主塔与粗氩塔响应。',
        risk_note: '阀位调整需分步执行，避免引起主塔压力和回流突变。'
      }),
      node('A2_E1', 'V3近期明显开大', 'evidence', 'A2', 'NONE', { branch: '主塔工况异常', related_tags: ['V3'], evidence_rules: [rule('R_A2_1', 'V3', 'V3阀开度', 'delta', '>', '', 'up', 'V3近期明显开大', '60min', '%')] }),
      node('A2_E2', 'AIAS102随后下降', 'evidence', 'A2', 'NONE', { branch: '主塔工况异常', related_tags: ['AIAS102'], evidence_rules: [rule('R_A2_2', 'AIAS102', '氧气纯度', 'slope', '<', 0, 'down', 'AIAS102随后下降')] }),
      node('A2_E3', 'AI705随后下降', 'evidence', 'A2', 'NONE', { branch: '主塔工况异常', related_tags: ['AI705'], evidence_rules: [rule('R_A2_3', 'AI705', '粗氩纯度', 'slope', '<', 0, 'down', 'AI705随后下降')] }),
      node('A3', '主塔负荷扰动', 'cause', 'A', 'OR', { branch: '主塔工况异常', mechanism: '主塔负荷快速波动会引起精馏段组分分布变化。', recommended_action: '核对空量、氧氮产品取出和主塔压力趋势，优先稳定负荷。' }),
      node('B', '粗氩系统异常', 'cause', 'R0', 'OR', { branch: '粗氩系统异常', mechanism: '粗氩系统换热、回流和阻力异常会直接削弱粗氩塔分离能力。' }),
      node('B1', '粗氩冷凝器不凝气积聚', 'cause', 'B', 'AND', {
        branch: '粗氩系统异常',
        related_tags: ['LIC702', 'TD_AR_COND', 'PDI701', 'AI705'],
        mechanism: '不凝气积聚会降低粗氩冷凝器换热效率，回流减少后粗氩塔阻力和粗氩纯度下降。',
        recommended_action: '检查不凝气排放、冷凝器温差和液位，必要时按规程处理不凝气。',
        risk_note: '处理前确认联锁和阀位状态，防止冷凝器液位剧烈波动。'
      }),
      node('B1_E1', 'LIC702上涨', 'evidence', 'B1', 'NONE', { branch: '粗氩系统异常', related_tags: ['LIC702'], evidence_rules: [rule('R_B1_1', 'LIC702', '液空液位', 'slope', '>', 0, 'up', 'LIC702上涨')] }),
      node('B1_E2', '冷凝器温差缩小', 'evidence', 'B1', 'NONE', { branch: '粗氩系统异常', related_tags: ['TD_AR_COND'], evidence_rules: [rule('R_B1_2', 'TD_AR_COND', '冷凝器温差', 'slope', '<', 0, 'down', '冷凝器温差缩小')] }),
      node('B1_E3', 'PDI701下降', 'evidence', 'B1', 'NONE', { branch: '粗氩系统异常', related_tags: ['PDI701'], evidence_rules: [rule('R_B1_3', 'PDI701', '粗氩塔阻力', 'slope', '<', 0, 'down', 'PDI701下降')] }),
      node('B1_E4', 'AI705下降', 'evidence', 'B1', 'NONE', { branch: '粗氩系统异常', related_tags: ['AI705'], evidence_rules: [rule('R_B1_4', 'AI705', '粗氩纯度', 'slope', '<', 0, 'down', 'AI705下降')] }),
      node('B2', '粗氩塔回流不足', 'cause', 'B', 'AND', { branch: '粗氩系统异常', mechanism: '回流不足会降低粗氩塔分离效率。', recommended_action: '核对冷凝器液位、回流阀位和塔阻力变化。' }),
      node('C', '前端空气系统扰动', 'cause', 'R0', 'OR', { branch: '前端空气系统扰动', mechanism: '前端空量、压力或净化波动会传导至冷箱并影响精馏稳定性。' }),
      node('D', '操作调节因素', 'cause', 'R0', 'OR', { branch: '操作调节因素', mechanism: '连续或幅度过大的人工调节可能造成系统短时偏离稳态。' })
    ],
    edges: []
  },
  {
    tree_id: 'FT_ASU_O2_PURITY_DROP_V0',
    tree_name: '氧纯度下降故障树',
    version: '0.1.0',
    description: '占位示例，后续可补充标准故障树。',
    domain: '空分装置',
    top_event_name: '氧纯度下降',
    created_at: now(),
    updated_at: now(),
    status: 'draft',
    nodes: [node('T0', '氧纯度下降', 'top_event', null, 'OR', { branch: '顶事件' })],
    edges: []
  },
  {
    tree_id: 'FT_ARGON_RESISTANCE_ABNORMAL_V0',
    tree_name: '粗氩塔阻力异常故障树',
    version: '0.1.0',
    description: '占位示例，后续可补充标准故障树。',
    domain: '粗氩系统',
    top_event_name: '粗氩塔阻力异常',
    created_at: now(),
    updated_at: now(),
    status: 'disabled',
    nodes: [node('T0', '粗氩塔阻力异常', 'top_event', null, 'OR', { branch: '顶事件' })],
    edges: []
  }
])

const withEdges = (tree) => ({
  ...tree,
  edges: tree.nodes.filter((item) => item.parent_id).map((item) => ({ from: item.parent_id, to: item.node_id })),
  rules: tree.nodes.flatMap((item) => (item.evidence_rules || []).map((ruleItem) => ({
    ...ruleItem,
    node_id: item.node_id
  })))
})

const readTrees = () => {
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) {
    const defaults = createDefaultFaultTrees()
    localStorage.setItem(STORAGE_KEY, JSON.stringify(defaults))
    return defaults
  }
  try {
    return JSON.parse(raw)
  } catch {
    const defaults = createDefaultFaultTrees()
    localStorage.setItem(STORAGE_KEY, JSON.stringify(defaults))
    return defaults
  }
}

const writeTrees = (trees) => localStorage.setItem(STORAGE_KEY, JSON.stringify(trees))

export async function getFaultTrees() {
  return readTrees().map(withEdges)
}

export async function getFaultTreeById(treeId) {
  return withEdges(readTrees().find((tree) => tree.tree_id === treeId))
}

export async function createFaultTree(data) {
  const trees = readTrees()
  const item = { ...data, created_at: now(), updated_at: now(), nodes: data.nodes || [], edges: data.edges || [] }
  trees.unshift(item)
  writeTrees(trees)
  return withEdges(item)
}

export async function updateFaultTree(treeId, data) {
  const trees = readTrees()
  const next = trees.map((tree) => tree.tree_id === treeId ? { ...tree, ...data, updated_at: now() } : tree)
  writeTrees(next)
  return withEdges(next.find((tree) => tree.tree_id === treeId))
}

export async function deleteFaultTree(treeId) {
  const trees = readTrees().filter((tree) => tree.tree_id !== treeId)
  writeTrees(trees)
}

export async function createNode(treeId, nodeData) {
  const tree = await getFaultTreeById(treeId)
  return updateFaultTree(treeId, { nodes: [...tree.nodes, nodeData] })
}

export async function updateNode(treeId, nodeId, nodeData) {
  const tree = await getFaultTreeById(treeId)
  return updateFaultTree(treeId, { nodes: tree.nodes.map((item) => item.node_id === nodeId ? { ...item, ...nodeData } : item) })
}

export async function deleteNode(treeId, nodeId) {
  const tree = await getFaultTreeById(treeId)
  const descendants = new Set([nodeId])
  let changed = true
  while (changed) {
    changed = false
    tree.nodes.forEach((item) => {
      if (item.parent_id && descendants.has(item.parent_id) && !descendants.has(item.node_id)) {
        descendants.add(item.node_id)
        changed = true
      }
    })
  }
  return updateFaultTree(treeId, { nodes: tree.nodes.filter((item) => !descendants.has(item.node_id)) })
}

export async function exportFaultTree(treeId) {
  return getFaultTreeById(treeId)
}

export async function importFaultTree(json) {
  const data = typeof json === 'string' ? JSON.parse(json) : json
  const tree = { ...data, updated_at: now(), nodes: data.nodes || [], edges: data.edges || [] }
  const trees = readTrees().filter((item) => item.tree_id !== tree.tree_id)
  trees.unshift(tree)
  writeTrees(trees)
  return withEdges(tree)
}

export function createBlankNode(parentId, type = 'cause') {
  const id = `N_${Date.now().toString(36).toUpperCase()}`
  return node(id, '新节点', type, parentId, type === 'gate' ? 'OR' : 'NONE', { source: '人工维护' })
}

export function createBlankTree() {
  const id = `FT_${Date.now().toString(36).toUpperCase()}`
  return {
    tree_id: id,
    tree_name: '新故障树',
    version: '0.1.0',
    description: '',
    domain: '空分装置',
    top_event_name: '新顶事件',
    status: 'draft',
    nodes: [node('T0', '新顶事件', 'top_event', null, 'OR', { branch: '顶事件', source: '人工维护' })],
    edges: []
  }
}
