import { useEffect, useState } from 'react'

const LABELS = [
  { value: 1, text: '1 꼭 인식' },
  { value: 2, text: '2 어려움' },
  { value: 3, text: '3 불필요' },
]

export default function Ocr() {
  // 카드: 그림이 나온 위치 하나 — images.jsonl 의 그림 정보 + key · occurrence · label · craft (없으면 null) · batch
  const [cards, setCards] = useState(null)
  const [error, setError] = useState(null)
  const [batch, setBatch] = useState(() => Number(new URLSearchParams(location.search).get('batch')) || null)
  // 크게 보는 그림: 이 묶음에서 미리보기가 있는 카드 중 몇 번째인지 (닫혀 있으면 null)
  const [zoom, setZoom] = useState(null)

  // StrictMode 는 개발 중 이 effect 를 두 번 돌린다. 물러난 실행의 늦은 응답이 그 사이 매긴 라벨을 덮지 않게 버린다
  useEffect(() => {
    let retired = false
    fetch('/ocr-api/images')
      .then(async (res) => {
        const body = res.ok ? await res.json() : await errorText(res)
        if (!retired) res.ok ? setCards(body) : setError(body)
      })
      .catch(() => retired || setError(UNREACHABLE))
    return () => { retired = true }
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

  // 맡은 묶음은 주소(?batch=N)에 두어 새로고침해도 그대로다
  function chooseBatch(n) {
    setBatch(n)
    setZoom(null)
    history.replaceState(null, '', `?batch=${n}`)
    window.scrollTo(0, 0)
  }

  const shown = cards?.filter((c) => c.batch === batch) ?? []
  const viewable = shown.filter((c) => c.viewable)
  // 내보내기는 서버에 저장된 라벨만 담으므로, 저장 중인 라벨은 진행 수에서 빼고 내보내기를 잠근다
  const saving = shown.filter((c) => c.saving).length
  const done = shown.filter((c) => c.label !== null && !c.saving).length
  return (
    <>
      <header className="bar">
        <div className="bar-inner">
          <span>OCR 이미지 라벨링</span>
          <div className="tools">
            <div className="batches" role="group" aria-label="묶음">
              {[1, 2, 3, 4, 5].map((n) => (
                <button key={n} aria-pressed={batch === n} onClick={() => chooseBatch(n)}>묶음 {n}</button>
              ))}
            </div>
            {batch && cards && <span className="meta">라벨 {done} / {shown.length}{saving > 0 && ` · 저장 중 ${saving}`}</span>}
            {batch && (saving > 0
              ? <button className="ghost" disabled>결과 내보내기</button>
              : <a className="ghost" href={`/ocr-api/export?batch=${batch}`}>결과 내보내기</a>)}
          </div>
        </div>
      </header>
      <main className="page">
        <p className="meta lead">
          {batch ? '1 꼭 인식해야 함 · 2 인식해야 하나 어려움 · 3 인식할 필요 없음. 누르는 즉시 저장됩니다. 다 매기면 결과 내보내기로 받은 파일을 전달하세요.'
            : '위에서 맡은 묶음을 고르세요. 다섯 묶음을 한 사람씩 나눠 매기고, 각자 내보낸 결과를 합칩니다.'}
        </p>
        {error && <p className="error">{error}</p>}
        {!cards && !error && <p className="meta lead">그림 목록을 읽는 중…</p>}
        <div className="grid">
          {shown.map((card) => <Card key={card.key} card={card} onLabel={label} onZoom={() => setZoom(viewable.indexOf(card))} />)}
        </div>
      </main>
      {zoom !== null && <Zoom cards={viewable} at={zoom} setAt={setZoom} />}
    </>
  )
}

function Card({ card, onLabel, onZoom }) {
  const name = card.file.split('/').at(-1)
  const o = card.occurrence
  return (
    <article className="card">
      {card.viewable ? (
        <button className="zoom-open" aria-label={`${name} 크게 보기`} onClick={onZoom}>
          <img className="preview" src={fileUrl(card.file)} alt={name} loading="lazy" />
        </button>
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

// 크게 보기: 바깥을 누르거나 Esc 로 닫고, ◀ ▶ · ← → 로 이 묶음의 앞뒤 그림으로 간다.
// 끝에서 돌아 들어가지 않고 그쪽 화살표를 감춰, 묶음 끝에 닿았음을 보인다
function Zoom({ cards, at, setAt }) {
  const card = cards[at]
  const hasPrev = at > 0
  const hasNext = at < cards.length - 1
  useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape') setAt(null)
      if (e.key === 'ArrowLeft' && hasPrev) setAt(at - 1)
      if (e.key === 'ArrowRight' && hasNext) setAt(at + 1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [at, hasPrev, hasNext, setAt])
  // --ratio 는 그림 비율 — CSS 가 창 너비 · 높이 중 먼저 닿는 쪽까지 키운다 (작은 그림도 크게)
  return (
    <div className="zoom" onClick={(e) => e.target === e.currentTarget && setAt(null)}>
      {hasPrev && <button className="step prev" aria-label="이전 그림" onClick={() => setAt(at - 1)}>◀</button>}
      <img key={card.key} src={fileUrl(card.file)} alt={card.file.split('/').at(-1)}
        onLoad={(e) => e.target.style.setProperty('--ratio', e.target.naturalWidth / e.target.naturalHeight)} />
      <p className="label caption">{card.occurrence.source} · {where(card.occurrence)}</p>
      {hasNext && <button className="step next" aria-label="다음 그림" onClick={() => setAt(at + 1)}>▶</button>}
    </div>
  )
}

function where(o) {
  if (o.format === 'pdf') return `p.${o.page} · ${o.image_index + 1}번째 그림`
  // marker_start 가 null 이면 문서에 들어 있지만 본문에 표시가 없는 그림 — 01 전처리가 보지 않는다
  return o.marker_start === null ? `${o.image_name} · 본문 표시 없음` : o.image_name
}

function fileUrl(file) {
  return '/ocr-api/files/' + encodeURIComponent(file)
}

const UNREACHABLE = '서버에 연결할 수 없습니다. 실행 창(frontend/start.cmd · start.command)이 닫혔다면 다시 실행하세요.'

async function errorText(res) {
  // Vite 프록시는 API 서버에 닿지 못하면 502 를 돌려준다
  if (res.status === 502) return 'API 서버가 아직 준비되지 않았습니다. 잠시 뒤 새로고침하세요.'
  const body = await res.json().catch(() => ({}))
  return typeof body.detail === 'string' ? body.detail : `API 서버 오류 (${res.status}). 실행 창의 로그를 확인하세요.`
}
