"""
works.py — author/work-specific landing pages for SEO long-tail.

Each work is a substantial hub page that targets specific student
searches ("hamlet themes", "great gatsby symbolism") and links
heavily back to glossary.py entries.
"""
from __future__ import annotations
from html import escape

import glossary as _glossary


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────

WORKS: list[dict] = [
    {
        "slug": "hamlet",
        "title": "Hamlet — A Reader's Guide to Shakespeare's Vocabulary and Concepts",
        "h1": "Hamlet — concepts, vocabulary, and themes",
        "author": "William Shakespeare",
        "year": "c. 1600",
        "meta_description": "A reader's guide to the concepts, vocabulary, and themes of Shakespeare's Hamlet — melancholy, hamartia, soliloquy, dramatic irony, and more, with deep links to in-context explanations.",
        "updated": "2026-05-20",
        "body_html": """
<p><em>Hamlet</em> is the most studied play in the English language,
and also the most misread — partly because so many of its central
concepts are technical terms from Greek tragedy or Renaissance
psychology that students encounter without explanation. This page
collects the vocabulary you actually need to read the play closely,
with links to in-depth essays on each concept.</p>

<h2>The tragic vocabulary</h2>

<p>Hamlet is a revenge tragedy that consciously inherits from Greek
tragic theory. To read it well, you need a working sense of three
Aristotelian terms:</p>

<ul>
  <li><a href="/glossary/hamartia"><strong>Hamartia</strong></a> —
      the tragic flaw or fatal error. What is Hamlet's? Critics
      have argued for centuries: indecision, melancholy, an excess
      of reflection, an inability to act without certainty. The
      concept gives you a way to ask the question precisely.</li>
  <li><a href="/glossary/hubris"><strong>Hubris</strong></a> —
      contemptuous overreach. Claudius's hubris is more obvious
      than Hamlet's; Hamlet's is more complicated.</li>
  <li><a href="/glossary/catharsis-greek-tragedy"><strong>Catharsis</strong></a>
      — the emotional purgation Aristotle claimed tragedy
      produced. The play's ending — five corpses on stage — is
      one of the most contested cathartic moments in the canon.</li>
  <li><a href="/glossary/anagnorisis"><strong>Anagnorisis</strong></a>
      — the recognition. The moment Hamlet truly understands his
      situation, or Claudius understands his exposure, is the
      play's anagnorisis.</li>
  <li><a href="/glossary/peripeteia"><strong>Peripeteia</strong></a>
      — the reversal of fortune. The Mousetrap scene, the
      bedchamber confrontation, the duel — Hamlet pivots
      repeatedly on peripeteia.</li>
</ul>

<h2>Melancholy and the Renaissance mind</h2>

<p>Hamlet's "melancholy" is not modern depression. It is a specific
Renaissance medical category, rooted in the theory of the four
humors. Read <a href="/glossary/melancholy-hamlet">what melancholy
meant in Shakespeare's England</a> — it is a creative, intellectual,
brooding temperament associated with artists and scholars, but
also pathological in excess. Hamlet inhabits this concept the way
Romeo inhabits love-melancholy or Falstaff inhabits the sanguine.</p>

<h2>The soliloquies</h2>

<p>Hamlet has seven <a href="/glossary/soliloquy"><strong>soliloquies</strong></a>,
including "To be, or not to be" — the most quoted speech in English.
Each is a window into the character's interior. The soliloquy is
not the same as a monologue; it is a speech alone, addressed
essentially to the self, with the audience as eavesdropper. This
convention is what allows Shakespeare to give us such complete
access to Hamlet's mind.</p>

<h2>The play of irony</h2>

<p>Hamlet is saturated with <a href="/glossary/dramatic-irony"><strong>dramatic
irony</strong></a> — the gap between what characters know and what
we know. From the moment we hear Claudius's confession in Act III,
Hamlet's hesitation acquires a particular kind of pathos: we know
he is right; we know revenge is justified; and we watch him fail
to act. The irony cuts both ways: Claudius lives, but he lives
knowing he is exposed.</p>

<h2>Rhetorical devices to watch for</h2>

<p>Shakespeare's verse is a workshop of figures. Some you'll meet
repeatedly in Hamlet:</p>

<ul>
  <li><a href="/glossary/paradox-oxymoron"><strong>Paradox and
      oxymoron</strong></a> — Hamlet thinks in contradictions. "I
      must be cruel only to be kind" is a paradox; "wicked wit"
      is an oxymoron. The play's mental life is built out of
      collisions.</li>
  <li><a href="/glossary/chiasmus"><strong>Chiasmus</strong></a> —
      the ABBA reversal. "Conscience does make cowards of us all"
      is an inversion of the expected order; the play loves
      these structural flips.</li>
  <li><a href="/glossary/apostrophe-figure"><strong>Apostrophe</strong></a>
      — Hamlet addresses Yorick's skull, addresses the ghost,
      addresses absent or dead persons. The figure is
      everywhere.</li>
  <li><a href="/glossary/anaphora"><strong>Anaphora</strong></a> —
      repetition at the start of clauses. "To die — to sleep — /
      To sleep — perchance to dream" uses anaphoric structure to
      build the soliloquy's pace.</li>
</ul>

<h2>Structural concepts</h2>

<p><a href="/glossary/iambic-pentameter"><strong>Iambic
pentameter</strong></a> is the verse Shakespeare uses for most of
Hamlet's elevated speech. The prose passages — the gravediggers,
some of Hamlet's exchanges with Polonius — mark shifts of register.
Notice when Hamlet drops out of verse: it is usually for satire,
contempt, or madness (real or feigned).</p>

<p><a href="/glossary/blank-verse"><strong>Blank verse</strong></a>
— unrhymed iambic pentameter — is the play's basic medium. The
absence of rhyme makes the meter feel speakable rather than
artificial.</p>

<h2>Critical concepts useful for essays</h2>

<p><a href="/glossary/objective-correlative"><strong>The objective
correlative</strong></a> — T. S. Eliot's famous (and controversial)
charge against the play. Eliot argued that Hamlet's emotion
exceeds the objective situation, making the play an artistic
failure. Whether or not you accept the charge, the concept gives
you a tool for asking how Shakespeare matches feeling to event.</p>

<p><a href="/glossary/negative-capability"><strong>Negative
capability</strong></a> — Keats's idea, formulated with Shakespeare
as the model. Hamlet's ability to remain in uncertainty rather
than reaching after fact and reason is Keats's example of what
the poetic mind can do. Hamlet's hesitation, on this view, is
not a flaw but a kind of cognitive achievement.</p>

<h2>The play as a whole</h2>

<p>Reading Hamlet well means holding two things at once: the
play's specific Renaissance and classical inheritances, and the
ways it has been re-read across four centuries — by Freudian
critics, by feminist critics, by the philosopher Stanley Cavell,
by the actor Olivier and the director Almereyda. The vocabulary
on this page won't settle any of those readings, but it will let
you participate in them with precision.</p>
""",
        "related_works": ["great-gatsby"],
        "key_entries": [
            "hamartia", "melancholy-hamlet", "soliloquy",
            "catharsis-greek-tragedy", "dramatic-irony",
            "negative-capability", "objective-correlative",
        ],
    },
    {
        "slug": "great-gatsby",
        "title": "The Great Gatsby — Symbolism, Motifs, and Key Concepts Explained",
        "h1": "The Great Gatsby — symbolism, motifs, and themes",
        "author": "F. Scott Fitzgerald",
        "year": "1925",
        "meta_description": "A reader's guide to The Great Gatsby — the green light, the eyes of T.J. Eckleburg, motifs of water and color, the unreliable narrator, and the central theme of the failed American dream.",
        "updated": "2026-05-20",
        "body_html": """
<p><em>The Great Gatsby</em> is one of the most carefully built
American novels — every detail repeated, every color significant,
every casual remark eventually weighted with meaning. To read it
well, you need a working vocabulary for what symbols, motifs, and
narrative voice are doing. This page collects the central
concepts, with links to deeper essays on each.</p>

<h2>Symbol vs. motif: getting the levels right</h2>

<p>Students often confuse <a href="/glossary/allegory-vs-symbol"><strong>symbols</strong></a>
with <a href="/glossary/motif"><strong>motifs</strong></a>. Both are
recurring elements, but they operate differently:</p>

<ul>
  <li>A <strong>symbol</strong> stands for something else — the
      green light "means" something Gatsby is reaching for: hope,
      Daisy, the future, the American dream.</li>
  <li>A <strong>motif</strong> is a pattern of recurrence that
      accumulates meaning through repetition rather than direct
      reference. Water in Gatsby is a motif: it doesn't "mean"
      one thing, but it returns in so many forms (the bay, the
      pool, the rain at the reunion, the fountain in West Egg)
      that it becomes part of the novel's thematic texture.</li>
</ul>

<p>Don't write "the motif of the green light" — the green light is
a <em>symbol</em>. Don't write "the symbol of water" — water is
a <em>motif</em>. Get the <a href="/glossary/theme-vs-motif">levels
right</a> and your analysis sharpens immediately.</p>

<h2>The famous symbols</h2>

<p><strong>The green light</strong> at the end of Daisy's dock is
the novel's most discussed image. It is at once geographically
literal (Gatsby can see it from across the bay), psychologically
specific (it is what Gatsby reaches toward), and culturally
expansive (it becomes, in the final paragraph, the "orgastic
future" that recedes from us all).</p>

<p><strong>The eyes of Doctor T. J. Eckleburg</strong> — a faded
billboard for an oculist's practice — preside over the valley of
ashes. The eyes have been read as God watching America, as the
emptiness behind apparent observation, as the watchfulness of
the dead. Their power is that they observe without judging — a
sterile gaze that mirrors the moral landscape they overlook.</p>

<p><strong>The valley of ashes</strong> — the wasteland between
West Egg and New York — is the novel's symbolic underworld. It
is what the parties produce, what the rich don't see, where the
moral consequences accumulate. The Eliotic resonance is direct:
<a href="/glossary/wasteland-eliot">Eliot's Waste Land</a> was
published three years before Gatsby, and Fitzgerald owed the
imagery.</p>

<h2>The motifs</h2>

<ul>
  <li><strong>Water</strong> — the bay, the pool, the rain at the
      Gatsby-Daisy reunion, the fountain. Water marks moments of
      attempted transformation; Gatsby's failure to recover the
      past is concentrated, finally, in the pool where he dies.</li>
  <li><strong>Colors</strong> — green (the light, Gatsby's car
      seat), yellow / gold (Gatsby's car, Daisy's voice "full of
      money"), white (Daisy, the Buchanans' house), grey (the
      valley of ashes). Each color clusters around specific moral
      associations.</li>
  <li><strong>Eyes / watching</strong> — Eckleburg, Owl-Eyes at
      the funeral, the constant act of looking and being looked
      at. Visibility is the novel's central social anxiety.</li>
  <li><strong>Clocks and time</strong> — Gatsby knocks over the
      clock at the reunion. The novel is, at its center, about the
      impossibility of going back. Time is the antagonist.</li>
</ul>

<h2>Narrative voice: Nick Carraway</h2>

<p>Nick is a famously slippery <a href="/glossary/unreliable-narrator"><strong>narrator</strong></a>.
He claims, in the opening pages, to be "inclined to reserve all
judgments" — and then judges everyone, often harshly. He claims
honesty and is repeatedly evasive. The novel's first-person
narration is one of its most carefully constructed devices: we
are reading Nick reading Gatsby, with all the partiality that
implies.</p>

<p>The narration also uses <a href="/glossary/free-indirect-discourse"><strong>free
indirect discourse</strong></a> — Nick's voice merging with the
voices of characters he describes, particularly Gatsby. The
famous final paragraphs slip from Nick's first person into a
"we" that becomes universal.</p>

<h2>The theme of the failed dream</h2>

<p>The novel's central theme — usually stated as "the corruption
of the American dream" — is not stated by Fitzgerald in those
words. The reader assembles it from accumulating motifs: the
green light's recession, the wealth that doesn't satisfy, the
valley of ashes that the parties produce, the original Dutch
settlers' "fresh, green breast of the new world" that has been
flattened by the East. Notice that this is how a <a href="/glossary/theme-vs-motif">theme</a>
works — it is the abstract claim the motifs develop, not a thing
you can point to in the text.</p>

<h2>Structural concepts</h2>

<p><a href="/glossary/in-medias-res"><strong>In medias res</strong></a>
— the novel does not begin at the beginning of Gatsby's story but
in the middle, with Nick's arrival in West Egg. Gatsby's history
is revealed in fragments, out of order. This is part of why the
novel rewards rereading: on a second pass, every detail is
already inflected by what we know about what's coming.</p>

<p><a href="/glossary/foreshadowing"><strong>Foreshadowing</strong></a>
is one of the novel's signatures. The death of Myrtle, Gatsby's
death, the dissolution of the marriages — all are subtly
prefigured. The first sentence Gatsby speaks to Nick contains a
sentimental gesture that already announces the man's whole
posture toward the world.</p>

<h2>Rhetorical figures</h2>

<p>The novel's famous closing image — "boats against the current,
borne back ceaselessly into the past" — is metaphor of historical
inevitability. Throughout the novel, Fitzgerald uses
<a href="/glossary/simile-vs-metaphor">metaphor</a> with great
precision. Notice when he uses <a href="/glossary/simile-vs-metaphor">simile</a>
versus metaphor — the difference matters for tone.</p>

<p><a href="/glossary/hyperbole"><strong>Hyperbole</strong></a>
animates the descriptions of Gatsby's parties: the orchestra has
"oboes and trombones and saxophones and viols and cornets and
piccolos, and low and high drums." The cataloguing
(<a href="/glossary/asyndeton-polysyndeton">polysyndeton</a>) is
itself a form of exaggeration.</p>
""",
        "related_works": ["hamlet"],
        "key_entries": [
            "motif", "theme-vs-motif", "allegory-vs-symbol",
            "unreliable-narrator", "free-indirect-discourse",
            "foreshadowing", "wasteland-eliot",
        ],
    },
]

