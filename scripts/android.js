import path from 'path'
import os from 'os'
import fs from 'fs'
import { createRequire } from 'module'

const require = createRequire(import.meta.url)
const isWindows = process.platform === 'win32'
const env = { ...process.env }

// 1. Setup JAVA_HOME (Prioritize Java 21 / 17 LTS for Gradle compatibility)
const javaCandidates = [
  path.join(os.homedir(), '.jdks', 'jbr-21.0.11'),
  'C:\\Program Files\\Java\\jdk-21',
  'C:\\Program Files\\Java\\jdk-17',
  'C:\\Program Files\\Android\\Android Studio\\jbr',
  'E:\\Android\\jbr',
  path.join(os.homedir(), 'AppData', 'Local', 'Programs', 'Android Studio', 'jbr'),
]
for (const p of javaCandidates) {
  if (fs.existsSync(p)) {
    env.JAVA_HOME = p
    break
  }
}

// 2. Setup ANDROID_HOME
if (!env.ANDROID_HOME || !fs.existsSync(env.ANDROID_HOME)) {
  const androidCandidates = [
    path.join(os.homedir(), 'AppData', 'Local', 'Android', 'Sdk'),
    'C:\\Android\\Sdk',
    'E:\\Android\\Sdk',
  ]
  for (const p of androidCandidates) {
    if (fs.existsSync(p)) {
      env.ANDROID_HOME = p
      env.ANDROID_SDK_ROOT = p
      break
    }
  }
}

// 3. Setup NDK_HOME
if ((!env.NDK_HOME || !fs.existsSync(env.NDK_HOME)) && env.ANDROID_HOME) {
  const ndkRoot = path.join(env.ANDROID_HOME, 'ndk')
  if (fs.existsSync(ndkRoot)) {
    const ndkVersions = fs.readdirSync(ndkRoot).filter(d => fs.existsSync(path.join(ndkRoot, d, 'source.properties')))
    if (ndkVersions.length > 0) {
      env.NDK_HOME = path.join(ndkRoot, ndkVersions[ndkVersions.length - 1])
      env.ANDROID_NDK_ROOT = env.NDK_HOME
    }
  }
}

// 4. Safely augment System PATH on all platforms
const pathKeys = Object.keys(process.env).filter(k => k.toLowerCase() === 'path')
const nodeDir = path.dirname(process.execPath)
const extraPaths = []

if (env.JAVA_HOME) {
  extraPaths.push(path.join(env.JAVA_HOME, 'bin'))
}
if (env.ANDROID_HOME) {
  extraPaths.push(path.join(env.ANDROID_HOME, 'platform-tools'))
  extraPaths.push(path.join(env.ANDROID_HOME, 'cmdline-tools', 'latest', 'bin'))
}
if (env.NDK_HOME) {
  const llvmBin = path.join(env.NDK_HOME, 'toolchains', 'llvm', 'prebuilt', 'windows-x86_64', 'bin')
  if (fs.existsSync(llvmBin)) {
    extraPaths.push(llvmBin)
  }
}
extraPaths.push(nodeDir)
extraPaths.push(path.join(process.cwd(), 'node_modules', '.bin'))

const sep = isWindows ? ';' : ':'
for (const key of (pathKeys.length > 0 ? pathKeys : ['PATH', 'Path'])) {
  const existing = process.env[key] || ''
  env[key] = `${extraPaths.join(sep)}${sep}${existing}`
}

// In-process environment application
for (const [k, v] of Object.entries(env)) {
  process.env[k] = v
}

const args = process.argv.slice(2)
console.log(`[KVIE Android Engine] JAVA_HOME: ${process.env.JAVA_HOME}`)
console.log(`[KVIE Android Engine] ANDROID_HOME: ${process.env.ANDROID_HOME}`)
console.log(`[KVIE Android Engine] NDK_HOME: ${process.env.NDK_HOME}`)
console.log(`[KVIE Android Engine] Executing Tauri Android: ${args.join(' ')}\n`)

const { run, logError } = require('@tauri-apps/cli/main.js')

try {
  await run(['android', ...args], 'tauri')
} catch (err) {
  if (err && typeof err === 'object' && err.message) {
    console.error('[KVIE Android Engine Error]:', err.message)
  } else {
    try {
      if (logError) logError(String(err?.message || err))
      else console.error(err)
    } catch {
      console.error(err)
    }
  }
  process.exit(1)
}
