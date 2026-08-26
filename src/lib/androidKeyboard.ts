import { invoke } from '@tauri-apps/api/core'

declare global {
  interface Window {
    AndroidKeyboardBridge?: {
      isAndroid?: () => boolean
      openKeyboardSettings?: () => void
      showKeyboardPicker?: () => void
      requestMicPermission?: () => void
      isMicPermissionGranted?: () => boolean
      isKeyboardEnabled?: () => boolean
    }
  }
}

export const isAndroid = (): boolean => {
  if (typeof window === 'undefined') return false
  if (window.AndroidKeyboardBridge?.isAndroid?.()) return true
  return /android/i.test(navigator.userAgent)
}

export const openAndroidKeyboardSettings = async (): Promise<void> => {
  // 1. Try Android Native Bridge
  if (window.AndroidKeyboardBridge?.openKeyboardSettings) {
    try {
      window.AndroidKeyboardBridge.openKeyboardSettings()
      return
    } catch (e) {
      console.warn('AndroidKeyboardBridge.openKeyboardSettings failed', e)
    }
  }

  // 2. Try Tauri IPC Invoke
  try {
    await invoke('open_android_keyboard_settings')
    return
  } catch {}

  // 3. Fallback to Android Intent URL
  try {
    window.location.href = 'intent:#Intent;action=android.settings.INPUT_METHOD_SETTINGS;end'
  } catch (err) {
    console.error('Failed to open keyboard settings via intent', err)
  }
}

export const showAndroidKeyboardPicker = async (): Promise<void> => {
  // 1. Try Android Native Bridge
  if (window.AndroidKeyboardBridge?.showKeyboardPicker) {
    try {
      window.AndroidKeyboardBridge.showKeyboardPicker()
      return
    } catch (e) {
      console.warn('AndroidKeyboardBridge.showKeyboardPicker failed', e)
    }
  }

  // 2. Try Tauri IPC Invoke
  try {
    await invoke('show_android_keyboard_picker')
    return
  } catch {}
}

export const requestAndroidMicPermission = async (): Promise<void> => {
  if (window.AndroidKeyboardBridge?.requestMicPermission) {
    try {
      window.AndroidKeyboardBridge.requestMicPermission()
      return
    } catch (e) {
      console.warn('AndroidKeyboardBridge.requestMicPermission failed', e)
    }
  }

  try {
    await invoke('request_android_mic_permission')
    return
  } catch {}

  navigator.mediaDevices?.getUserMedia?.({ audio: true }).catch(() => {})
}

export const isAndroidKeyboardEnabled = (): boolean => {
  try {
    return window.AndroidKeyboardBridge?.isKeyboardEnabled?.() ?? false
  } catch {
    return false
  }
}