_BY_SLUG: dict[str, dict] = {w["slug"]: w for w in WORKS}


def get(slug: str) -> dict | None:
    return _BY_SLUG.get(slug)


def all_works() -> list[dict]:
    return list(WORKS)


# ─────────────────────────────────────────────────────────────────────────────
# Rendering
# ─────────────────────────────────────────────────────────────────────────────

def render_work(work: dict) -> str:
    """Render a single work page. Reuses glossary.py styling and head."""
    canonical = f"https://lexio.site/works/{work['slug']}"
    head = _glossary._head(work["title"], work["meta_description"], canonical)

    import json as _json
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "headline": work["title"],
                "description": work["meta_description"],
                "url": canonical,
                "dateModified": work["updated"],
                "about": {
                    "@type": "Book",
                    "name": work["title"].split(" — ")[0],
                    "author": {"@type": "Person", "name": work["author"]},
                },
                "publisher": {
                    "@type": "Organization",
                    "name": "Lexio",
                    "logo": {"@type": "ImageObject", "url": "https://lexio.site/favicon-512.png"},
                },
                "mainEntityOfPage": canonical,
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Lexio", "item": "https://lexio.site/"},
                    {"@type": "ListItem", "position": 2, "name": "Works", "item": "https://lexio.site/works"},
                    {"@type": "ListItem", "position": 3, "name": work["title"].split(" — ")[0], "item": canonical},
                ],
            },
        ],
    }
    jsonld_tag = f'<script type="application/ld+json">{_json.dumps(jsonld, ensure_ascii=False)}</script>'

    # Build related-entries block from key_entries
    related_items = []
    for slug in work.get("key_entries", []):
        e = _glossary._BY_SLUG.get(slug)
        if not e:
            continue
        related_items.append(f"""
        <a class="related-item" href="/glossary/{escape(e['slug'])}">
          <div class="related-item-term">{escape(e['term'])}</div>
          <div class="related-item-context">in {escape(e['context'])}</div>
        </a>""")
    related_block = ""
    if related_items:
        related_block = f"""
  <div class="related">
    <div class="related-title">Key glossary entries</div>
    <div class="related-list">{''.join(related_items)}</div>
  </div>"""

    return f"""{head}
<body>
{jsonld_tag}
<div class="wrap">
  <a class="back" href="/glossary">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
    Glossary
  </a>

  <span class="logo">Le<em>x</em>io</span>
  <nav class="breadcrumb" aria-label="Breadcrumb">
    <a href="/">Home</a> &nbsp;›&nbsp; <a href="/works">Works</a> &nbsp;›&nbsp; {escape(work['title'].split(' — ')[0])}
  </nav>
  <h1>{escape(work['h1'])}</h1>
  <p class="term-context"><em>{escape(work['author'])}</em> · {escape(work['year'])}</p>

  {work['body_html']}

  {related_block}

  {_glossary._cta_block()}

  <p class="closing">
    <em>Read deeper. Understand everything.</em><br>
    © 2026 Lexio · <a href="/privacy.html">Privacy</a> · <a href="/credits.html">Credits</a>
  </p>
</div>
</body>
</html>
"""


