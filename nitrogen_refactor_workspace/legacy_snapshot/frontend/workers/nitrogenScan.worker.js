import { evaluateWindows } from '../utils/nitrogenCore'

self.onmessage = (event) => {
  const payload = event.data || {}
  const { requestId, rows = [], options = {} } = payload

  try {
    const result = evaluateWindows(rows, options)
    self.postMessage({
      requestId,
      success: true,
      options,
      ...result
    })
  } catch (error) {
    self.postMessage({
      requestId,
      success: false,
      error: error instanceof Error ? error.message : String(error || '扫描失败')
    })
  }
}
