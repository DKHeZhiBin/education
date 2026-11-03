import { MathContentEditor } from "./MathContentEditor";
import type { SolutionFrameworkStep } from "../types";

type SolutionFrameworkEditorProps = {
  steps: SolutionFrameworkStep[];
  onChange: (steps: SolutionFrameworkStep[]) => void;
};

const emptyStep = (): SolutionFrameworkStep => ({ title: "", framework: "", solution_step: "", formula_latex: null });

/** 中文：编辑题型的框架思路，并让每一段思路紧邻对应的实际解题步骤。 English: Edits a problem-type framework with each idea paired directly with its worked step. */
export function SolutionFrameworkEditor({ steps, onChange }: SolutionFrameworkEditorProps) {
  /** 中文：更新指定步骤中的一个字段。 English: Updates one field in a selected framework step. */
  const updateStep = (index: number, patch: Partial<SolutionFrameworkStep>) => onChange(steps.map((step, stepIndex) => stepIndex === index ? { ...step, ...patch } : step));

  /** 中文：移动步骤并保持思路和解题内容成对。 English: Moves a step while keeping its idea and worked content paired. */
  const moveStep = (index: number, offset: number) => {
    const destination = index + offset;
    if (destination < 0 || destination >= steps.length) return;
    const next = [...steps];
    [next[index], next[destination]] = [next[destination], next[index]];
    onChange(next);
  };

  return <section className="solution-framework-editor full">
    <header><div><h3>解题框架</h3><p>每一步先说明“为什么这样想”，再填写这道例题对应的实际解题步骤。</p></div><button type="button" className="secondary" onClick={() => onChange([...steps, emptyStep()])}>＋ 添加框架步骤</button></header>
    {steps.map((step, index) => <article key={index} className="solution-framework-step-editor">
      <div className="solution-framework-step-heading"><strong>步骤 {index + 1}</strong><div><button type="button" disabled={index === 0} onClick={() => moveStep(index, -1)}>上移</button><button type="button" disabled={index === steps.length - 1} onClick={() => moveStep(index, 1)}>下移</button><button type="button" className="danger" onClick={() => onChange(steps.filter((_, stepIndex) => stepIndex !== index))}>删除</button></div></div>
      <label>步骤标题<input value={step.title} onChange={event => updateStep(index, { title: event.target.value })} placeholder="例如：识别结构并选择方法" required /></label>
      <label>框架思路<textarea value={step.framework} onChange={event => updateStep(index, { framework: event.target.value })} placeholder="说明这一阶段要观察什么、为什么这样处理" required /></label>
      <MathContentEditor body={step.solution_step} formula={step.formula_latex ?? ""} onBodyChange={value => updateStep(index, { solution_step: value })} onFormulaChange={value => updateStep(index, { formula_latex: value || null })} />
    </article>)}
    {!steps.length && <div className="empty framework-empty">题型还没有解题框架。添加后，学生端会按步骤显示“框架思路 + 对应解题步骤”。</div>}
  </section>;
}