def render_index() -> str:
    """Hub page listing all works at /works."""
    canonical = "https://lexio.site/works"
    head = _glossary._head(
        "Lexio — Reader's Guides to Major Works",
        "In-depth guides to the vocabulary, themes, and concepts of major works of literature — Hamlet, The Great Gatsby, and more.",
        canonical,
    )

    cards = []
    for w in WORKS:
        cards.append(f"""
    <a class="entry-card" href="/works/{escape(w['slug'])}">
      <div class="entry-card-term">{escape(w['title'].split(' — ')[0])}</div>
      <div class="entry-card-context">{escape(w['author'])} · {escape(w['year'])}</div>
      <div class="entry-card-desc">{escape(w['meta_description'])}</div>
    </a>""")

    return f"""{head}
<body>
<div class="wrap-wide">
  <a class="back" href="/">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
    Back to Lexio
  </a>

  <span class="logo">Le<em>x</em>io</span>
  <h1>Reader's guides</h1>
  <p class="intro">Substantial reader's guides to major works of literature — vocabulary, themes, and concepts, with links to in-depth glossary entries.</p>

  <div class="entry-grid">{''.join(cards)}</div>

  <p class="closing">
    <em>Read deeper. Understand everything.</em><br>
    © 2026 Lexio · <a href="/privacy.html">Privacy</a> · <a href="/credits.html">Credits</a>
  </p>
</div>
</body>
</html>
"""
