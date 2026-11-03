import { useEffect, useRef, useState } from "react";
import type { MathfieldElement } from "mathlive";
import "mathlive/fonts.css";

type MathContentEditorProps = {
  body: string;
  formula: string;
  onBodyChange: (value: string) => void;
  onFormulaChange: (value: string) => void;
};

type SymbolGroup = "常用" | "结构" | "微积分" | "关系";

type FormulaTemplate = {
  label: string;
  title: string;
  latex: string;
};

const TEMPLATES: Record<SymbolGroup, FormulaTemplate[]> = {
  常用: [
    { label: "x", title: "变量 x", latex: "x" },
    { label: "y", title: "变量 y", latex: "y" },
    { label: "π", title: "圆周率", latex: "\\pi" },
    { label: "θ", title: "希腊字母 theta", latex: "\\theta" },
    { label: "ε", title: "希腊字母 epsilon", latex: "\\varepsilon" },
    { label: "δ", title: "希腊字母 delta", latex: "\\delta" },
    { label: "∞", title: "无穷", latex: "\\infty" },
    { label: "±", title: "正负号", latex: "\\pm" },
  ],
  结构: [
    { label: "分数", title: "上下分数", latex: "\\frac{\\placeholder{}}{\\placeholder{}}" },
    { label: "√", title: "平方根", latex: "\\sqrt{\\placeholder{}}" },
    { label: "ⁿ√", title: "n 次方根", latex: "\\sqrt[\\placeholder{}]{\\placeholder{}}" },
    { label: "xⁿ", title: "上标或次方", latex: "^{\\placeholder{}}" },
    { label: "xₙ", title: "下标", latex: "_{\\placeholder{}}" },
    { label: "( )", title: "自适应圆括号", latex: "\\left(\\placeholder{}\\right)" },
    { label: "|x|", title: "绝对值", latex: "\\left|\\placeholder{}\\right|" },
    { label: "分段", title: "分段函数", latex: "\\begin{cases}\\placeholder{}&\\placeholder{}\\\\\\placeholder{}&\\placeholder{}\\end{cases}" },
  ],
  微积分: [
    { label: "lim", title: "极限", latex: "\\lim_{\\placeholder{}\\to\\placeholder{}}\\placeholder{}" },
    { label: "d/dx", title: "导数", latex: "\\frac{d}{dx}\\placeholder{}" },
    { label: "∂", title: "偏导数", latex: "\\frac{\\partial \\placeholder{}}{\\partial \\placeholder{}}" },
    { label: "∫", title: "不定积分", latex: "\\int \\placeholder{}\\,dx" },
    { label: "∫ₐᵇ", title: "定积分", latex: "\\int_{\\placeholder{}}^{\\placeholder{}}\\placeholder{}\\,dx" },
    { label: "Σ", title: "求和", latex: "\\sum_{\\placeholder{}}^{\\placeholder{}}\\placeholder{}" },
    { label: "→", title: "趋向", latex: "\\to" },
    { label: "∞级数", title: "无穷级数", latex: "\\sum_{n=1}^{\\infty}\\placeholder{}" },
  ],
  关系: [
    { label: "=", title: "等于", latex: "=" },
    { label: "≠", title: "不等于", latex: "\\ne" },
    { label: "≤", title: "小于等于", latex: "\\le" },
    { label: "≥", title: "大于等于", latex: "\\ge" },
    { label: "≈", title: "约等于", latex: "\\approx" },
    { label: "∼", title: "等价或渐近", latex: "\\sim" },
    { label: "∈", title: "属于", latex: "\\in" },
    { label: "⇒", title: "推出", latex: "\\Rightarrow" },
  ],
};

