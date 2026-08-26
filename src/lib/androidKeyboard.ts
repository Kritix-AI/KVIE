declare global {
  interface Window {
    AndroidKeyboardBridge?: {
      isAndroid?: () => boolean
      openKeyboardSettings?: () => void
      showKeyboardPicker?: () => void
      requestMicPermission?: () => void
      openSetupActivity?: () => void
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
    try {
      window.AndroidKeyboardBridge.openKeyboardSettings()
      return
    } catch (e) {
      console.warn('AndroidKeyboardBridge.openKeyboardSettings failed', e)
    }
  }

  if (window.AndroidKeyboardBridge?.openSetupActivity) {
    try {
      window.AndroidKeyboardBridge.openSetupActivity()
      return
    } catch (e) {
      console.warn('AndroidKeyboardBridge.openSetupActivity failed', e)
    }
  }

  console.warn('AndroidKeyboardBridge is not yet attached')
}

export const showAndroidKeyboardPicker = (): void => {
  if (window.AndroidKeyboardBridge?.showKeyboardPicker) {
    try {
      window.AndroidKeyboardBridge.showKeyboardPicker()
      return
    } catch (e) {
      console.warn('AndroidKeyboardBridge.showKeyboardPicker failed', e)
    }
  }

  console.warn('AndroidKeyboardBridge is not yet attached')
}

export const requestAndroidMicPermission = (): void => {
  if (window.AndroidKeyboardBridge?.requestMicPermission) {
    try {
      window.AndroidKeyboardBridge.requestMicPermission()
      return
    } catch (e) {
      console.warn('AndroidKeyboardBridge.requestMicPermission failed', e)
    }
  }

  navigator.mediaDevices?.getUserMedia?.({ audio: true }).catch(() => {})
}

export const isAndroidKeyboardEnabled = (): boolean => {
  try {
    return window.AndroidKeyboardBridge?.isKeyboardEnabled?.() ?? false
  } catch {
    return false
  }
}
