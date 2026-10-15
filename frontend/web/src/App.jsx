import { useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export default function App() {
  // 대화 기록은 이 탭에만 있다. 턴: { question, answer?, sources?, contexts?, error? }
  const [turns, setTurns] = useState([])
  const [input, setInput] = useState('')
  // 출처 칸이 보여 주는 턴과 펼친 출처 번호. turn 이 null 이면 마지막 턴
  const [open, setOpen] = useState({ turn: null, n: null })
  const thread = useRef(0)
  const box = useRef(null)
  const last = turns.at(-1)
  const pending = last !== undefined && last.answer === undefined && last.error === undefined
  const shown = open.turn ?? turns.length - 1

  useEffect(() => {
    document.querySelector('.turn:last-of-type')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [turns.length])

  async function ask() {
    const question = input.trim()
    if (!question || pending) return
    const gen = thread.current
    const history = turns.filter((t) => t.answer !== undefined).map((t) => ({ question: t.question, answer: t.answer }))
    setTurns([...turns, { question }])
    setOpen({ turn: null, n: null })
    setInput('')
    const result = await postQuestion(question, history)
    // 새 스레드를 시작한 뒤 도착한 응답은 버린다
    if (gen !== thread.current) return
    setTurns((ts) => ts.map((t, i) => (i === ts.length - 1 ? { ...t, ...result } : t)))
    // 출처 칩을 누르느라 포커스가 옮겨 갔어도 바로 이어서 물을 수 있게
    box.current?.focus({ preventScroll: true })
  }

  function newThread() {
    thread.current += 1
    setTurns([])
    setOpen({ turn: null, n: null })
    setInput('')
  }

  function showSource(turn, n) {
    setOpen({ turn, n })
    // 넓은 화면에서는 출처 칸의 카드, 좁은 화면에서는 답변 위 카드 — 보이는 쪽으로 간다
    requestAnimationFrame(() => {
      const cards = document.querySelectorAll(`[data-src="${turn}-${n}"]`)
      ;[...cards].find((el) => el.offsetParent !== null)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    })
  }

  function toggleSource(turn, n) {
    if (shown === turn && open.n === n) setOpen({ turn, n: null })
    else showSource(turn, n)
  }

  if (turns.length === 0) {
    return (
      <main className="landing">
        <Settings />
        <h1>RFP 질의응답</h1>
        <p className="lead">공공기관 제안요청서에 대해 물어보세요. 답변의 번호를 누르면 근거 문단이 옆에 열립니다.</p>
        <AskBox value={input} onChange={setInput} onSubmit={ask} autoFocus
          placeholder="예: 고려대학교 차세대 포털 시스템 사업의 응답 시간 요구사항은?" />
      </main>
    )
  }

  const openIn = (i) => (shown === i ? open.n : null)
  return (
    <>
      <header className="bar">
        <div className="bar-inner">
          <span>RFP 질의응답</span>
          <button className="ghost" onClick={newThread}>새 스레드</button>
        </div>
      </header>
      <div className="layout">
        <main className="thread">
          {turns.map((turn, i) => (
            <Turn key={i} index={i} turn={turn} openN={openIn(i)}
              onCite={(n) => showSource(i, n)} onToggle={(n) => toggleSource(i, n)} />
          ))}
          <div className="dock">
            <AskBox ref={box} value={input} onChange={setInput} onSubmit={ask} disabled={pending} autoFocus
              placeholder={pending ? '답변을 기다리는 중…' : '이어서 질문하기'} />
          </div>
        </main>
        <aside className="pane" aria-label="출처">
          <SourcePane index={shown} turn={turns[shown]} openN={open.n} onToggle={(n) => toggleSource(shown, n)} />
        </aside>
      </div>
    </>
  )
}

// 첫 화면 오른쪽 위의 설정 메뉴 — 같은 Vite 서버의 다른 화면으로 옮겨 간다
function Settings() {
  return (
    <details className="settings">
      <summary className="ghost">설정</summary>
      <nav className="settings-menu">
        <a href="/ocr.html">OCR 이미지 라벨링</a>
      </nav>
    </details>
  )
}

async function postQuestion(question, history) {
  let res
  try {
    res = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, history }),
    })
  } catch {
    // 이 페이지를 준 Vite 개발 서버 자체에 닿지 못했다
    return { error: '화면 서버에 연결할 수 없습니다. 실행 창(start.cmd · start.command)이 닫혔다면 다시 실행하세요.' }
  }
  // Vite 프록시는 API 서버에 닿지 못하면 502 를 돌려준다
  if (res.status === 502) return { error: 'API 서버가 아직 준비되지 않았습니다. 색인을 읽는 동안 잠시 기다린 뒤 다시 물어보세요.' }
  if (!res.ok) return { error: `API 서버 오류 (${res.status}). 실행 창의 로그를 확인하세요.` }
  // 헤더가 온 뒤 연결이 끊기면 본문 읽기가 실패한다 — 턴이 기다림에 멈추지 않게 오류로 끝낸다
  return res.json().catch(() => ({ error: '답변을 받는 중 연결이 끊겼습니다. 다시 물어보세요.' }))
}

