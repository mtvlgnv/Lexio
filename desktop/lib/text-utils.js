/**
 * Shared text helpers for turning a big blob of captured text (from DOM, AX,
 * or OCR) into the single sentence around a selected word — with a guard
 * that refuses to ship a wrong sentence (which would yield a confidently
 * wrong definition). Used by both context.js and ocr-context.js so all three
 * capture sources go through the exact same guarded extraction.
 */
const WINDOW = 240;

function expandToSentence(fullText, matchIndex, matchLen) {
  const start = Math.max(0, matchIndex - WINDOW);
  const end = Math.min(fullText.length, matchIndex + matchLen + WINDOW);
  const slice = fullText.slice(start, end);
  const localIndex = matchIndex - start;
  const before = slice.slice(0, localIndex);
  const match = slice.slice(localIndex, localIndex + matchLen);
  const after = slice.slice(localIndex + matchLen);

  const sentenceStart = Math.max(before.lastIndexOf('. '), before.lastIndexOf('! '), before.lastIndexOf('? '), before.lastIndexOf('\n'));
  const trimmedBefore = sentenceStart >= 0 ? before.slice(sentenceStart + 2) : before;

  const sentenceEnd = after.search(/[.!?](?=\s|$)/);
  const trimmedAfter = sentenceEnd >= 0 ? after.slice(0, sentenceEnd + 1) : after;

  return (trimmedBefore + match + trimmedAfter).trim();
}

function findWordInText(fullText, word) {
  const w = (word || '').trim();
  if (!w || !fullText) return null;

  let idx = fullText.indexOf(w);
  if (idx >= 0) return { idx, len: w.length };

  const lower = fullText.toLowerCase();
  const lw = w.toLowerCase();
  idx = lower.indexOf(lw);
  if (idx >= 0) return { idx, len: w.length };

  const bare = w.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, '');
  if (bare && bare !== w) {
    idx = fullText.indexOf(bare);
    if (idx >= 0) return { idx, len: bare.length };
    idx = lower.indexOf(bare.toLowerCase());
    if (idx >= 0) return { idx, len: bare.length };
  }
  return null;
}

// A WRONG sentence yields a wrong definition the user can't detect — which
// is strictly worse than honestly showing the word alone. This rejects the
// confidently-wrong cases the compat sweep found: Terminal (hands back its
// whole scrollback buffer, so we "find" the word buried in shell output and
// extract shell noise as its "sentence"), apps that return a different
// document than the one the selection lives in, and OCR that grabbed UI
// chrome instead of prose. We can't catch every wrong grab without true
// cursor-to-glyph mapping, but we can reject the ones that clearly aren't a
// clean single sentence of prose.
function isPlausibleSentence(sentence) {
  const s = sentence.trim();
  // A single-word lookup's surrounding sentence is short. A 350+ char
  // "sentence" means expandToSentence never found a boundary and we grabbed
  // a whole scrollback/UI subtree, not a line. (Known-good captures from the
  // compat sweep were all under ~210 chars.)
  if (s.length < 1 || s.length > 350) return false;
  // A single sentence has no hard line breaks; scrollback and flattened UI
  // trees do (expandToSentence bounds the START at a newline but the END
  // only at ./!/?, so a run of unpunctuated lines slips through).
  if (/\n/.test(s)) return false;
  // Shell prompts / paths / code — never in a prose sentence.
  if (/[@~|]/.test(s)) return false;                 // user@host, ~/path, pipes
  if ((s.match(/\//g) || []).length >= 2) return false;   // /usr/local/bin
  // Overwhelmingly ordinary prose characters.
  const proseChars = (s.match(/[\p{L}\p{N}\s.,;:'"()\-–—!?%$&]/gu) || []).length;
  if (proseChars / s.length < 0.9) return false;
  // UI chrome repeats labels ("Home Inbox Settings Home Inbox Settings…");
  // real prose does not repeat a content word 4+ times in one sentence.
  const words = s.toLowerCase().match(/\p{L}{4,}/gu) || [];
  const counts = new Map();
  for (const w of words) {
    const c = (counts.get(w) || 0) + 1;
    if (c >= 4) return false;
    counts.set(w, c);
  }
  return true;
}

// Extract the guarded sentence around `word` from a captured text blob.
// Returns the sentence, or null to signal "degrade to word-only".
function contextFromText(fullText, word, source) {
  if (!fullText || fullText.length <= word.length) return null;
  const hit = findWordInText(fullText, word);
  if (!hit) return null;
  const sentence = expandToSentence(fullText, hit.idx, hit.len);
  if (sentence.length <= word.length) return null;
  if (!isPlausibleSentence(sentence)) {
    console.log(`[overlay] context: ${source} rejected as implausible (${sentence.length} chars) — degrading to word-only`);
    return null;
  }
  console.log(`[overlay] context: ${source} → ${sentence.length} chars`);
  return sentence;
}

module.exports = { expandToSentence, findWordInText, isPlausibleSentence, contextFromText };
