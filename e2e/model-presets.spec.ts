import { expect, test, type Page } from '@playwright/test'

type LlmConfig = {
  id: string
  name: string
  base_url: string
  api_key: string
  model: string
}

const defaultConfigs: LlmConfig[] = [
  {
    id: 'preset-default',
    name: 'Default Preset',
    base_url: 'https://api.openai.com/v1',
    api_key: 'sk-demo',
    model: 'gpt-4o-mini',
  },
]

type SampleFile = {
  name: string
  path: string
  size: number
  updated_at: string
  is_default: boolean
}

const defaultSampleFiles: SampleFile[] = [
  {
    name: 'sample-1.xlsx',
    path: 'data/sample-1.xlsx',
    size: 123456,
    updated_at: '2026-03-04T19:12:47',
    is_default: true,
  },
]

const jsonOk = (data: unknown) => ({
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify(data),
})

async function installMockWebSocket(page: Page) {
  await page.addInitScript(() => {
    const sockets: any[] = []

    class MockWebSocket {
      static CONNECTING = 0
      static OPEN = 1
      static CLOSING = 2
      static CLOSED = 3
      readyState = MockWebSocket.CONNECTING
      onopen: ((event: unknown) => void) | null = null
      onclose: ((event: unknown) => void) | null = null
      onmessage: ((event: { data: string }) => void) | null = null
      onerror: ((event: unknown) => void) | null = null
      sent: string[] = []

      constructor(_url: string) {
        sockets.push(this)
        setTimeout(() => {
          this.readyState = MockWebSocket.OPEN
          this.onopen?.({ type: 'open' })
        }, 0)
      }

      send(payload: string) {
        this.sent.push(payload)
      }

      close() {
        this.readyState = MockWebSocket.CLOSED
        this.onclose?.({ type: 'close' })
      }

      addEventListener(event: string, handler: (event: unknown) => void) {
        ;(this as any)[`on${event}`] = handler
      }

      removeEventListener() {}
    }

    ;(window as any).__mockWsPush = (payload: unknown) => {
      const packet = { data: JSON.stringify(payload) }
      sockets.forEach((socket) => socket.onmessage?.(packet))
    }

    ;(window as any).__mockWsSent = () => {
      const messages: unknown[] = []
      sockets.forEach((socket) => {
        socket.sent.forEach((raw: string) => {
          try {
            messages.push(JSON.parse(raw))
          } catch {
            // ignore malformed packets in test helper
          }
        })
      })
      return messages
    }

    ;(window as any).WebSocket = MockWebSocket
  })
}

async function installApiMocks(page: Page, configs: LlmConfig[] = defaultConfigs, samples: SampleFile[] = defaultSampleFiles) {
  await page.route('**/api/health', async (route) => {
    await route.fulfill(jsonOk({ success: true }))
  })

  await page.route('**/api/configs', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill(jsonOk({ success: true, data: configs }))
      return
    }
    await route.fulfill(jsonOk({ success: true, data: { id: 'preset-saved' } }))
  })

  await page.route('**/api/samples', async (route) => {
    await route.fulfill(jsonOk({ success: true, data: samples }))
  })

  await page.route('**/api/ux-metrics', async (route) => {
    await route.fulfill(jsonOk({ success: true }))
  })
}

async function bootstrap(page: Page, configs: LlmConfig[] = defaultConfigs, samples: SampleFile[] = defaultSampleFiles) {
  await installMockWebSocket(page)
  await installApiMocks(page, configs, samples)
}

async function pushWs(page: Page, payload: Record<string, unknown>) {
  await page.evaluate((message) => {
    ;(window as any).__mockWsPush(message)
  }, payload)
}

async function getSentPackets(page: Page) {
  return page.evaluate(() => (window as any).__mockWsSent?.() ?? [])
}

async function openSettings(page: Page) {
  await page.getByTestId('toggle-settings').click()
}

