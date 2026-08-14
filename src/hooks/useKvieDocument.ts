import { useCallback, useEffect, useRef, useState } from 'react'
import { DocumentEdit, DocumentSnapshot, tauriBridge } from '../lib/tauriBridge'

const emptySnapshot: DocumentSnapshot = { text: '', cursor: 0, version: 0, can_undo: false, can_redo: false }

export const useKvieDocument = () => {
  const [snapshot, setSnapshot] = useState<DocumentSnapshot>(emptySnapshot)
  const [error, setError] = useState<string | null>(null)
  const [isDesktop, setIsDesktop] = useState(false)
  const tauriAvailableRef = useRef(false)
  const browserUndoRef = useRef<string[]>([])
  const browserRedoRef = useRef<string[]>([])

  useEffect(() => {
    let mounted = true
    tauriBridge.getDocument().then(value => {
      if (mounted) { tauriAvailableRef.current = true; setIsDesktop(true); setSnapshot(value) }
    }).catch(() => { /* browser fallback uses local state */ })
    return () => { mounted = false }
  }, [])

  const apply = useCallback(async (edit: DocumentEdit) => {
    setError(null)
    if (tauriAvailableRef.current) {
      try { setSnapshot(await tauriBridge.apply(edit)); return }
      catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); return }
    }
    setSnapshot(current => {
      const currentBefore = current.text
      let text = currentBefore
      let cursor = current.cursor
      if (edit.action === 'append') {
        text = `${currentBefore && !/[\s\n]$/.test(currentBefore) ? `${currentBefore} ` : currentBefore}${(edit.text || '').trim()}`
        cursor = text.length
      } else if (edit.action === 'insert') {
        const position = Math.min(edit.start ?? current.cursor, currentBefore.length)
        text = `${currentBefore.slice(0, position)}${edit.text || ''}${currentBefore.slice(position)}`
        cursor = position + (edit.text || '').length
      } else if (edit.action === 'replace') {
        const start = Math.max(0, Math.min(edit.start ?? 0, currentBefore.length))
        const end = Math.max(start, Math.min(edit.end ?? start, currentBefore.length))
        text = `${currentBefore.slice(0, start)}${edit.text || ''}${currentBefore.slice(end)}`
        cursor = start + (edit.text || '').length
      } else if (edit.action === 'clear') { text = ''; cursor = 0 }
      if (text !== currentBefore) { browserUndoRef.current.push(currentBefore); browserRedoRef.current = [] }
      return { text, cursor, version: current.version + (text === currentBefore ? 0 : 1), can_undo: text !== currentBefore || current.can_undo, can_redo: false }
    })
  }, [])

  const undo = useCallback(async () => {
    if (tauriAvailableRef.current) { try { setSnapshot(await tauriBridge.undo()); return } catch (cause) { setError(String(cause)); return } }
    const previous = browserUndoRef.current.pop()
    if (previous === undefined) return
    setSnapshot(current => { browserRedoRef.current.push(current.text); return { ...current, text: previous, cursor: previous.length, version: current.version + 1, can_undo: browserUndoRef.current.length > 0, can_redo: true } })
  }, [])
  const redo = useCallback(async () => {
    if (tauriAvailableRef.current) { try { setSnapshot(await tauriBridge.redo()); return } catch (cause) { setError(String(cause)); return } }
    const next = browserRedoRef.current.pop()
    if (next === undefined) return
    setSnapshot(current => { browserUndoRef.current.push(current.text); return { ...current, text: next, cursor: next.length, version: current.version + 1, can_undo: true, can_redo: browserRedoRef.current.length > 0 } })
  }, [])

  return { ...snapshot, error, apply, undo, redo, isDesktop }
}