function AskBox({ ref, value, onChange, onSubmit, disabled, placeholder, autoFocus }) {
  function onKeyDown(e) {
    // 한글 조합 중의 Enter 는 글자 확정이지 전송이 아니다.
    // Safari 는 compositionend 를 먼저 보내 isComposing 이 false 인 채로 keyCode 229 의 Enter 가 온다
    const composing = e.nativeEvent.isComposing || e.keyCode === 229
    if (e.key === 'Enter' && !e.shiftKey && !composing) {
      e.preventDefault()
      onSubmit()
    }
  }
  return (
    <form className="ask" onSubmit={(e) => { e.preventDefault(); onSubmit() }}>
      <textarea ref={ref} rows={1} value={value} placeholder={placeholder} autoFocus={autoFocus} aria-label="질문"
        onChange={(e) => onChange(e.target.value)} onKeyDown={onKeyDown} />
      <div className="ask-foot">
        <span className="hint">Enter 보내기 · Shift+Enter 줄바꿈</span>
        <button type="submit" className="send" disabled={disabled || !value.trim()} aria-label="질문 보내기">↑</button>
      </div>
    </form>
  )
}

function Turn({ index, turn, openN, onCite, onToggle }) {
  return (
    <section className="turn">
      <p className="bubble">{turn.question}</p>
      <div className="reply">
        <p className="who"><DocIcon />문서 도우미</p>
        {turn.error !== undefined && <p className="error">답변을 받지 못했습니다. {turn.error}</p>}
        {turn.answer === undefined && turn.error === undefined && (
          <p className="waiting"><span className="dots" aria-hidden="true"><i /><i /><i /></span>문서를 찾는 중…</p>
        )}
        {/* 좁은 화면 전용 — 넓은 화면에서는 옆 출처 칸이 같은 카드를 보여 준다 */}
        {turn.sources?.length > 0 && (
          <div className="inline-sources">
            <h3 className="label">출처</h3>
            <Sources index={index} turn={turn} openN={openN} onToggle={onToggle} />
          </div>
        )}
        {turn.answer !== undefined && <Answer text={turn.answer} count={turn.sources.length} onCite={onCite} />}
      </div>
    </section>
  )
}

const DocIcon = () => (
  <span className="avatar" aria-hidden="true">
    <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <path d="M4 1.75h5.5L12.25 4.5v9.75H4z M6 7.5h4 M6 10.5h4" />
    </svg>
  </span>
)

function SourcePane({ index, turn, openN, onToggle }) {
  return (
    <>
      <h3 className="label">출처</h3>
      <p className="pane-question" title={turn.question}>{turn.question}</p>
      {turn.sources?.length > 0
        ? <Sources index={index} turn={turn} openN={openN} onToggle={onToggle} />
        : <p className="meta">{turn.error === undefined ? '답변이 오면 근거 문단이 여기에 표시됩니다.' : '출처가 없습니다.'}</p>}
    </>
  )
}

// 같은 파일의 청크가 여럿이고 HWP 는 쪽 번호도 없어서, 카드마다 청크 첫머리를 보여 구별한다.
// 표 청크 머리의 Col1 Col2 … 는 PDF 파서가 붙인 빈 열 이름이라 뺀다
const snippet = (text) =>
  text.replace(/[|#*`>]|-{3,}|\bCol\d+\b/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 120)

// 카드 목록은 위에 고정하고, 펼친 청크는 그 아래에 연다 — 긴 청크가 다른 카드를 밀어내지 않게
function Sources({ index, turn, openN, onToggle }) {
  return (
    <>
      <ol className="cards">
        {turn.sources.map((source, i) => {
          const n = i + 1
          const [, file, page] = source.match(/^(.*?)(?: p\.(\d+))?$/)
          return (
            <li key={i}>
              <button className="card" data-src={`${index}-${n}`} aria-expanded={openN === n} title={source}
                onClick={() => onToggle(n)}>
                <span className="num">{n}</span>
                <span className="file">{file}</span>
                {page && <span className="page">p.{page}</span>}
                <span className="snippet">{snippet(turn.contexts[i])}</span>
              </button>
            </li>
          )
        })}
      </ol>
      {openN !== null && (
        <div className="chunk">
          <p className="label">[{openN}] {turn.sources[openN - 1]}</p>
          <Markdown remarkPlugins={[remarkGfm]}>{turn.contexts[openN - 1]}</Markdown>
        </div>
      )}
    </>
  )
}

const cite = (n) => `[${n.trim()}](#cite-${n.trim()})`

// [1] · [1, 2] 를 #cite-n 링크로 바꿔 두고 a 를 칩으로 그린다.
// 모델이 [PER-002 근거: 1] 처럼 쓰기도 해서, '근거' 가 든 괄호 안의 홀로 선 번호도 칩으로 만든다
function linkCitations(text) {
  return text.replace(/\[([^[\]]+)\](?!\()/g, (whole, inner) => {
    if (/^\s*\d+(\s*,\s*\d+)*\s*$/.test(inner)) return inner.split(',').map(cite).join('')
    if (!inner.includes('근거')) return whole
    return `[${inner.replace(/(?<![\w.\-가-힣])\d{1,2}(?![\w.%\-가-힣])/g, cite)}]`
  })
}

function Answer({ text, count, onCite }) {
  function Link({ href, children }) {
    const n = Number(href?.match(/^#cite-(\d+)$/)?.[1])
    if (!n) return <a href={href} target="_blank" rel="noreferrer">{children}</a>
    if (n > count) return <>[{n}]</>
    return <button className="chip" onClick={() => onCite(n)} aria-label={`출처 ${n} 보기`}>{n}</button>
  }
  return (
    <div className="answer">
      <Markdown remarkPlugins={[remarkGfm]} components={{ a: Link }}>{linkCitations(text)}</Markdown>
    </div>
  )
}
