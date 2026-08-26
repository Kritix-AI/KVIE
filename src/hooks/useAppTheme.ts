import { useEffect, useState } from 'react'

export interface ThemePreset {
  id: string
  name: string
  color: string
  glow: string
}

export const THEME_PRESETS: ThemePreset[] = [
  { id: 'cyan', name: 'Cyan (KVIE Blue)', color: '#22d3ee', glow: 'rgba(34, 211, 238, 0.4)' },
  { id: 'green', name: 'Green (Default Lime)', color: '#c7f36b', glow: 'rgba(199, 243, 107, 0.4)' },
  { id: 'pink', name: 'Pink (Neon Pink)', color: '#ec4899', glow: 'rgba(236, 72, 153, 0.4)' },
  { id: 'red', name: 'Red (Crimson Red)', color: '#ef4444', glow: 'rgba(239, 68, 68, 0.4)' },
  { id: 'purple', name: 'Purple (Deep Violet)', color: '#a855f7', glow: 'rgba(168, 85, 247, 0.4)' },
  { id: 'yellow', name: 'Yellow (Electric Gold)', color: '#eab308', glow: 'rgba(234, 179, 8, 0.4)' },
  { id: 'orange', name: 'Orange (Vibrant Amber)', color: '#f97316', glow: 'rgba(249, 115, 22, 0.4)' },
]

function hexToRgba(hex: string, alpha = 0.4): string {
  let cleanHex = hex.replace('#', '')
  if (cleanHex.length === 3) {
    cleanHex = cleanHex.split('').map(c => c + c).join('')
  }
  const r = parseInt(cleanHex.substring(0, 2), 16) || 34
  const g = parseInt(cleanHex.substring(2, 4), 16) || 211
  const b = parseInt(cleanHex.substring(4, 6), 16) || 238
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

export const useAppTheme = () => {
  const [accentColor, setAccentColor] = useState<string>(() => {
    const saved = localStorage.getItem('kvie_theme_accent_color')
    return saved || '#22d3ee'
  })

  const [activePresetId, setActivePresetId] = useState<string>(() => {
    const saved = localStorage.getItem('kvie_theme_preset_id')
    return saved || 'cyan'
  })

  const applyThemeColor = (color: string, presetId = 'custom') => {
    setAccentColor(color)
    setActivePresetId(presetId)
    localStorage.setItem('kvie_theme_accent_color', color)
    localStorage.setItem('kvie_theme_preset_id', presetId)

    const glowRgba = hexToRgba(color, 0.4)
    const subtleRgba = hexToRgba(color, 0.15)

    document.documentElement.style.setProperty('--accent-color', color)
    document.documentElement.style.setProperty('--accent-glow', glowRgba)
    document.documentElement.style.setProperty('--accent-subtle', subtleRgba)
  }

  useEffect(() => {
    applyThemeColor(accentColor, activePresetId)

    // Synchronize theme across multiple Tauri windows / localStorage updates
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'kvie_theme_accent_color' && e.newValue) {
        applyThemeColor(e.newValue, localStorage.getItem('kvie_theme_preset_id') || 'custom')
      }
    }

    const interval = setInterval(() => {
      const currentSaved = localStorage.getItem('kvie_theme_accent_color')
      if (currentSaved && currentSaved !== accentColor) {
        applyThemeColor(currentSaved, localStorage.getItem('kvie_theme_preset_id') || 'custom')
      }
    }, 400)

    window.addEventListener('storage', handleStorageChange)
    return () => {
      window.removeEventListener('storage', handleStorageChange)
      clearInterval(interval)
    }
  }, [accentColor])

  const selectPreset = (preset: ThemePreset) => {
    applyThemeColor(preset.color, preset.id)
  }

  const setCustomColor = (color: string) => {
    applyThemeColor(color, 'custom')
  }

  return {
    accentColor,
    activePresetId,
    selectPreset,
    setCustomColor,
    presets: THEME_PRESETS,
  }
}
