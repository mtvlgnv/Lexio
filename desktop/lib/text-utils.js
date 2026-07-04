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

function contextFromText(fullText, word, source) {
  if (!fullText || fullText.length <= word.length) return null;
  const hit = findWordInText(fullText, word);
  if (!hit) return null;
  const sentence = expandToSentence(fullText, hit.idx, hit.len);
  if (sentence.length <= word.length) return null;
  console.log(`[overlay] context: ${source} → ${sentence.length} chars`);
  return sentence;
}

module.exports = { expandToSentence, findWordInText, contextFromText };