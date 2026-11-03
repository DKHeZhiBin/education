import { useEffect, useRef, useState } from 'react'
import type { MathfieldElement } from 'mathlive'
import 'mathlive/fonts.css'

type SymbolGroup = '常用' | '结构' | '关系' | '符号'

type MathTemplate = {
  label: string
  spokenLabel: string
  latex: string
}

const TEMPLATES: Record<SymbolGroup, MathTemplate[]> = {
  常用: [
    { label: 'x', spokenLabel: '变量 x', latex: 'x' },
    { label: 'y', spokenLabel: '变量 y', latex: 'y' },
    { label: '+', spokenLabel: '加号', latex: '+' },
    { label: '−', spokenLabel: '减号', latex: '-' },
    { label: '×', spokenLabel: '乘号', latex: '\\times' },
    { label: '÷', spokenLabel: '除号', latex: '\\div' },
    { label: '=', spokenLabel: '等号', latex: '=' },
    { label: '±', spokenLabel: '正负号', latex: '\\pm' },
  ],
  结构: [
    { label: '▤', spokenLabel: '上下分数', latex: '\\frac{\\placeholder{}}{\\placeholder{}}' },
    { label: '√', spokenLabel: '平方根', latex: '\\sqrt{\\placeholder{}}' },
    { label: 'ⁿ√', spokenLabel: 'n 次方根', latex: '\\sqrt[\\placeholder{}]{\\placeholder{}}' },
    { label: 'x²', spokenLabel: '上标或次方', latex: '^{\\placeholder{}}' },
    { label: 'xₙ', spokenLabel: '下标', latex: '_{\\placeholder{}}' },
    { label: '( )', spokenLabel: '圆括号', latex: '\\left(\\placeholder{}\\right)' },
    { label: '|x|', spokenLabel: '绝对值', latex: '\\left|\\placeholder{}\\right|' },
    { label: '{ }', spokenLabel: '集合', latex: '\\left\\{\\placeholder{}\\right\\}' },
  ],
  关系: [
    { label: '≠', spokenLabel: '不等于', latex: '\\ne' },
    { label: '<', spokenLabel: '小于', latex: '<' },
    { label: '>', spokenLabel: '大于', latex: '>' },
    { label: '≤', spokenLabel: '小于等于', latex: '\\le' },
    { label: '≥', spokenLabel: '大于等于', latex: '\\ge' },
    { label: '≈', spokenLabel: '约等于', latex: '\\approx' },
    { label: '∥', spokenLabel: '平行', latex: '\\parallel' },
    { label: '⊥', spokenLabel: '垂直', latex: '\\perp' },
  ],
  符号: [
    { label: 'π', spokenLabel: '圆周率', latex: '\\pi' },
    { label: 'θ', spokenLabel: '西塔', latex: '\\theta' },
    { label: '△', spokenLabel: '三角形', latex: '\\triangle' },
    { label: '∠', spokenLabel: '角', latex: '\\angle' },
    { label: '∞', spokenLabel: '无穷', latex: '\\infty' },
    { label: '∈', spokenLabel: '属于', latex: '\\in' },
    { label: '∑', spokenLabel: '求和', latex: '\\sum' },
    { label: '→', spokenLabel: '推出或趋向', latex: '\\to' },
  ],
}

type MathAnswerComposerProps = {
  id: string
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  rows?: number
  placeholder?: string
}

