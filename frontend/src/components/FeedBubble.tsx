import { useState } from 'react'
import type { AgentMessage } from '../types'
import { useContestStore, roleColor } from '../hooks/useContestStore'
import { MentionHighlight } from './MentionHighlight'

const LONG_THRESHOLD = 300

/** Parse the leading @Address from content and return destination + body. */
function parseAddress(
  content: string,
  agentConfigs: Record<string, { id: string; name: string }>,
): { to: string; body: string } {
  const match = content.match(/^(@\w+)[\s\-—,;:.!?]*/)
  if (match) {
    const word = match[1].slice(1) // strip leading @
    const lower = word.toLowerCase()
    if (lower === 'all') return { to: 'All', body: content.slice(match[0].length) }
    // Resolve agent ID or name fragment → display name
    const found = Object.values(agentConfigs).find(
      (c) => c.id.toLowerCase() === lower || c.name.toLowerCase().includes(lower),
    )
    return { to: found ? found.name : word, body: content.slice(match[0].length) }
  }
  return { to: 'All', body: content }
}

export function FeedBubble({ message }: { message: AgentMessage }) {
  const [expanded, setExpanded] = useState(false)
  const agentConfigs = useContestStore((s) => s.agentConfigs)
  const accent = roleColor(message.agent_role)
  const { to: parsedTo, body } = parseAddress(message.content, agentConfigs)
  const isLong = body.length > LONG_THRESHOLD
  const isJudgesOnly = message.visibility === 'judges_only'
  const isOrganizerOnly = message.visibility === 'organizer_only'
  // Judge messages with visibility='all' are scorecard handovers to the scorekeeper
  const isHandover = message.agent_role === 'judge' && message.visibility === 'all'
  const to = isOrganizerOnly
    ? (agentConfigs['organizer']?.name ?? 'Romano')
    : parsedTo

  return (
    <div
      className={`feed-bubble${isJudgesOnly ? ' feed-bubble--judges-only' : ''}${isOrganizerOnly ? ' feed-bubble--organizer-only' : ''}${isHandover ? ' feed-bubble--handover' : ''}`}
      style={{ borderLeftColor: accent }}
    >
      <div className="feed-bubble__header">
        <span className="feed-bubble__from" style={{ color: accent }}>
          {message.agent_name}
        </span>
        <span className="feed-bubble__arrow">→</span>
        <span className="feed-bubble__to">{to}</span>
        {isJudgesOnly && (
          <span className="feed-bubble__judges-badge">🔒 judges only</span>
        )}
        {isOrganizerOnly && (
          <span className="feed-bubble__judges-badge">🔒 private</span>
        )}
        {isHandover && (
          <span className="feed-bubble__handover-badge">📋 scorecards</span>
        )}
        {message.timestamp && (
          <span className="feed-bubble__time">{message.timestamp}</span>
        )}
      </div>
      <div
        className={`feed-bubble__body${isLong && !expanded ? ' feed-bubble__body--collapsed' : ''}`}
      >
        <MentionHighlight text={body} />
      </div>
      {isLong && (
        <button className="bubble-expand" onClick={() => setExpanded((v) => !v)}>
          {expanded ? 'show less' : 'show more'}
        </button>
      )}
    </div>
  )
}
