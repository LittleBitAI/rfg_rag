import { useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const VERDICTS = { ok: 'OK', partly_wrong: '일부 틀림', wrong: '틀림' }
const TYPES = { table: '표', diagram: '도식', text: '텍스트' }
const markdownComponents = { img: () => null }

export default function Review() {
  const [cards, setCards] = useState(null)
  const [filters, setFilters] = useState({ document: '', type: '', engine: '', verdict: '' })
  const [index, setIndex] = useState(0)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const saving = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    fetch('/ocr-api/review', { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error('저장된 OCR 결과를 읽지 못했습니다. 실행 창과 데이터 파일을 확인하세요.')
        setCards(await res.json())
      })
      .catch((err) => { if (!controller.signal.aborted) setError(err.message) })
    return () => controller.abort()
  }, [])

  const filtered = (cards ?? []).filter((card) =>
    (!filters.document || card.occurrences.some((o) => o.document_sha256 === filters.document)) &&
    (!filters.type || card.image_type === filters.type) &&
    (!filters.engine || card.engine === filters.engine) &&
    (!filters.verdict || (card.verdict ?? 'unreviewed') === filters.verdict))
  const position = Math.min(index, Math.max(0, filtered.length - 1))
  const card = filtered[position]

  useEffect(() => {
    function onKey(event) {
      if (pending || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey ||
          event.target.closest('select, input, textarea, [contenteditable="true"]')) return
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault()
        setIndex(Math.max(0, Math.min(filtered.length - 1, position + (event.key === 'ArrowLeft' ? -1 : 1))))
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [filtered.length, position, pending])

  function filter(name, value) {
    setFilters((current) => ({ ...current, [name]: value }))
    setIndex(0)
    setError('')
  }

  async function save(verdict) {
    if (saving.current) return
    saving.current = true
    setPending(true)
    setError('')
    try {
      const res = await fetch('/ocr-api/review/verdicts', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_sha256: card.image_sha256, verdict }),
      })
      if (!res.ok) throw new Error('판정을 저장하지 못했습니다. 다시 눌러 주세요.')
      const saved = await res.json()
      setCards((current) => current.map((c) => c.image_sha256 === saved.image_sha256 ? { ...c, ...saved } : c))
      setIndex(position)
    } catch (err) {
      setError(err.message)
    } finally {
      saving.current = false
      setPending(false)
    }
  }

  const documents = [...new Map((cards ?? []).flatMap((c) =>
    c.occurrences.map((o) => [o.document_sha256, o.source])))]
    .sort((a, b) => a[1].localeCompare(b[1], 'ko'))

  return <>
    <header className="bar"><div className="bar-inner">
      <span>OCR 결과 검토</span>
      <span className="meta">검토 {cards?.filter((c) => c.verdict).length ?? 0} / {cards?.length ?? 0}</span>
      <a className="ghost" href="/">질문 화면</a>
    </div></header>
    <main className="page review-page">
      <p className="lead meta">원본과 저장된 전사를 비교하고 판정을 누르세요. 누르는 즉시 저장됩니다. ← → 키로 이동합니다.</p>
      <fieldset className="review-filters" disabled={pending}>
        <legend className="label">필터</legend>
        <Filter label="문서" value={filters.document} onChange={(v) => filter('document', v)} options={documents} />
        <Filter label="이미지 유형" value={filters.type} onChange={(v) => filter('type', v)}
          options={[...new Set((cards ?? []).map((c) => c.image_type))].sort().map((t) => [t, TYPES[t] ?? t])} />
        <Filter label="엔진" value={filters.engine} onChange={(v) => filter('engine', v)}
          options={[...new Set((cards ?? []).map((c) => c.engine))].sort().map((e) => [e, e])} />
        <Filter label="판정 상태" value={filters.verdict} onChange={(v) => filter('verdict', v)}
          options={[[ 'unreviewed', '미검토' ], ...Object.entries(VERDICTS)]} />
      </fieldset>
      <nav className="review-navigation" aria-label="그림 이동">
        <button className="ghost" disabled={pending || !card || position === 0} onClick={() => setIndex(position - 1)}>이전</button>
        <span className="meta" aria-live="polite">{card ? position + 1 : 0} / {filtered.length}</span>
        <button className="ghost" disabled={pending || !card || position === filtered.length - 1} onClick={() => setIndex(position + 1)}>다음</button>
      </nav>
      {error && <p className="error" role="alert">{error}</p>}
      {!cards && !error && <p role="status">OCR 결과를 읽는 중…</p>}
      {cards && !card && <p>조건에 맞는 그림이 없습니다.</p>}
      {card && <article className="review-card" data-image-sha256={card.image_sha256}>
        <section className="review-image" aria-label="원본 이미지">
          <h1 className="label">원본 이미지</h1>
          <img key={card.file} src={'/ocr-api/files/' + card.file.split('/').map(encodeURIComponent).join('/')}
            alt={`${TYPES[card.image_type] ?? card.image_type} 원본`} />
        </section>
        <section className="review-result" aria-label="저장된 전사">
          <h2 className="label">저장된 전사</h2>
          <p className="meta">엔진: {card.engine} · 이미지 유형: {TYPES[card.image_type] ?? card.image_type}</p>
          <div className="review-markdown">
            <Markdown remarkPlugins={[remarkGfm]} skipHtml components={markdownComponents}>{card.text}</Markdown>
          </div>
          <h2 className="label">등장 위치 ({card.occurrences.length})</h2>
          <ul className="review-places meta">{card.occurrences.map((o, i) => <li key={i}>
            {o.source} · {o.format === 'pdf' ? `PDF ${o.page}쪽` :
              `${o.image_name} · 표시 위치: ${o.marker_start ?? '본문 표시 없음'}`}
          </li>)}</ul>
          <div className="choices" aria-label="전사 판정" aria-busy={pending}>
            {Object.entries(VERDICTS).map(([value, label]) =>
              <button key={value} aria-pressed={card.verdict === value} disabled={pending} onClick={() => save(value)}>{label}</button>)}
          </div>
          <p className="meta review-status" role="status">{pending ? '저장 중…' : card.verdict ?
            `${VERDICTS[card.verdict]} · 저장됨 (${card.reviewed_at})` : '미검토'}</p>
        </section>
      </article>}
    </main>
  </>
}

function Filter({ label, value, onChange, options }) {
  return <label className="meta">{label}
    <select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="">전체</option>
      {options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}
    </select>
  </label>
}
