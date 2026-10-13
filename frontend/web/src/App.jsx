import { useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export default function App() {
  // 대화 기록은 이 탭에만 있다. 턴: { question, answer?, sources?, contexts?, error? }
  const [turns, setTurns] = useState([])
  const [input, setInput] = useState('')
  const thread = useRef(0)
  const last = turns.at(-1)
  const pending = last !== undefined && last.answer === undefined && last.error === undefined

  useEffect(() => {
    document.querySelector('.turn:last-of-type')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [turns.length])

  async function ask() {
    const question = input.trim()
    if (!question || pending) return
    const gen = thread.current
    const history = turns.filter((t) => t.answer !== undefined).map((t) => ({ question: t.question, answer: t.answer }))
    setTurns([...turns, { question }])
    setInput('')
    const result = await postQuestion(question, history)
    // 새 스레드를 시작한 뒤 도착한 응답은 버린다
    if (gen !== thread.current) return
    setTurns((ts) => ts.map((t, i) => (i === ts.length - 1 ? { ...t, ...result } : t)))
  }

  function newThread() {
    thread.current += 1
    setTurns([])
    setInput('')
  }

  if (turns.length === 0) {
    return (
      <main className="landing">
        <h1>RFP 질의응답</h1>
        <p className="lead">공공기관 제안요청서에 대해 물어보세요. 답변의 번호를 누르면 근거 문단이 열립니다.</p>
        <AskBox value={input} onChange={setInput} onSubmit={ask} autoFocus
          placeholder="예: 고려대학교 차세대 포털 시스템 사업의 응답 시간 요구사항은?" />
      </main>
    )
  }

  return (
    <>
      <header className="bar">
        <span className="brand">RFP 질의응답</span>
        <button className="ghost" onClick={newThread}>새 스레드</button>
      </header>
      <main className="thread">
        {turns.map((turn, i) => <Turn key={i} id={`t${i}`} turn={turn} />)}
      </main>
      <footer className="dock">
        <AskBox value={input} onChange={setInput} onSubmit={ask} disabled={pending}
          placeholder={pending ? '답변을 기다리는 중…' : '이어서 질문하기'} />
      </footer>
    </>
  )
}

async function postQuestion(question, history) {
  try {
    const res = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, history }),
    })
    if (!res.ok) throw new Error(`서버 응답 ${res.status}`)
    return await res.json()
  } catch (e) {
    return { error: e.message }
  }
}

function AskBox({ value, onChange, onSubmit, disabled, placeholder, autoFocus }) {
  function onKeyDown(e) {
    // 한글 조합 중의 Enter 는 글자 확정이지 전송이 아니다
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      onSubmit()
    }
  }
  return (
    <form className="ask" onSubmit={(e) => { e.preventDefault(); onSubmit() }}>
      <textarea rows={1} value={value} placeholder={placeholder} autoFocus={autoFocus} aria-label="질문"
        onChange={(e) => onChange(e.target.value)} onKeyDown={onKeyDown} />
      <button type="submit" className="send" disabled={disabled || !value.trim()} aria-label="질문 보내기">↑</button>
    </form>
  )
}

function Turn({ id, turn }) {
  const [open, setOpen] = useState(null)

  function showSource(n) {
    setOpen(n)
    document.getElementById(`${id}-src-${n}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  return (
    <section className="turn">
      <h2 className="question">{turn.question}</h2>
      {turn.error !== undefined && (
        <p className="error">답변을 받지 못했습니다 ({turn.error}). 서버를 막 켰다면 색인을 읽는 동안 잠시 기다린 뒤 다시 물어보세요.</p>
      )}
      {turn.answer === undefined && turn.error === undefined && <p className="waiting">문서를 찾아 답변을 만드는 중…</p>}
      {turn.sources?.length > 0 && (
        <Sources id={id} sources={turn.sources} contexts={turn.contexts} open={open}
          onToggle={(n) => setOpen(open === n ? null : n)} />
      )}
      {turn.answer !== undefined && <Answer text={turn.answer} count={turn.sources.length} onCite={showSource} />}
    </section>
  )
}

function Sources({ id, sources, contexts, open, onToggle }) {
  return (
    <div className="sources">
      <h3 className="label">출처</h3>
      <ol className="cards">
        {sources.map((source, i) => {
          const [, file, page] = source.match(/^(.*?)(?: p\.(\d+))?$/)
          return (
            <li key={i}>
              <button id={`${id}-src-${i + 1}`} className="card" aria-expanded={open === i + 1}
                onClick={() => onToggle(i + 1)}>
                <span className="num">{i + 1}</span>
                <span className="file" title={file}>{file}</span>
                {page && <span className="page">p.{page}</span>}
              </button>
            </li>
          )
        })}
      </ol>
      {open !== null && (
        <blockquote className="chunk">
          <span className="label">[{open}] {sources[open - 1]}</span>
          <Markdown remarkPlugins={[remarkGfm]}>{contexts[open - 1]}</Markdown>
        </blockquote>
      )}
    </div>
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
      <h3 className="label">답변</h3>
      <Markdown remarkPlugins={[remarkGfm]} components={{ a: Link }}>{linkCitations(text)}</Markdown>
    </div>
  )
}