async function chooseSampleSource(page: Page, sampleName = 'sample-1.xlsx') {
  await page.getByTestId('add-data-trigger').click()
  await page.getByText('从示例库选择', { exact: true }).click()
  await page.getByTestId('sample-select').click()
  await page.getByRole('option', { name: sampleName }).click()
  await page.getByTestId('confirm-sample-select').click()
}

async function chooseUploadSource(page: Page, fileName = 'upload.xlsx') {
  const sampleDialog = page.getByTestId('sample-file-dialog')
  if (await sampleDialog.isVisible().catch(() => false)) {
    await sampleDialog.getByRole('button', { name: /取消|鍙栨秷/ }).click()
  }
  await page.getByTestId('add-data-trigger').click()
  await page.getByText('上传本地文件', { exact: true }).click()
  await page.getByTestId('file-input').setInputFiles({
    name: fileName,
    mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    buffer: Buffer.from('mock-upload-content'),
  })
}

async function startDifyRun(page: Page) {
  await openSettings(page)
  await page.getByTestId('mode-dify').click()
  await page.getByTestId('close-settings-dialog').click()
  await chooseSampleSource(page)
  await page.getByTestId('start-analysis').click()

  await expect.poll(async () => {
    const packets = (await getSentPackets(page)) as Array<{ type?: string }>
    return packets.some((item) => item.type === 'start')
  }).toBeTruthy()
}

