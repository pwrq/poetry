import { useRef, useEffect } from 'react'
import { useContestStore } from '../hooks/useContestStore'
import { FeedBubble } from './FeedBubble'
import type { AgentMessage } from '../types'

/** Split a message into multiple if it contains 2+ @mention-led paragraphs. */
function expand(msg: AgentMessage): { key: string; msg: AgentMessage }[] {
  const paragraphs = msg.content.split(/\n\n+/).map((p) => p.trim()).filter(Boolean)
  const mentionCount = paragraphs.filter((p) => /^@\w+/.test(p)).length
  if (mentionCount < 2) return [{ key: String(msg.slot), msg }]
  return paragraphs.map((part, i) => ({
    key: `${msg.slot}-${i}`,
    msg: { ...msg, content: part },
  }))
}

export function MessageFeed() {
  const messages = useContestStore((s) => s.messages)
  const feedRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = feedRef.current
    if (!el) return
    // Only auto-scroll if already near the bottom (120px tolerance)
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120
    if (isNearBottom) el.scrollTop = el.scrollHeight
  }, [messages.length])

  const visible = messages
    .slice()
    .sort((a, b) => a.slot - b.slot)

  return (
    <div ref={feedRef} className="message-feed">
      {visible.flatMap((msg) =>
        expand(msg).map(({ key, msg: m }) => <FeedBubble key={key} message={m} />)
      )}
    </div>
  )
}