/** 中文：提供文字步骤与可视化数学公式组合输入。 English: Combines prose input with a visual math editor. */
export function MathAnswerComposer({
  id,
  value,
  onChange,
  disabled = false,
  rows = 3,
  placeholder = '写下你的关系、计算或理由…',
}: MathAnswerComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const mathHostRef = useRef<HTMLDivElement | null>(null)
  const mathfieldRef = useRef<MathfieldElement | null>(null)
  const [activeGroup, setActiveGroup] = useState<SymbolGroup>('常用')
  const [hasFormula, setHasFormula] = useState(false)

  useEffect(() => {
    const host = mathHostRef.current
    if (!host) return
    let disposed = false
    let mountedMathfield: MathfieldElement | null = null
    let updateFormulaState: (() => void) | null = null
    void import('mathlive').then(({ MathfieldElement: MathfieldConstructor }) => {
      if (disposed) return
      const mathfield = new MathfieldConstructor()
      mathfield.className = 'visual-math-field'
      mathfield.setAttribute('aria-label', '可视化数学公式输入')
      mathfield.placeholder = '\\text{在这里像手写一样输入公式}'
      mathfield.smartFence = true
      mathfield.smartSuperscript = true
      mathfield.mathVirtualKeyboardPolicy = 'auto'
      mathfield.disabled = disabled
      updateFormulaState = () => {
        setHasFormula(Boolean(mathfield.getValue('latex-without-placeholders').trim()))
      }
      mathfield.addEventListener('input', updateFormulaState)
      host.replaceChildren(mathfield)
      mathfieldRef.current = mathfield
      mountedMathfield = mathfield
    })
    return () => {
      disposed = true
      if (mountedMathfield && updateFormulaState) {
        mountedMathfield.removeEventListener('input', updateFormulaState)
      }
      if (mathfieldRef.current === mountedMathfield) mathfieldRef.current = null
      mountedMathfield?.remove()
    }
  }, [])

  useEffect(() => {
    if (mathfieldRef.current) mathfieldRef.current.disabled = disabled
  }, [disabled])

  /** 中文：将公式模板插入当前公式光标。 English: Inserts a template at the math caret. */
  const insertTemplate = (latex: string) => {
    if (disabled) return
    mathfieldRef.current?.insert(latex, {
      selectionMode: 'placeholder',
      focus: true,
      feedback: true,
    })
  }

  /** 中文：把排版后的公式转成清晰文本并插入作答光标。 English: Inserts the typeset formula into the prose answer at its caret. */
  const insertFormulaIntoAnswer = () => {
    const mathfield = mathfieldRef.current
    if (!mathfield || disabled) return
    const formula = mathfield.getValue('ascii-math').trim()
    if (!formula) return
    const textarea = textareaRef.current
    const start = textarea?.selectionStart ?? value.length
    const end = textarea?.selectionEnd ?? value.length
    const before = value.slice(0, start)
    const after = value.slice(end)
    const leadingSpace = before && !/[\s\n]$/.test(before) ? ' ' : ''
    const trailingSpace = after && !/^[\s\n，。；,.!?！？]/.test(after) ? ' ' : ''
    const inserted = `${leadingSpace}${formula}${trailingSpace}`
    onChange(`${before}${inserted}${after}`)
    mathfield.setValue('')
    setHasFormula(false)
    window.requestAnimationFrame(() => {
      const caret = start + inserted.length
      textarea?.focus()
      textarea?.setSelectionRange(caret, caret)
    })
  }

  /** 中文：清除公式草稿。 English: Clears the current formula draft. */
  const clearFormula = () => {
    mathfieldRef.current?.setValue('')
    mathfieldRef.current?.focus()
    setHasFormula(false)
  }

  return <div className="math-answer-composer">
    <textarea
      ref={textareaRef}
      id={id}
      rows={rows}
      value={value}
      disabled={disabled}
      onChange={event => onChange(event.target.value)}
      placeholder={placeholder}
    />
    <div className="visual-math-composer" aria-label="数学公式编辑器">
      <div className="visual-math-heading">
        <div><strong>公式手写板</strong><span>分数、根式和上下标会按纸笔形式排版</span></div>
        <button type="button" className="math-clear-button" disabled={disabled || !hasFormula} onClick={clearFormula}>清空</button>
      </div>
      <div ref={mathHostRef} className="visual-math-host" />
      <div className="math-symbol-groups" role="tablist" aria-label="数学符号分类">
        {(Object.keys(TEMPLATES) as SymbolGroup[]).map(group => <button
          key={group}
          type="button"
          role="tab"
          aria-selected={activeGroup === group}
          className={activeGroup === group ? 'active' : ''}
          disabled={disabled}
          onClick={() => setActiveGroup(group)}
        >{group}</button>)}
      </div>
      <div className="math-symbol-grid" aria-label={`${activeGroup}数学符号`}>
        {TEMPLATES[activeGroup].map(template => <button
          key={template.spokenLabel}
          type="button"
          title={template.spokenLabel}
          aria-label={template.spokenLabel}
          disabled={disabled}
          onClick={() => insertTemplate(template.latex)}
        >{template.label}</button>)}
      </div>
      <div className="visual-math-footer">
        <span>可直接使用键盘输入；手机端点公式框可打开完整数学键盘。</span>
        <button type="button" className="math-insert-button" disabled={disabled || !hasFormula} onClick={insertFormulaIntoAnswer}>加入上方作答 ↑</button>
      </div>
    </div>
  </div>
}
