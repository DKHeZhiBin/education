import { useEffect, useRef, type ReactNode, type RefObject } from 'react'
import type { MathfieldElement, OutputFormat } from 'mathlive'
import 'mathlive/fonts.css'

/** 中文：渲染包含 Markdown 风格行内公式与公式块的数学正文。 English: Renders prose containing Markdown-style inline and display math. */
export function MathMarkdown({ source, className = '' }: { source: string; className?: string }) {
  const blocks = splitDisplayMath(source)
  return <div className={`math-markdown ${className}`.trim()}>
    {blocks.map((block, index) => block.kind === 'math'
      ? <MathFormula key={`math-${index}`} latex={block.value} display />
      : <MathProse key={`text-${index}`} source={block.value} />)}
  </div>
}

/** 中文：在标题、按钮或列表项内渲染可混排公式的单行文字。 English: Renders one line of mixed prose and math inside headings, buttons, or list items. */
export function MathInline({ source, className = '' }: { source: string; className?: string }) {
  return <span className={`math-inline-text ${className}`.trim()}>{renderInlineMath(source)}</span>
}

type MathBlock = { kind: 'text' | 'math'; value: string }
type FormulaFormat = Extract<OutputFormat, 'latex' | 'ascii-math'>
type InlineFragment = { kind: 'text' | 'math'; value: string; format?: FormulaFormat }

const proseBoundary = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}，。；：！？、…“”‘’《》【】]/u
const latexCommand = /\\(?:frac|dfrac|tfrac|sqrt|lim|sum|prod|int|oint|begin|end|left|right|infty|to|rightarrow|leq|geq|neq|cdot|times|div|sin|cos|tan|ln|log|exp|mathrm|mathbf|overline|underline|vec|hat|bar|binom|partial|nabla|pm|mp|alpha|beta|gamma|delta|theta|lambda|mu|pi|sigma|phi|omega)\b/

/** 中文：把双美元符号或方括号包裹的独立公式从正文中拆出。 English: Splits display formulas delimited by double dollars or LaTeX brackets from prose. */
function splitDisplayMath(source: string): MathBlock[] {
  const parts = source.split(/(\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\])/g).filter(Boolean)
  return parts.map(part => {
    if (part.startsWith('$$') && part.endsWith('$$')) return { kind: 'math', value: part.slice(2, -2).trim() }
    if (part.startsWith('\\[') && part.endsWith('\\]')) return { kind: 'math', value: part.slice(2, -2).trim() }
    return { kind: 'text', value: part }
  })
}

/** 中文：渲染普通段落，并识别其中的行内 LaTeX。 English: Renders prose paragraphs while recognizing inline LaTeX. */
function MathProse({ source }: { source: string }) {
  const paragraphs = source.split(/\n\s*\n|\n/g).map(item => item.trim()).filter(Boolean)
  if (!paragraphs.length) return null
  return <>{paragraphs.map((paragraph, index) => <p key={index}>{renderInlineMath(paragraph)}</p>)}</>
}

/** 中文：将单美元符号或圆括号包裹的公式转换为只读数学组件。 English: Converts inline formulas delimited by single dollars or LaTeX parentheses into read-only math components. */
function renderInlineMath(source: string): ReactNode[] {
  return source.split(/(\$(?!\$)[^$\n]+\$|\\\([^\n]*?\\\))/g).filter(Boolean).flatMap((part, index) => {
    if (part.startsWith('$') && part.endsWith('$')) return <MathFormula key={index} latex={part.slice(1, -1).trim()} />
    if (part.startsWith('\\(') && part.endsWith('\\)')) return <MathFormula key={index} latex={part.slice(2, -2).trim()} />
    return splitUndelimitedMath(part).map((fragment, fragmentIndex) => fragment.kind === 'math'
      ? <MathFormula key={`${index}-${fragmentIndex}`} latex={fragment.value} format={fragment.format} />
      : fragment.value)
  })
}

/**
 * 中文：识别模型或旧数据中未被 `$...$` 包裹的公式，兼容 `f(x)=\\frac{...}{...}`、`x^2+1` 与 `∞-∞`。
 * English: Detects bare formulas from model output or legacy data, including LaTeX commands, ASCII math, and Unicode operators.
 */
