// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

// Best-effort MathJax rendering for the formula sheet. Mirrors the practice
// test's action (ts/routes/practice-test/mathjax.ts): MathJax (tex-svg-full,
// the same bundle the editor uses) is loaded lazily on the client and typesets
// a node's LaTeX (\( ... \) / \[ ... \]). If it can't load, the node simply
// keeps its plain text, so a missing bundle never breaks the reference sheet.

/* eslint @typescript-eslint/no-explicit-any: "off" */

let mathjaxPromise: Promise<any> | null = null;

async function ensureMathJax(): Promise<any> {
    if (!mathjaxPromise) {
        mathjaxPromise = import("mathjax/es5/tex-svg-full")
            .then(() => (globalThis as any).MathJax ?? null)
            .catch(() => null);
    }
    return mathjaxPromise;
}

async function typeset(node: HTMLElement): Promise<void> {
    const mj = await ensureMathJax();
    if (!mj?.typesetPromise) {
        return;
    }
    try {
        await mj.startup?.promise;
        mj.typesetClear?.([node]);
        await mj.typesetPromise([node]);
    } catch {
        // Leave the plain text in place — never block the sheet on rendering.
    }
}

/** Svelte action: typeset the node now and again whenever `deps` changes. */
export function mathjax(node: HTMLElement, _deps?: unknown) {
    void typeset(node);
    return {
        update(): void {
            void typeset(node);
        },
    };
}
