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

export const openAndroidKeyboardSettings = (): void => {
  if (window.AndroidKeyboardBridge?.openKeyboardSettings) {
    window.AndroidKeyboardBridge.openKeyboardSettings()
  } else {
    console.warn('AndroidKeyboardBridge not available')
  }
}

export const showAndroidKeyboardPicker = (): void => {
  if (window.AndroidKeyboardBridge?.showKeyboardPicker) {
    window.AndroidKeyboardBridge.showKeyboardPicker()
  } else {
    console.warn('AndroidKeyboardBridge not available')
  }
}

export const requestAndroidMicPermission = (): void => {
  if (window.AndroidKeyboardBridge?.requestMicPermission) {
    window.AndroidKeyboardBridge.requestMicPermission()
  } else {
    navigator.mediaDevices?.getUserMedia?.({ audio: true }).catch(() => {})
  }
}

export const isAndroidKeyboardEnabled = (): boolean => {
  try {
    return window.AndroidKeyboardBridge?.isKeyboardEnabled?.() ?? false
  } catch {
    return false
  }
}
