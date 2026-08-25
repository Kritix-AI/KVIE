import { spawn } from 'child_process'
import path from 'path'
import os from 'os'
import fs from 'fs'

const isWindows = process.platform === 'win32'
const env = { ...process.env }

// 1. Setup JAVA_HOME
if (!env.JAVA_HOME || !fs.existsSync(env.JAVA_HOME)) {
  const javaCandidates = [
    'E:\\Android\\jbr',
    'C:\\Program Files\\Android\\Android Studio\\jbr',
    'C:\\Program Files\\Java\\jdk-21',
    'C:\\Program Files\\Java\\jdk-17',
    path.join(os.homedir(), 'AppData', 'Local', 'Programs', 'Android Studio', 'jbr'),
  ]
  for (const p of javaCandidates) {
    if (fs.existsSync(p)) {
      env.JAVA_HOME = p
      break
    }
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

// 4. Prepend Java binary to PATH
if (env.JAVA_HOME) {
  env.PATH = `${path.join(env.JAVA_HOME, 'bin')}${isWindows ? ';' : ':'}${env.PATH || ''}`
}

const args = process.argv.slice(2)
const tauriBin = isWindows ? 'npx.cmd' : 'npx'

console.log(`[KVIE Android Engine] JAVA_HOME: ${env.JAVA_HOME}`)
console.log(`[KVIE Android Engine] ANDROID_HOME: ${env.ANDROID_HOME}`)
console.log(`[KVIE Android Engine] NDK_HOME: ${env.NDK_HOME}`)
console.log(`[KVIE Android Engine] Executing: tauri android ${args.join(' ')}\n`)

const child = spawn(tauriBin, ['tauri', 'android', ...args], {
  env,
  stdio: 'inherit',
  shell: true,
})

child.on('exit', code => {
  process.exit(code || 0)
})
