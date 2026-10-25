// CodeMirror 6 editor for Haskell, bundled by build.sh into a single static file
// that exposes window.HaskellEditor:
//
//   const view = HaskellEditor.create(element, {doc: "...", readOnly: false});
//   HaskellEditor.getCode(view) / setCode(view, text) / setReadOnly(view, bool)
//   HaskellEditor.showDiagnostics(view, [{from: [line, col], to: [line, col], severity, message}])
//
// Diagnostics use 1-based lines and columns, as GHC reports them.

import { basicSetup, EditorView } from "codemirror";
import { indentWithTab } from "@codemirror/commands";
import { indentUnit, StreamLanguage } from "@codemirror/language";
import { haskell } from "@codemirror/legacy-modes/mode/haskell";
import { lintGutter, setDiagnostics } from "@codemirror/lint";
import { Compartment, EditorState } from "@codemirror/state";
import { keymap } from "@codemirror/view";

const editable = new Compartment();

function editability(readOnly) {
  return [EditorState.readOnly.of(readOnly), EditorView.editable.of(!readOnly)];
}

export function create(parent, { doc = "", readOnly = false } = {}) {
  return new EditorView({
    parent,
    state: EditorState.create({
      doc,
      extensions: [
        basicSetup,
        keymap.of([indentWithTab]),
        indentUnit.of("  "), // GHC warns about tabs: indent with spaces
        StreamLanguage.define(haskell),
        lintGutter(),
        editable.of(editability(readOnly)),
      ],
    }),
  });
}

export function getCode(view) {
  return view.state.doc.toString();
}

export function setCode(view, text) {
  view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: text } });
}

export function setReadOnly(view, readOnly) {
  view.dispatch({ effects: editable.reconfigure(editability(readOnly)) });
}

function position(doc, [line, col]) {
  const l = doc.line(Math.min(Math.max(line, 1), doc.lines));
  return Math.min(l.from + Math.max(col - 1, 0), l.to);
}

export function showDiagnostics(view, diagnostics) {
  const doc = view.state.doc;
  const list = diagnostics.map((d) => {
    const from = position(doc, d.from);
    return { from, to: Math.max(from, position(doc, d.to)), severity: d.severity, message: d.message };
  });
  view.dispatch(setDiagnostics(view.state, list));
}