test.describe('Conversation Flow UX', () => {
  test('start-analysis remains disabled until data source is selected', async ({ page }) => {
    await bootstrap(page)
    await page.goto('/')

    await openSettings(page)
    await page.getByTestId('mode-dify').click()
    await page.getByTestId('close-settings-dialog').click()

    await expect(page.getByTestId('start-analysis')).toBeDisabled()
    await chooseSampleSource(page)
    await expect(page.getByTestId('start-analysis')).toBeEnabled()
  })

  test('sample source start payload includes data_source and sample_file', async ({ page }) => {
    await bootstrap(page)
    await page.goto('/')

    await openSettings(page)
    await page.getByTestId('mode-dify').click()
    await page.getByTestId('close-settings-dialog').click()
    await chooseSampleSource(page, 'sample-1.xlsx')
    await page.getByTestId('start-analysis').click()

    await expect.poll(async () => {
      const packets = (await getSentPackets(page)) as Array<{ type?: string; data_source?: string; sample_file?: string }>
      return packets.some((item) => item.type === 'start' && item.data_source === 'sample' && item.sample_file === 'data/sample-1.xlsx')
    }).toBeTruthy()
  })

  test('quick-run start payload includes auto_confirm', async ({ page }) => {
    await bootstrap(page)
    await page.goto('/')

    await openSettings(page)
    await page.getByTestId('mode-dify').click()
    await page.getByTestId('close-settings-dialog').click()
    await chooseSampleSource(page, 'sample-1.xlsx')
    await page.getByTestId('start-analysis-auto').click()

    await expect.poll(async () => {
      const packets = (await getSentPackets(page)) as Array<{ type?: string; auto_confirm?: boolean; data_source?: string }>
      return packets.some((item) => item.type === 'start' && item.auto_confirm === true && item.data_source === 'sample')
    }).toBeTruthy()
  })

  test('upload source start payload includes data_source and file_data', async ({ page }) => {
    await bootstrap(page)
    await page.goto('/')

    await openSettings(page)
    await page.getByTestId('mode-dify').click()
    await page.getByTestId('close-settings-dialog').click()
    await chooseUploadSource(page, 'upload.xlsx')
    await page.getByTestId('start-analysis').click()

    await expect.poll(async () => {
      const packets = (await getSentPackets(page)) as Array<{ type?: string; data_source?: string; file_data?: string; file_name?: string }>
      return packets.some(
        (item) => item.type === 'start'
          && item.data_source === 'upload'
          && typeof item.file_data === 'string'
          && item.file_data.length > 0
          && item.file_name === 'upload.xlsx',
      )
    }).toBeTruthy()
  })

  test('sample API failure still allows upload source run', async ({ page }) => {
    await bootstrap(page)
    await page.route('**/api/samples', async (route) => {
      await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ success: false, error: 'failed' }) })
    })
    await page.goto('/')

    await openSettings(page)
    await page.getByTestId('mode-dify').click()
    await page.getByTestId('close-settings-dialog').click()

    await page.getByTestId('add-data-trigger').click()
    await page.getByText('从示例库选择', { exact: true }).click()
    await expect(page.locator('.error-text')).toContainText('failed')

    await chooseUploadSource(page, 'fallback-upload.xlsx')
    await page.getByTestId('start-analysis').click()

    await expect.poll(async () => {
      const packets = (await getSentPackets(page)) as Array<{ type?: string; data_source?: string; file_name?: string }>
      return packets.some((item) => item.type === 'start' && item.data_source === 'upload' && item.file_name === 'fallback-upload.xlsx')
    }).toBeTruthy()
  })

  test('loads page and shows model presets in direct mode', async ({ page }) => {
    await bootstrap(page, [
      { id: 'preset-1', name: 'Mock Preset 1', base_url: 'http://mock-url', api_key: 'mock-key', model: 'mock-model' },
      { id: 'preset-2', name: 'Mock Preset 2', base_url: 'http://mock-url-2', api_key: 'mock-key-2', model: 'mock-model-2' },
    ])

    await page.goto('/')

    await expect(page.getByTestId('header-title')).toContainText(/.+/)
    await openSettings(page)
    await page.getByTestId('mode-direct').click()
    await expect(page.getByTestId('label-model-preset')).toBeVisible()
    await expect(page.getByTestId('label-model-url')).toBeVisible()
    await expect(page.locator('label[data-testid="label-model-url"] + .el-input input')).toHaveValue('http://mock-url')

    await page.getByTestId('close-settings-dialog').click()
    await chooseSampleSource(page, 'sample-1.xlsx')
    await page.getByTestId('start-analysis').click()

    await expect.poll(async () => {
      const packets = (await getSentPackets(page)) as Array<{
        type?: string
        mode?: string
        dify_config?: { api_url?: string; api_key?: string }
        llm_config?: { base_url?: string; api_key?: string; model?: string }
      }>
      return packets.some((item) => item.type === 'start'
        && item.mode === 'direct'
        && item.dify_config?.api_url === 'http://localhost/v1/chat-messages'
        && typeof item.dify_config?.api_key === 'string'
        && item.dify_config.api_key.length > 0
        && item.llm_config?.base_url === 'http://mock-url'
        && item.llm_config?.model === 'mock-model')
    }).toBeTruthy()
  })

  test('workspace panel can collapse and keep state after reload', async ({ page }) => {
    await bootstrap(page)
    await page.goto('/')

    await expect(page.getByTestId('toggle-workspace-collapse')).toBeVisible()
    await page.getByTestId('toggle-workspace-collapse').click()
    await expect(page.getByTestId('workspace-collapsed-rail')).toBeVisible()
    await expect(page.getByTestId('workspace-tab-monitor')).toHaveCount(0)

    await page.reload()
    await expect(page.getByTestId('workspace-collapsed-rail')).toBeVisible()

    await page.getByTestId('expand-workspace').click()
    await expect(page.getByTestId('workspace-collapsed-rail')).toHaveCount(0)
    await expect(page.getByTestId('workspace-tab-monitor')).toBeVisible()
  })

  test('mobile layout keeps single column and hides collapse control', async ({ page }) => {
    await page.setViewportSize({ width: 900, height: 900 })
    await bootstrap(page)
    await page.goto('/')

    await expect(page.getByTestId('toggle-workspace-collapse')).toHaveCount(0)
    await expect(page.getByTestId('workspace-collapsed-rail')).toHaveCount(0)
  })

  test('normal flow: 3 confirmations then result', async ({ page }) => {
    await bootstrap(page)
    await page.goto('/')
    await startDifyRun(page)

    await expect(page.locator('.rail-chip').first()).toContainText('步骤 1/8')

    await pushWs(page, {
      type: 'interaction',
      id: 'check-1',
      title: '数据范围确认',
      desc: '确认时间窗口',
      checkpoint_key: 'init_data_range_confirm',
      phase: 'init',
      risk_level: 'medium',
      impact_scope: ['时间窗口'],
      recommended_action: '确认范围并继续',
      blocking: true,
      workflow_step_id: 1,
      workflow_step_title: '数据加载与范围确认',
    })
    await expect(page.getByTestId('action-card')).toContainText('[步骤 1/8] 数据范围确认')
    await page.getByTestId('action-continue').click()

    await pushWs(page, {
      type: 'phase_update',
      phase: 'analysis',
      status: 'running',
      step: 2,
      workflow_step_id: 4,
      workflow_step_title: '工况总览判断',
      workflow_step_state: 'started',
      step_started_at: new Date().toISOString(),
      progress_percent: 55,
      eta_sec: 40,
    })
    await expect(page.locator('[data-testid="step-group-4"]')).toContainText('步骤 4/8')

    await pushWs(page, {
      type: 'interaction',
      id: 'check-2',
      title: '工况总览确认',
      desc: '确认工况总览',
      checkpoint_key: 'analysis_overview_confirm',
      phase: 'analysis',
      risk_level: 'medium',
      impact_scope: ['主换热器', '负荷'],
      recommended_action: '继续异常复核',
      blocking: true,
      workflow_step_id: 4,
      workflow_step_title: '工况总览判断',
    })
    await expect(page.getByTestId('action-card')).toContainText('[步骤 4/8] 工况总览确认')
    await page.getByTestId('action-continue').click()

    await pushWs(page, {
      type: 'interaction',
      id: 'check-3',
      title: '异常候选确认',
      desc: '确认异常候选',
      checkpoint_key: 'analysis_candidate_confirm',
      phase: 'analysis',
      risk_level: 'medium',
      impact_scope: ['压缩机'],
      recommended_action: '继续 AI 诊断',
      blocking: true,
      workflow_step_id: 5,
      workflow_step_title: '时序特征提取与候选复核',
    })
    await expect(page.getByTestId('action-card')).toContainText('[步骤 5/8] 异常候选确认')
    await page.getByTestId('action-continue').click()

    await pushWs(page, {
      type: 'result',
      data: {
        semantic_data: [],
        abnormal_indicators: [],
        reasoning_result: 'analysis done',
        decision_suggestion: 'keep stable',
      },
    })

    await expect(page.getByTestId('workspace-tab-report')).toHaveClass(/active/)
  })

  test('step starts immediately and shows timer + heartbeat on long silence', async ({ page }) => {
    await bootstrap(page)
    await page.goto('/')
    await startDifyRun(page)

    await pushWs(page, {
      type: 'phase_update',
      phase: 'analysis',
      status: 'running',
      step: 3,
      workflow_step_id: 6,
      workflow_step_title: '外挂知识库 API 检索手段',
      workflow_step_state: 'started',
      step_started_at: new Date().toISOString(),
      progress_percent: 62,
      eta_sec: 34,
    })

    const step6Card = page.locator('[data-testid="step-group-6"]')
    await expect(step6Card).toContainText('步骤 6/8')
    await expect(step6Card).toContainText('进行中')

    await page.waitForTimeout(1800)
    await expect(page.locator('[data-testid="step-heartbeat-6"]')).toBeVisible()

    await pushWs(page, {
      type: 'log',
      level: 'info',
      category: 'reasoning',
      message: '知识库 API 检索完成：命中 2 条可执行手段。',
      workflow_step_id: 6,
      workflow_step_title: '外挂知识库 API 检索手段',
    })

    await expect(page.locator('[data-testid="step-heartbeat-6"]')).toHaveCount(0)

    await pushWs(page, {
      type: 'phase_update',
      phase: 'analysis',
      status: 'running',
      step: 3,
      workflow_step_id: 6,
      workflow_step_title: '外挂知识库 API 检索手段',
      workflow_step_state: 'completed',
      step_started_at: new Date(Date.now() - 5000).toISOString(),
      progress_percent: 70,
      eta_sec: 20,
    })
    await expect(step6Card).toContainText('已完成')
  })

  test('llm activity started/completed shows and hides rail loading chip', async ({ page }) => {
    await bootstrap(page)
    await page.goto('/')
    await startDifyRun(page)

    await pushWs(page, {
      type: 'llm_activity',
      event_id: 'llm-evt-1',
      task_key: 'root_cause_diagnosis',
      task_label: '根因诊断',
      status: 'started',
      phase: 'analysis',
      workflow_step_id: 7,
      workflow_step_title: 'AI 根因诊断',
      provider: 'dify',
      model: 'dify-app',
    })

    await expect(page.getByTestId('rail-llm-working')).toContainText('模型处理中 · 根因诊断')

    await pushWs(page, {
      type: 'llm_activity',
      event_id: 'llm-evt-1',
      task_key: 'root_cause_diagnosis',
      task_label: '根因诊断',
      status: 'completed',
      phase: 'analysis',
      workflow_step_id: 7,
      workflow_step_title: 'AI 根因诊断',
      provider: 'dify',
      model: 'dify-app',
    })

    await expect.poll(async () => await page.getByTestId('rail-llm-working').count(), { timeout: 3000 }).toBe(0)
  })

  test('duplicate log messages in same step are merged', async ({ page }) => {
    await bootstrap(page)
    await page.goto('/')
    await startDifyRun(page)

    const duplicateMessage = '正在检索知识库索引...'

    await pushWs(page, {
      type: 'log',
      level: 'info',
      category: 'reasoning',
      message: duplicateMessage,
      workflow_step_id: 6,
      workflow_step_title: '外挂知识库 API 检索手段',
    })
    await pushWs(page, {
      type: 'log',
      level: 'info',
      category: 'reasoning',
      message: duplicateMessage,
      workflow_step_id: 6,
      workflow_step_title: '外挂知识库 API 检索手段',
    })

    await expect(page.locator('.thinking-line').last()).toContainText('x2')
  })

  test('cancel flow: click stop should end current run', async ({ page }) => {
    await bootstrap(page)
    await page.goto('/')
    await startDifyRun(page)

    await pushWs(page, {
      type: 'interaction',
      id: 'stop-1',
      title: '人工确认',
      desc: '是否继续执行',
      phase: 'analysis',
      risk_level: 'medium',
      blocking: true,
      workflow_step_id: 5,
      workflow_step_title: '时序特征提取与候选复核',
    })

    await expect(page.getByTestId('action-card')).toContainText('人工确认')
    await page.getByTestId('action-stop').click()
    await expect(page.getByTestId('start-analysis')).toBeEnabled()

    await expect.poll(async () => {
      const packets = (await getSentPackets(page)) as Array<{ type?: string; id?: string; value?: string }>
      return packets.some((item) => item.type === 'interaction_response' && item.id === 'stop-1' && item.value === 'no')
    }).toBeTruthy()
  })

  test('compatibility: legacy interaction payload still works', async ({ page }) => {
    await bootstrap(page)
    await page.goto('/')
    await startDifyRun(page)

    await pushWs(page, {
      type: 'interaction',
      id: 'legacy-1',
      title: '旧协议确认',
      desc: '仅包含旧字段',
    })

    await expect(page.getByTestId('action-card')).toContainText('旧协议确认')
    await page.getByTestId('action-continue').click()

    await expect.poll(async () => {
      const packets = (await getSentPackets(page)) as Array<{ type?: string; id?: string; value?: string }>
      return packets.some((item) => item.type === 'interaction_response' && item.id === 'legacy-1' && item.value === 'yes')
    }).toBeTruthy()
  })
})
