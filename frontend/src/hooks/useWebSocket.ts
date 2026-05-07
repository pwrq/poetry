import { useEffect, useRef, useCallback } from 'react'
import { useContestStore } from './useContestStore'
import type { ServerMessage, ClientMessage, AgentMessage, ScoresPayload, FinalResults } from '../types'

const WS_URL = `ws://${window.location.hostname}:8001/ws`

type QueueItem =
  | { kind: 'agent_message'; data: AgentMessage }
  | { kind: 'scores'; data: ScoresPayload }
  | { kind: 'final_results'; data: FinalResults }

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Client-side message pace queue (agent_message + scores + final_results)
  const msgQueue = useRef<QueueItem[]>([])
  const processing = useRef(false)
  const paceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  function processQueue() {
    if (msgQueue.current.length === 0) {
      processing.current = false
      return
    }
    processing.current = true
    const item = msgQueue.current.shift()!
    const s = useContestStore.getState()
    switch (item.kind) {
      case 'agent_message':
        s.addMessage(item.data)
        break
      case 'scores':
        s.setScores(item.data.round_number, item.data.scores, item.data.cumulative)
        break
      case 'final_results':
        s.setFinalResults(item.data)
        break
    }
    const delay = useContestStore.getState().messageDelay
    paceTimer.current = setTimeout(processQueue, delay)
  }

  function enqueue(item: QueueItem) {
    msgQueue.current.push(item)
    if (!processing.current) processQueue()
  }

  function flushQueue() {
    if (paceTimer.current) clearTimeout(paceTimer.current)
    msgQueue.current = []
    processing.current = false
  }

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      useContestStore.getState().setConnected(true)
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current)
        reconnectTimer.current = null
      }
      if (useContestStore.getState().models.length === 0) {
        fetch(`http://${window.location.hostname}:8001/api/models`)
          .then((r) => r.json())
          .then((d) => useContestStore.getState().setModels(d.models))
          .catch(() => {})
      }
    }

    ws.onclose = () => {
      useContestStore.getState().setConnected(false)
      reconnectTimer.current = setTimeout(connect, 3000)
    }

    ws.onerror = () => {
      ws.close()
    }

    ws.onmessage = (event: MessageEvent) => {
      const msg: ServerMessage = JSON.parse(event.data)
      const s = useContestStore.getState()
      switch (msg.type) {
        case 'agent_message':
          enqueue({ kind: 'agent_message', data: msg.data })
          break
        case 'state_update':
          // Phase/round changes are always immediate — needed for UI routing
          s.updateContestState(msg.data)
          break
        case 'scores':
          // Queue alongside agent_messages so scores appear after the messages that produced them
          enqueue({ kind: 'scores', data: msg.data })
          break
        case 'final_results':
          enqueue({ kind: 'final_results', data: msg.data })
          break
        case 'config_sync':
          s.updateAgentConfig(msg.data.id, msg.data)
          break
        case 'history_sync':
          // Clear queue on reset, then replay history instantly
          flushQueue()
          s.setHistory(msg.data)
          break
        case 'error':
          s.setServerError(msg.data.message)
          break
      }
    }
  }, []) // stable

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      if (paceTimer.current) clearTimeout(paceTimer.current)
      wsRef.current?.close()
    }
  }, [connect])

  const send = useCallback((msg: ClientMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg))
    }
  }, [])

  return { send }
}
