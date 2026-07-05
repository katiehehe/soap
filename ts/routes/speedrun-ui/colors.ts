// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

// Single source of truth for the semantic (honest) signal colours shared by the
// custom Speedrun screens. Mirrors the --sr-* tokens in ts/routes/base.scss.
//
// SEMANTIC and FIXED: these encode measured meaning (not-started / in-progress /
// mastered) and must never be swapped for decoration.

export const SIGNAL = {
    pending: "#8a9598", // not started (cool grey)
    progress: "#d3a95f", // in progress (suds gold)
    mastered: "#5bb39a", // mastered / good (fresh mint)
    weak: "#c9705c", // performance: struggling (clay red)
    memory: "#5b8fd6", // memory / spaced-repetition track (sky blue)
} as const;
