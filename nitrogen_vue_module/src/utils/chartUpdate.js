import { Chart } from 'chart.js'

export function buildChartDatasets(rows, selectedTags, tagNames, tagColors, options = {}) {
  const {
    mode = 'normalized',
    tagUnits = {},
    groupDefinitions = [],
    fixedTagBounds = {}
  } = options
  const groupAxisByTag = buildGroupAxisByTag(groupDefinitions)

  return selectedTags.map((tag) => {
    const rawData = rows.map((row) => row.metrics[tag])
    const normalizationBounds = fixedTagBounds[tag] || null
    const data = mode === 'normalized' ? normalizeSeries(rawData, normalizationBounds) : rawData

    return {
      label: `${tag} ${tagNames[tag] || ''}`.trim(),
      data,
      rawData,
      normalizationBounds,
      tag,
      unit: tagUnits[tag] || '',
      borderColor: tagColors[tag] || '#334155',
      backgroundColor: tagColors[tag] || '#334155',
      borderWidth: 1.8,
      pointRadius: 0,
      spanGaps: true,
      tension: 0.25,
      yAxisID: mode === 'grouped' ? (groupAxisByTag[tag] || 'group-default') : 'y'
    }
  })
}

export function createOrUpdateLineChart({
  chart,
  canvas,
  labels,
  datasets,
  plugins,
  mode = 'normalized',
  groupDefinitions = [],
  fixedYBounds = {}
}) {
  if (!canvas) return null

  const options = buildChartOptions(mode, groupDefinitions, fixedYBounds)

  if (!chart) {
    return new Chart(canvas, {
      type: 'line',
      data: { labels, datasets },
      plugins,
      options
    })
  }

  chart.data.labels = labels
  chart.data.datasets = datasets
  chart.options = options
  chart.update('none')
  return chart
}

function buildChartOptions(mode, groupDefinitions, fixedYBounds = {}) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: {
        position: 'bottom',
        labels: { boxWidth: 10, usePointStyle: true }
      },
      tooltip: {
        mode: 'index',
        intersect: false,
        callbacks: {
          label(context) {
            const dataset = context.dataset || {}
            const dataIndex = context.dataIndex
            const rawValue = dataset.rawData?.[dataIndex]
            const displayedValue = context.parsed?.y
            if (!Number.isFinite(rawValue) && !Number.isFinite(displayedValue)) {
              return `${dataset.label}: -`
            }
            if (mode === 'normalized') {
              const normalizedText = Number.isFinite(displayedValue) ? displayedValue.toFixed(2) : '-'
              const rawText = formatValue(rawValue, dataset.unit)
              return `${dataset.label}: ${normalizedText}（原始值 ${rawText}）`
            }
            return `${dataset.label}: ${formatValue(rawValue, dataset.unit)}`
          }
        }
      }
    },
    scales: mode === 'grouped' ? buildGroupedScales(groupDefinitions, fixedYBounds) : buildSingleScales(mode, fixedYBounds)
  }
}

function buildSingleScales(mode, fixedYBounds = {}) {
  const yScale = {
    grid: { color: '#e2e8f0' }
  }
  if (mode === 'normalized') {
    yScale.min = 0
    yScale.max = 1
    yScale.ticks = {
      callback: (value) => `${Math.round(value * 100)}%`
    }
  } else {
    applyFixedBounds(yScale, fixedYBounds.y)
  }
  return {
    x: {
      ticks: { maxTicksLimit: 8 },
      grid: { color: '#e2e8f0' }
    },
    y: yScale
  }
}

function buildGroupedScales(groupDefinitions, fixedYBounds = {}) {
  const scales = {
    x: {
      ticks: { maxTicksLimit: 8 },
      grid: { color: '#e2e8f0' }
    }
  }

  const visibleGroups = groupDefinitions.filter((group) => group.tags?.length)
  visibleGroups.forEach((group, index) => {
    const scale = {
      type: 'linear',
      position: 'left',
      stack: 'trend-groups',
      stackWeight: 1,
      grid: {
        color: index === visibleGroups.length - 1 ? '#cbd5e1' : '#eef2f7'
      },
      ticks: {
        maxTicksLimit: 4
      },
      title: {
        display: true,
        text: group.label,
        color: '#475569',
        font: {
          size: 11,
          weight: '700'
        }
      }
    }
    applyFixedBounds(scale, fixedYBounds[`group-${group.key}`])
    scales[`group-${group.key}`] = scale
  })

  if (!visibleGroups.length) {
    const fallbackScale = {
      type: 'linear',
      position: 'left',
      stack: 'trend-groups',
      stackWeight: 1,
      grid: { color: '#e2e8f0' }
    }
    applyFixedBounds(fallbackScale, fixedYBounds['group-default'])
    scales['group-default'] = fallbackScale
  }

  return scales
}

function applyFixedBounds(scale, bounds) {
  if (!bounds || !Number.isFinite(bounds.min) || !Number.isFinite(bounds.max)) return
  scale.min = bounds.min
  scale.max = bounds.max
  const hiddenTickValues = Array.isArray(bounds.hiddenTickValues) ? bounds.hiddenTickValues : []
  if (Number.isFinite(bounds.stepSize) || hiddenTickValues.length) {
    const previousCallback = scale.ticks?.callback
    scale.ticks = {
      ...(scale.ticks || {}),
      ...(Number.isFinite(bounds.stepSize) ? { stepSize: bounds.stepSize } : {}),
      callback: (value, index, ticks) => {
        if (hiddenTickValues.some((tickValue) => Math.abs(Number(value) - tickValue) < 1e-6)) return ''
        return previousCallback ? previousCallback(value, index, ticks) : formatAxisTick(value)
      }
    }
  }
}

function formatAxisTick(value) {
  const numberValue = Number(value)
  if (!Number.isFinite(numberValue)) return ''
  if (Number.isInteger(numberValue)) return String(numberValue)
  return Math.abs(numberValue) >= 100 ? numberValue.toFixed(0) : numberValue.toFixed(2)
}

function buildGroupAxisByTag(groupDefinitions) {
  return groupDefinitions.reduce((map, group) => {
    group.tags?.forEach((tag) => {
      map[tag] = `group-${group.key}`
    })
    return map
  }, {})
}

function normalizeSeries(values, fixedBounds = null) {
  const numericValues = values.filter(Number.isFinite)
  if (!numericValues.length) return values.map(() => null)
  const minValue = Number.isFinite(fixedBounds?.min) ? fixedBounds.min : Math.min(...numericValues)
  const maxValue = Number.isFinite(fixedBounds?.max) ? fixedBounds.max : Math.max(...numericValues)
  if (maxValue === minValue) {
    return values.map((value) => (Number.isFinite(value) ? 0.5 : null))
  }
  return values.map((value) => (
    Number.isFinite(value)
      ? (value - minValue) / (maxValue - minValue)
      : null
  ))
}

function formatValue(value, unit) {
  if (!Number.isFinite(value)) return '-'
  const text = Math.abs(value) >= 100 ? value.toFixed(0) : value.toFixed(2)
  return unit ? `${text}${unit}` : text
}
