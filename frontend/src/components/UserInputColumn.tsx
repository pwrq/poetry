import { useRef, useState, useEffect } from 'react'
import { useContestStore } from '../hooks/useContestStore'
import type { ClientMessage } from '../types'

interface Props {
  send: (msg: ClientMessage) => void
}

export function UserInputColumn({ send }: Props) {
  const [text, setText] = useState('')
  const connected = useContestStore((s) => s.connected)
  const waitingForUser = useContestStore((s) => s.waitingForUser)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (waitingForUser) textareaRef.current?.focus()
  }, [waitingForUser])

  function handleSend() {
    const content = text.trim()
    if (!content || !connected) return
    send({ type: 'user_message', data: { content } })
    setText('')
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const placeholder = waitingForUser ? 'Type your reply…' : 'Message Romano…'

  return (
    <div
      className="user-input-bar"
      style={waitingForUser ? { borderTopColor: '#f59e0b' } : undefined}
    >
      <div className="user-input-area">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={!connected}
          style={waitingForUser ? { borderColor: '#f59e0b' } : undefined}
        />
        <button onClick={handleSend} disabled={!connected || !text.trim()}>
          Send
        </button>
      </div>
    </div>
  )
}
