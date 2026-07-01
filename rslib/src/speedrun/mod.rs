// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! SOA Exam P "Speedrun" fork: study-readiness features layered on top of
//! Anki's engine. Kept in a self-contained module so the diff against upstream
//! stays small and easy to merge.

pub(crate) mod mastery;
mod service;
