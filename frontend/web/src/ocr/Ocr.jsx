import { useEffect, useState } from 'react'

const LABELS = [
  { value: 1, text: '1 꼭 인식' },
  { value: 2, text: '2 어려움' },
  { value: 3, text: '3 불필요' },
]

export default function Ocr() {
  // 카드: 그림이 나온 위치 하나 — images.jsonl 의 그림 정보 + key · occurrence · label · craft (없으면 null)
  const [cards, setCards] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/ocr-api/images')
      .then(async (res) => (res.ok ? setCards(await res.json()) : setError(await errorText(res))))
      .catch(() => setError(UNREACHABLE))
  }, [])

  // 누르는 즉시 바꿔 보이고, 저장에 실패하면 원래 라벨로 되돌린다.
  // 저장하는 동안 그 카드의 버튼을 막아 두어 한 위치의 라벨이 누른 순서대로 파일에 쌓인다
  async function label(key, value) {
    const before = cards.find((c) => c.key === key).label
    const patch = (fields) => setCards((cs) => cs.map((c) => (c.key === key ? { ...c, ...fields } : c)))
    patch({ label: value, error: null, saving: true })
    const res = await fetch('/ocr-api/labels', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, label: value }),
    }).catch(() => null)
    if (res?.ok) patch({ saving: false })
    else patch({ label: before, error: res ? await errorText(res) : UNREACHABLE, saving: false })
  }

  const done = cards?.filter((c) => c.label !== null).length ?? 0
  return (
    <>
      <header className="bar">
        <div className="bar-inner">
          <span>OCR 이미지 라벨링</span>
          {cards && <span className="meta">라벨 {done} / {cards.length}</span>}
        </div>
      </header>
      <main className="page">
        <p className="meta lead">1 꼭 인식해야 함 · 2 인식해야 하나 어려움 · 3 인식할 필요 없음. 누르는 즉시 저장됩니다.</p>
        {error && <p className="error">{error}</p>}
        {!cards && !error && <p className="meta lead">그림 목록을 읽는 중…</p>}
        <div className="grid">
          {cards?.map((card) => <Card key={card.key} card={card} onLabel={label} />)}
        </div>
      </main>
    </>
  )
}

function Card({ card, onLabel }) {
  const name = card.file.split('/').at(-1)
  const o = card.occurrence
  return (
    <article className="card">
      {card.viewable ? (
        <img className="preview" src={fileUrl(card.file)} alt={name} loading="lazy" />
      ) : (
        <div className="preview placeholder">
          <span className="label">미리보기 없음 · {name.split('.').at(-1).toUpperCase()}</span>
          <span>{card.reason}</span>
        </div>
      )}
      <p className="label">{o.source}</p>
      <p className="meta where">{where(o)}</p>
      {card.craft && <p className="badges"><span className="badge">CRAFT {card.craft}</span></p>}
      <div className="choices">
        {LABELS.map((l) => (
          <button key={l.value} aria-pressed={card.label === l.value} disabled={card.saving} onClick={() => onLabel(card.key, l.value)}>
            {l.text}
          </button>
        ))}
      </div>
      {card.error && <p className="error">{card.error}</p>}
    </article>
  )
}

function where(o) {
  if (o.format === 'pdf') return `p.${o.page} · ${o.image_index + 1}번째 그림`
  // marker_start 가 null 이면 문서에 들어 있지만 본문에 표시가 없는 그림 — 01 전처리가 보지 않는다
  return o.marker_start === null ? `${o.image_name} · 본문 표시 없음` : o.image_name
}

// doc_id 에 한글 · 괄호가 있어 경로 조각마다 인코딩한다
function fileUrl(file) {
  return '/ocr-api/files/' + file.split('/').map(encodeURIComponent).join('/')
}

const UNREACHABLE = '서버에 연결할 수 없습니다. 실행 창(frontend/start.cmd · start.command)이 닫혔다면 다시 실행하세요.'

async function errorText(res) {
  // Vite 프록시는 API 서버에 닿지 못하면 502 를 돌려준다
  if (res.status === 502) return 'API 서버가 아직 준비되지 않았습니다. 잠시 뒤 새로고침하세요.'
  const body = await res.json().catch(() => ({}))
  return typeof body.detail === 'string' ? body.detail : `API 서버 오류 (${res.status}). 실행 창의 로그를 확인하세요.`
}
