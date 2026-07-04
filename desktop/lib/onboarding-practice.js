// Keep in sync with the .sample block in onboarding.html (step 3).
const PRACTICE_SENTENCE =
  'He smiled with a warmth that, she would later realize, was entirely adventitious.';

function practiceContextFor(word) {
  const w = (word || '').trim().replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, '');
  if (!w) return null;
  return PRACTICE_SENTENCE.toLowerCase().includes(w.toLowerCase()) ? PRACTICE_SENTENCE : null;
}

module.exports = { PRACTICE_SENTENCE, practiceContextFor };