import type { ReactNode } from "react";

/** 中文：显示管理端弹窗，并可为复杂编辑器启用宽版布局。 English: Displays an admin modal with an optional wide layout for complex editors. */
export function Modal({ title, children, onClose, wide = false }: { title: string; children: ReactNode; onClose: () => void; wide?: boolean }) {
  return <div className="modal-backdrop" onMouseDown={onClose}>
    <section className={`modal ${wide ? "wide" : ""}`} onMouseDown={event => event.stopPropagation()}>
      <header><h2>{title}</h2><button className="icon-button" onClick={onClose}>×</button></header>
      {children}
    </section>
  </div>;
}