function splitUndelimitedMath(source: string): InlineFragment[] {
  const fragments: InlineFragment[] = []
  let cursor = 0
  let runStart = 0

  const pushRun = (end: number) => {
    if (end <= runStart) return
    const value = source.slice(runStart, end)
    const leading = value.match(/^\s*/)?.[0] ?? ''
    const trailing = value.match(/\s*$/)?.[0] ?? ''
    const candidate = value.slice(leading.length, value.length - trailing.length)
    if (!candidate || !looksLikeMath(candidate)) {
      fragments.push({ kind: 'text', value })
      return
    }
    if (leading) fragments.push({ kind: 'text', value: leading })
    fragments.push({
      kind: 'math',
      value: normalizeBareFormula(candidate),
      format: latexCommand.test(candidate) || /\\[A-Za-z]+/.test(candidate) ? 'latex' : 'ascii-math',
    })
    if (trailing) fragments.push({ kind: 'text', value: trailing })
  }

  while (cursor < source.length) {
    const character = source[cursor]
    if (proseBoundary.test(character)) {
      pushRun(cursor)
      fragments.push({ kind: 'text', value: character })
      cursor += character.length
      runStart = cursor
      continue
    }
    cursor += character.length
  }
  pushRun(source.length)
  return mergeTextFragments(fragments)
}

/** 中文：判断一段非中文文本是否具有明确的数学结构。 English: Determines whether a non-CJK run has an explicit mathematical structure. */
function looksLikeMath(value: string) {
  const compact = value.trim()
  if (latexCommand.test(compact) || /\\[A-Za-z]+/.test(compact)) return true
  if (/[∞√∑∏∫≤≥≠±×÷∂∇α-ωΑ-Ω]/.test(compact)) return true
  if (/[_^]/.test(compact) && /[A-Za-z0-9)}\]]/.test(compact)) return true
  if (/[A-Za-z0-9)}\]]\s*(?:=|<|>|\+|-|\*|\/|→)\s*[A-Za-z0-9({\[]/.test(compact)) return true
  if (/^[A-Za-z](?:['′]{0,3})\s*\([^)]*\)$/.test(compact)) return true
  if (/^[([{][A-Za-z0-9+\-*/.,\s]+[)\]}]$/.test(compact)) return true
  if (/^(?:sin|cos|tan|cot|sec|csc|ln|log|exp)\s*\(?[A-Za-z0-9]/i.test(compact)) return true
  return /^[A-Za-z]$|^[A-Z]{2,3}$/.test(compact)
}

/** 中文：把常见 Unicode 数学符号转换为 ASCIIMath 可识别形式。 English: Normalizes common Unicode operators for MathLive's ASCIIMath parser. */
function normalizeBareFormula(value: string) {
  if (latexCommand.test(value) || /\\[A-Za-z]+/.test(value)) return value
  return value
    .replaceAll('∞', 'oo')
    .replaceAll('√', 'sqrt')
    .replaceAll('≤', '<=')
    .replaceAll('≥', '>=')
    .replaceAll('≠', '!=')
    .replaceAll('±', '+-')
    .replaceAll('×', '*')
    .replaceAll('÷', '/')
    .replaceAll('→', '->')
}

/** 中文：合并相邻文本片段，减少无意义 React 节点。 English: Merges adjacent text fragments to avoid unnecessary React nodes. */
function mergeTextFragments(fragments: InlineFragment[]) {
  return fragments.reduce<InlineFragment[]>((result, fragment) => {
    const previous = result.at(-1)
    if (fragment.kind === 'text' && previous?.kind === 'text') previous.value += fragment.value
    else result.push(fragment)
    return result
  }, [])
}

/** 中文：使用 MathLive 显示只读 LaTeX 公式。 English: Displays a read-only LaTeX formula with MathLive. */
function MathFormula({ latex, display = false, format = 'latex' }: { latex: string; display?: boolean; format?: FormulaFormat }) {
  const hostRef = useRef<HTMLSpanElement | HTMLDivElement | null>(null)

  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    let disposed = false
    let mounted: MathfieldElement | null = null
    void import('mathlive').then(({ MathfieldElement }) => {
      if (disposed) return
      const field = new MathfieldElement()
      field.className = display ? 'math-markdown-display' : 'math-markdown-inline'
      field.readOnly = true
      field.setValue(latex, { format })
      host.replaceChildren(field)
      mounted = field
    })
    return () => {
      disposed = true
      mounted?.remove()
    }
  }, [latex, display, format])

  return display
    ? <div ref={hostRef as RefObject<HTMLDivElement>} className="math-markdown-display-host" aria-label={`公式：${latex}`} />
    : <span ref={hostRef as RefObject<HTMLSpanElement>} className="math-markdown-inline-host" aria-label={`公式：${latex}`} />
}
