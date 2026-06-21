import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import fs from 'fs'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const repoRoot = path.resolve(__dirname, '..')
const envFile = path.resolve(repoRoot, '.env')
const llmConfigsFile = path.resolve(repoRoot, 'llm_configs.json')

function parseEnvFile(content) {
  return content.split(/\r?\n/).reduce((acc, line) => {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) return acc
    const separatorIndex = trimmed.indexOf('=')
    if (separatorIndex === -1) return acc
    const key = trimmed.slice(0, separatorIndex).trim()
    const value = trimmed.slice(separatorIndex + 1).trim()
    acc[key] = value
    return acc
  }, {})
}

const parsedEnv = fs.existsSync(envFile) ? parseEnvFile(fs.readFileSync(envFile, 'utf8')) : {}

let fallbackConfigs = []

if (parsedEnv.LLM_BASE_URL && parsedEnv.LLM_API_KEY) {
  fallbackConfigs.push({
    id: 'system_default',
    name: 'System Default (.env)',
    base_url: parsedEnv.LLM_BASE_URL,
    api_key: `${parsedEnv.LLM_API_KEY.slice(0, 6)}***`,
    api_key_full: parsedEnv.LLM_API_KEY,
    model: parsedEnv.LLM_MODEL_NAME || '',
    type: 'system',
  })
}

if (fs.existsSync(llmConfigsFile)) {
  try {
    const customConfigs = JSON.parse(fs.readFileSync(llmConfigsFile, 'utf8'))
    fallbackConfigs = fallbackConfigs.concat(
      customConfigs.map((config, index) => ({
        id: config.id || `fallback_${index + 1}`,
        ...config,
        type: 'custom',
      })),
    )
  } catch (error) {
    console.warn('Failed to parse llm_configs.json for frontend fallback:', error)
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  define: {
    __FALLBACK_LLM_CONFIGS__: JSON.stringify(fallbackConfigs),
  },
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 8080,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    }
  }
})
