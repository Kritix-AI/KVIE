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
      console.warn('AndroidKeyboardBridge failed', e)
    }
  }

  try {
    const iframe = document.createElement('iframe')
    iframe.style.display = 'none'
    iframe.src = 'kvie-action://open-keyboard-settings'
    document.body.appendChild(iframe)
    setTimeout(() => document.body.removeChild(iframe), 1000)
  } catch (err) {
    console.error('Failed to trigger action', err)
  }
}

export const showAndroidKeyboardPicker = (): void => {
  if (window.AndroidKeyboardBridge?.showKeyboardPicker) {
    try {
      window.AndroidKeyboardBridge.showKeyboardPicker()
      return
    } catch (e) {
      console.warn('AndroidKeyboardBridge failed', e)
    }
  }

  try {
    const iframe = document.createElement('iframe')
    iframe.style.display = 'none'
    iframe.src = 'kvie-action://show-keyboard-picker'
    document.body.appendChild(iframe)
    setTimeout(() => document.body.removeChild(iframe), 1000)
  } catch (err) {
    console.error('Failed to trigger action', err)
  }
}

export const requestAndroidMicPermission = (): void => {
  if (window.AndroidKeyboardBridge?.requestMicPermission) {
    try {
      window.AndroidKeyboardBridge.requestMicPermission()
      return
    } catch (e) {
      console.warn('AndroidKeyboardBridge failed', e)
    }
  }

  try {
    const iframe = document.createElement('iframe')
    iframe.style.display = 'none'
    iframe.src = 'kvie-action://request-mic'
    document.body.appendChild(iframe)
    setTimeout(() => document.body.removeChild(iframe), 1000)
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
