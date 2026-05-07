interface Props {
  text: string
}

export function MentionHighlight({ text }: Props) {
  const parts = text.split(/(@\w[\w.]*)/g)
  return (
    <>
      {parts.map((part, i) =>
        part.startsWith('@') ? (
          <span key={i} className="mention">{part}</span>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </>
  )
}