/** 中文：提供正文、可视化公式和 Markdown 数学公式插入能力。 English: Edits prose, visual formulas, and Markdown math insertions together. */
export function MathContentEditor({ body, formula, onBodyChange, onFormulaChange }: MathContentEditorProps) {
  const bodyRef = useRef<HTMLTextAreaElement | null>(null);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const mathfieldRef = useRef<MathfieldElement | null>(null);
  const formulaChangeRef = useRef(onFormulaChange);
  const [activeGroup, setActiveGroup] = useState<SymbolGroup>("常用");

  formulaChangeRef.current = onFormulaChange;

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let disposed = false;
    let mounted: MathfieldElement | null = null;
    let handleInput: (() => void) | null = null;
    void import("mathlive").then(({ MathfieldElement: MathfieldConstructor }) => {
      if (disposed) return;
      const mathfield = new MathfieldConstructor();
      mathfield.className = "admin-math-field";
      mathfield.setAttribute("aria-label", "可视化 LaTeX 公式编辑器");
      mathfield.placeholder = "\\text{像在纸上书写一样输入公式}";
      mathfield.smartFence = true;
      mathfield.smartSuperscript = true;
      mathfield.mathVirtualKeyboardPolicy = "auto";
      mathfield.setValue(formula);
      handleInput = () => formulaChangeRef.current(mathfield.getValue("latex-without-placeholders"));
      mathfield.addEventListener("input", handleInput);
      host.replaceChildren(mathfield);
      mathfieldRef.current = mathfield;
      mounted = mathfield;
    });
    return () => {
      disposed = true;
      if (mounted && handleInput) mounted.removeEventListener("input", handleInput);
      if (mathfieldRef.current === mounted) mathfieldRef.current = null;
      mounted?.remove();
    };
  }, []);

  useEffect(() => {
    const mathfield = mathfieldRef.current;
    if (mathfield && mathfield.getValue("latex-without-placeholders") !== formula) {
      mathfield.setValue(formula);
    }
  }, [formula]);

  /** 中文：将选中的公式模板插入可视化公式光标。 English: Inserts a selected template at the visual math caret. */
  function insertTemplate(latex: string) {
    mathfieldRef.current?.insert(latex, { selectionMode: "placeholder", focus: true, feedback: true });
  }

  /** 中文：同时清空可视化公式和受控表单值。 English: Clears both the visual mathfield and its controlled form value. */
  function clearFormula() {
    mathfieldRef.current?.setValue("");
    onFormulaChange("");
    mathfieldRef.current?.focus();
  }

  /** 中文：把当前公式按行内或独立格式插入正文光标。 English: Inserts the current formula into prose as inline or display math. */
  function insertIntoBody(display: boolean) {
    const latex = mathfieldRef.current?.getValue("latex-without-placeholders").trim();
    if (!latex) return;
    const textarea = bodyRef.current;
    const start = textarea?.selectionStart ?? body.length;
    const end = textarea?.selectionEnd ?? body.length;
    const wrapped = display ? `\n\n$$\n${latex}\n$$\n\n` : `$${latex}$`;
    onBodyChange(`${body.slice(0, start)}${wrapped}${body.slice(end)}`);
    window.requestAnimationFrame(() => {
      const caret = start + wrapped.length;
      textarea?.focus();
      textarea?.setSelectionRange(caret, caret);
    });
  }

  return <div className="math-content-editor full">
    <label>正文（Markdown，可直接输入中文）
      <textarea ref={bodyRef} className="editor" value={body} onChange={event => onBodyChange(event.target.value)} required />
    </label>
    <section className="visual-formula-panel">
      <header><div><strong>可视化公式编辑器</strong><span>支持分数、根式、上下标、极限、积分和求和</span></div><button type="button" onClick={clearFormula}>清空公式</button></header>
      <div ref={hostRef} className="admin-math-host" />
      <div className="formula-group-tabs" role="tablist" aria-label="数学符号分类">
        {(Object.keys(TEMPLATES) as SymbolGroup[]).map(group => <button type="button" role="tab" aria-selected={activeGroup === group} className={activeGroup === group ? "active" : ""} key={group} onClick={() => setActiveGroup(group)}>{group}</button>)}
      </div>
      <div className="formula-template-grid">
        {TEMPLATES[activeGroup].map(template => <button type="button" title={template.title} aria-label={template.title} key={template.title} onClick={() => insertTemplate(template.latex)}>{template.label}</button>)}
      </div>
      <footer><span>公式会保存为标准 LaTeX，也可以插入上方正文。</span><div><button type="button" onClick={() => insertIntoBody(false)}>插入行内公式</button><button type="button" className="formula-insert-primary" onClick={() => insertIntoBody(true)}>插入独立公式</button></div></footer>
    </section>
  </div>;
}

/** 中文：以只读排版形式展示 LaTeX 公式。 English: Displays LaTeX as a read-only typeset expression. */
export function MathFormulaDisplay({ latex }: { latex: string }) {
  const hostRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let disposed = false;
    void import("mathlive").then(({ MathfieldElement }) => {
      if (disposed) return;
      const mathfield = new MathfieldElement();
      mathfield.className = "admin-math-display";
      mathfield.readOnly = true;
      mathfield.setValue(latex);
      host.replaceChildren(mathfield);
    });
    return () => { disposed = true; host.replaceChildren(); };
  }, [latex]);

  return <div ref={hostRef} className="admin-math-display-host" aria-label={`公式：${latex}`} />;
}
