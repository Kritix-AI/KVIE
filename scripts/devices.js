import { execSync } from 'child_process'
import path from 'path'
import os from 'os'
import fs from 'fs'

const adbPath = path.join(os.homedir(), 'AppData', 'Local', 'Android', 'Sdk', 'platform-tools', 'adb.exe')

if (!fs.existsSync(adbPath)) {
  console.log('[KVIE] ADB not found at default location.')
  process.exit(1)
}

try {
  const out = execSync(`"${adbPath}" devices -l`, { encoding: 'utf8' })
  console.log('\n📱 Connected Android Devices:\n' + out)
} catch (err) {
  console.error(err)
}
