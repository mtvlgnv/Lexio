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

    # ─────────────────────────────────────────────────────────────────────
    {
        "slug": "1984",
        "title": "1984 — A Reader's Guide to Orwell's Dystopian Vocabulary",
        "h1": "1984 — themes, vocabulary, and concepts",
        "author": "George Orwell",
        "year": "1949",
        "meta_description": "A reader's guide to George Orwell's 1984 — dystopia, doublethink, Newspeak, Big Brother, totalitarianism, and the politics of language, with deep links to in-context explanations.",
        "updated": "2026-05-25",
        "body_html": """
<p>Orwell's <em>Nineteen Eighty-Four</em> is the most-cited novel
of the twentieth century, and the most-misused. Its vocabulary —
<em>Big Brother</em>, <em>Newspeak</em>, <em>doublethink</em>,
<em>thoughtcrime</em>, <em>memory hole</em> — escaped the book
and became everyday political slang, which means most readers meet
the words long before they meet the novel. This guide reverses
that order. Below, the technical concepts you need to read the
book closely, with internal links to in-depth glossary entries.</p>

<h2>The genre: dystopia</h2>

<p>Orwell's London is the canonical <a href="/glossary/dystopia">
<strong>dystopia</strong></a> — a society organized to maximize
control, conformity, and dehumanization. The genre's structural
features all appear here: total surveillance, the corruption of
language, an engineered conformity backed by violence, a
protagonist who senses the cage. Reading the novel as a dystopia
rather than a political pamphlet keeps the literary mechanics
visible. Orwell is not predicting the future; he is exaggerating
his present (Stalinism, BBC propaganda, the wartime British state)
into an argument.</p>

<h2>The Party's vocabulary</h2>

<p>The Party's invented words are the novel's technical core. Each
is a small, perfectly-engineered piece of mind-control:</p>

<ul>
  <li><strong>Newspeak</strong> — the contracted, ideologically
      purified version of English the Party is replacing
      "Oldspeak" with. Its purpose is not communication but the
      foreclosure of thought: if there is no word for freedom, the
      concept cannot be formulated. The Appendix on Newspeak is
      essential reading for anyone interested in the
      <a href="/glossary/dystopia">corruption of language</a> as a
      genre feature.</li>
  <li><strong>Doublethink</strong> — the simultaneous holding of
      two contradictory beliefs, knowing them to be contradictory,
      and believing both. The classic literary form of
      <a href="/glossary/paradox-oxymoron">paradox</a>, weaponized
      into a discipline of political obedience.</li>
  <li><strong>Thoughtcrime</strong> — the crime of unauthorized
      thought, prosecutable before any action. The implicit claim:
      that the state's reach extends to interiority itself.</li>
  <li><strong>Memory hole</strong> — the chute into which
      inconvenient documents are dropped to be incinerated. Memory
      is the second front of the war; the Party's slogan
      "Who controls the past controls the future" is its
      operational creed.</li>
</ul>

<h2>The slogans as paradox</h2>

<p>The Party's three slogans — <em>War is Peace. Freedom is
Slavery. Ignorance is Strength.</em> — are textbook examples of
<a href="/glossary/paradox-oxymoron"><strong>paradox</strong></a>.
Each line yokes together opposites, and each one names a
mechanism: perpetual war creates social peace by displacing
internal conflict; submission to the Party is reframed as freedom
from individual responsibility; controlled ignorance is what gives
the state its strength. The novel doesn't argue that the slogans
are wrong; it argues that they describe how the Party actually
works.</p>

<h2>Satire vs. prophecy</h2>

<p>Critics still debate whether <em>1984</em> is
<a href="/glossary/satire-vs-parody"><strong>satire</strong></a> or
prophecy. Orwell himself called it a warning: "I do not believe
that the kind of society I describe necessarily <em>will</em>
arrive, but I believe… that something resembling it <em>could</em>
arrive." The book is closer to satire in the eighteenth-century
sense (Swift, not <em>The Daily Show</em>) — it works by
exaggerating tendencies the author observed in his own moment
until they become impossible to ignore.</p>

<h2>The novel's structural devices</h2>

<p>The book is built on a few sustained literary devices:</p>

<ul>
  <li><a href="/glossary/foreshadowing"><strong>Foreshadowing</strong></a>
      is constant. Winston's first diary entry, his recurring dream
      of his mother, the glass paperweight, the song about the
      "lemon-tree" — every detail will return, transformed by what
      we learn in Part Three.</li>
  <li><a href="/glossary/dramatic-irony"><strong>Dramatic
      irony</strong></a> pervades the second part: the reader
      suspects what Winston refuses to consider — that O'Brien is
      not what he seems, that the room above the antique shop is
      bugged.</li>
  <li><a href="/glossary/in-medias-res"><strong>In medias res</strong></a>
      — the novel opens with Winston already a heretic, already
      drafting his diary, already in love with Julia in some
      latent sense. We never see the world before Big Brother.</li>
  <li>The interpolated <strong>Book within the Book</strong>
      (Goldstein's <em>Theory and Practice of Oligarchical
      Collectivism</em>) functions as a
      <a href="/glossary/mise-en-abyme">mise en abyme</a> — a small
      version of the novel's argument embedded inside the novel,
      and Orwell's mechanism for delivering the political theory
      without breaking character.</li>
</ul>

<h2>The themes</h2>

<p>The novel's themes (as opposed to its
<a href="/glossary/theme-vs-motif">motifs</a>):</p>

<ul>
  <li><strong>Language as political infrastructure.</strong> The
      reason the Party rewrites the dictionary is the same reason
      it rewrites the newspapers: thought runs on language; restrict
      one and you restrict the other.</li>
  <li><strong>Memory as resistance.</strong> Winston's diary, his
      private rituals, his attempt to remember his mother — the
      protagonist's small heresy is the act of holding the past
      against the Party's revisions.</li>
  <li><strong>The death of objective truth.</strong> Orwell's
      deepest political fear, articulated in his essays as well as
      the novel, is not that totalitarianism will be cruel but that
      it will make truth itself unstable.</li>
  <li><strong>The intimacy of the state.</strong> The Two Minutes
      Hate, the youth groups, the apartment telescreens, the final
      betrayal in Room 101 — the state's victory is total because
      it reaches into the most intimate corners of the self.</li>
</ul>

<h2>The ending</h2>

<p>The novel ends with Winston, broken, looking at the portrait
of Big Brother and feeling that he "loved Big Brother." Read this
as <a href="/glossary/dramatic-irony">dramatic irony</a>: we are
not asked to admire the resolution; we are asked to register the
horror of a man whose interior has been refurnished by the state.
The Appendix on Newspeak, written in the past tense, has been
read since the 1980s as Orwell's quiet hint that the regime
eventually fell — but the novel itself ends in defeat.</p>
""",
        "related_works": ["great-gatsby", "hamlet"],
        "key_entries": [
            "dystopia", "paradox-oxymoron", "satire-vs-parody",
            "foreshadowing", "dramatic-irony", "mise-en-abyme",
            "in-medias-res", "theme-vs-motif",
        ],
    },

    # ─────────────────────────────────────────────────────────────────────
    {
        "slug": "frankenstein",
        "title": "Frankenstein — A Reader's Guide to Mary Shelley's Gothic Romanticism",
        "h1": "Frankenstein — themes, vocabulary, and structure",
        "author": "Mary Shelley",
        "year": "1818",
        "meta_description": "A reader's guide to Mary Shelley's Frankenstein — Gothic fiction, the sublime, the Promethean myth, frame narrative, pathetic fallacy, and Romanticism's anxieties about science.",
        "updated": "2026-05-25",
        "body_html": """
<p>Mary Shelley's <em>Frankenstein</em> is two novels at once: a
Gothic horror story and a Romantic meditation on creation,
responsibility, and the natural sublime. Read it as only the
first and you miss most of the book; read it as only the second
and you miss the engine. This guide collects the technical
vocabulary that lets both registers come into focus.</p>

<h2>The genre: Gothic fiction</h2>

<p>The novel is a foundational text of
<a href="/glossary/gothic-fiction"><strong>Gothic fiction</strong></a> —
the genre of ruined castles, lonely landscapes, transgressive
knowledge, doubled identities, and the return of the repressed.
The Gothic stock characters and settings are all here: the
overreaching scientist as a secular Faust, the isolated mountain
laboratory, the wandering double, the woman as victim of male
ambition. But Shelley's novel is also one of the genre's first
self-conscious extensions — pushing Gothic from supernatural
horror into the territory of secular science.</p>

<h2>The Romantic sublime</h2>

<p>Read Shelley's descriptions of Mont Blanc, the icy ravines, the
storm-lashed Orkneys: these are textbook instances of
<a href="/glossary/sublime-in-romanticism"><strong>the
Romantic sublime</strong></a>. The sublime is not pretty; it is
the aesthetic experience of being dwarfed by something — a
mountain, a storm, an idea — and finding in that dwarfing both
terror and elevation. Victor's wanderings through the Alps and
the Arctic are not scenic backdrops; they are the novel's
emotional centre. The Creature, too, encounters and articulates
the sublime — one of the small details that complicates the
"monster" reading.</p>

<h2>The structure: frame narrative</h2>

<p>The novel is one of the great Gothic
<a href="/glossary/frame-narrative"><strong>frame narratives</strong></a>.
Walton's letters to his sister contain Victor's first-person
account, which itself contains the Creature's first-person account,
which itself quotes (in his self-education) <em>Paradise Lost</em>,
<em>The Sorrows of Young Werther</em>, and Plutarch. Each layer
reframes what came before. By the time we hear Walton's voice
again at the end, the moral economy of the book is so layered
that no single character can deliver the verdict — and Shelley
declines to.</p>

<h2>Pathetic fallacy and the Romantic landscape</h2>

<p>Shelley uses <a href="/glossary/pathetic-fallacy"><strong>pathetic
fallacy</strong></a> with deliberate intensity — the weather
mirrors Victor's psychological state at almost every turn. The
storm on the night the Creature is animated, the lightning over
the Alps, the polar ice that closes both Victor's and Walton's
narratives: nature is not background, it is a participant. This
is fully Romantic — Wordsworth and Shelley's husband would have
recognized every move.</p>

<h2>The Promethean theme: hubris and its costs</h2>

<p>The novel's subtitle is <em>The Modern Prometheus</em>. Read
through that frame, Victor's tragedy is one of
<a href="/glossary/hubris"><strong>hubris</strong></a> — the
mortal who reaches for divine prerogatives and is punished. But
Shelley is not simply moralizing against ambition. The book is
also a critique of <em>irresponsibility</em>: Victor's worse
crime is not making the Creature; it is abandoning it. The
ambition is dangerous; the abandonment is what produces the
horror.</p>

<h2>The double / doppelgänger</h2>

<p>Victor and the Creature are doubles — antithetical and
inseparable. Victor's ambition produces the Creature; the
Creature's loneliness mirrors Victor's; their final pursuit
across the Arctic blurs the question of who is hunting whom.
Gothic fiction loves the double, but Shelley's version is more
philosophically charged than most. The Creature is not Victor's
opposite; he is Victor's externalized conscience, and the novel
won't let us forget it.</p>

<h2>The Creature's vocabulary</h2>

<p>The Creature speaks more articulately than Victor — and his
articulacy is one of the book's most disorienting features. He
self-educates by overhearing the De Lacey family and by reading
<em>Paradise Lost</em>, identifying first with Adam ("a being
formed... and brought into the world by a creator") and then,
more bitterly, with Satan ("I am rather the fallen angel"). The
Creature's literary references are how Shelley signals that the
novel is participating in a long Romantic argument about
creation, responsibility, and the limits of sympathy.</p>

<h2>Themes worth tracking</h2>

<ul>
  <li><strong>The cost of unmonitored ambition.</strong> Victor's
      science has no community, no oversight, no shared discourse
      — the Romantic critique of Enlightenment individualism.</li>
  <li><strong>The making of the monster.</strong> The Creature is
      not born monstrous; he is made so by rejection. Shelley's
      argument anticipates twentieth-century sociology by a
      century and a half.</li>
  <li><strong>Knowledge and its limits.</strong> Both Walton (in
      his letters) and Victor (in his cautionary speech) frame the
      book as a warning against the pursuit of knowledge "in
      forbidden things." Whether Shelley endorses or critiques
      this framing is still debated.</li>
  <li><strong>Family, abandonment, and creation.</strong> Read
      biographically — Shelley's mother died days after her birth;
      Shelley's daughter died in infancy weeks before composition
      began — and the novel becomes a meditation on what creators
      owe what they create.</li>
</ul>
""",
        "related_works": ["hamlet"],
        "key_entries": [
            "gothic-fiction", "sublime-in-romanticism", "frame-narrative",
            "hubris", "pathetic-fallacy", "bildungsroman-genre",
            "uncanny-literature",
        ],
    },

    # ─────────────────────────────────────────────────────────────────────
    {
        "slug": "to-kill-a-mockingbird",
        "title": "To Kill a Mockingbird — A Reader's Guide to Harper Lee's Novel",
        "h1": "To Kill a Mockingbird — themes, narration, and symbols",
        "author": "Harper Lee",
        "year": "1960",
        "meta_description": "A reader's guide to Harper Lee's To Kill a Mockingbird — the bildungsroman frame, Scout's unreliable narration, the mockingbird as symbol, Southern Gothic, dramatic irony.",
        "updated": "2026-05-25",
        "body_html": """
<p>Harper Lee's <em>To Kill a Mockingbird</em> is read most often
as a novel about race and justice — which it is — but the literary
machinery underneath is more interesting than the moral lesson
usually pulled out of it. Three formal features in particular
deserve attention: it is a
<a href="/glossary/bildungsroman-genre">bildungsroman</a>, it has
a sophisticated double-perspective narrator, and its central
symbol is doing more work than the title lets on.</p>

<h2>The genre: bildungsroman</h2>

<p>The novel is a coming-of-age story — a classical
<a href="/glossary/bildungsroman-genre"><strong>bildungsroman</strong></a>
in the strict sense. Scout begins the novel as a young child with
inherited prejudices and a child's brand of moral certainty; by
the end she has been changed — not converted, but expanded — by
the events around her. The trial of Tom Robinson, the death of
Mrs. Dubose, the discovery of Boo Radley as a person rather than
a legend: each is an episode in the formation of a moral
sensibility. The novel respects the slowness of that formation.
Scout doesn't have an epiphany; she accumulates one, scene by
scene.</p>

<h2>The double narrator</h2>

<p>Scout is one of the most carefully constructed first-person
narrators in American fiction. The book is told retrospectively
by an adult Scout looking back at her child self — which gives
Lee two voices simultaneously. The child's voice carries the
immediacy and partial understanding; the adult's voice supplies
the framing, the irony, and the diction the child could not have
commanded. This is also why the narrator is, in the strict sense,
<a href="/glossary/unreliable-narrator"><strong>unreliable</strong></a>
— not because she lies, but because the child Scout cannot fully
read the world she is reporting on, and the adult Scout is
selecting what to remember.</p>

<h2>Dramatic irony</h2>

<p>The double-perspective narrator produces sustained
<a href="/glossary/dramatic-irony"><strong>dramatic
irony</strong></a>: we, the adult readers, understand things
about the situation — the racial dynamics of Maycomb, the legal
foregone conclusion, the cost Atticus is bearing — that Scout
the child does not yet understand. Some of the novel's most
moving moments turn on this gap. Scout's bewilderment in the
courtroom is not naïveté; it is the device by which Lee makes us
see the situation freshly.</p>

<h2>The mockingbird as symbol</h2>

<p>The mockingbird is the novel's central
<a href="/glossary/allegory-vs-symbol"><strong>symbol</strong></a>
— and it is doing more work than the title's moral epigraph
suggests. "It's a sin to kill a mockingbird," Atticus says,
because mockingbirds "don't do one thing but make music for us
to enjoy." Two figures in the novel are explicitly aligned with
mockingbirds: Tom Robinson, an innocent destroyed by a community
that refused to listen; and Boo Radley, an innocent feared by a
community that refused to know him. The symbol's range is broad
because the harm the novel anatomizes is broad — wherever
innocence is destroyed because the destroyer cannot recognize it.</p>

<h2>The novel's motifs</h2>

<p>Several recurring images and patterns — what we'd call
<a href="/glossary/theme-vs-motif">motifs</a> — develop the
novel's themes without quite stating them:</p>

<ul>
  <li><strong>Boundaries and crossing them.</strong> The Radley
      property, the courthouse balcony segregation, the racial
      and class lines of Maycomb. Scout's growth is partly a
      growing awareness of which lines have been drawn around her.</li>
  <li><strong>Sight and being seen.</strong> Boo Radley is
      compulsively watched and never seen; Tom Robinson is seen
      but not heard; Atticus insists on the importance of "climbing
      into another person's skin." The novel is a meditation on
      whose perception counts.</li>
  <li><strong>The children's games.</strong> Scout, Jem, and Dill
      enact Boo Radley's life as a play; the reenactment is both
      a child's way of metabolizing fear and a small model of how
      Maycomb mythologizes its outsiders.</li>
  <li><strong>Mad dogs, rabid creatures.</strong> The mad dog
      Atticus shoots is the novel's most famous set piece, and
      one of its clearest figurative scenes — the disease is also
      the racism eating Maycomb.</li>
</ul>

<h2>Atticus and the moral centre</h2>

<p>Atticus Finch has been read as the moral hero of American
fiction and, since the publication of <em>Go Set a Watchman</em>
in 2015, as something more complicated. Read the novel itself
without that complication: Atticus is the moral centre of Scout's
upbringing — a parent who refuses to lie to his children, takes
the case he is asked to take, and is defeated. Lee's deeper claim
is not that Atticus wins, but that he stays human while losing.
That moral claim is what the symbolic mockingbird is finally
asking us to see.</p>

<h2>The Southern Gothic frame</h2>

<p>Although the novel is rarely classed as Gothic, it borrows
heavily from the Southern Gothic tradition — Boo Radley as the
spectral figure behind shuttered windows, the Radley house as the
local haunted place, the racial violence as a kind of regional
curse. Lee uses these Gothic conventions and then revises them:
the spectral figure turns out to be the novel's quiet saviour.
The genre's expectations are set up to be reversed.</p>

<h2>The ending</h2>

<p>The novel ends with Scout walking Boo Radley home and standing
on his porch — and, for the first time, seeing the street from
his point of view. "You never really know a man," Atticus has
said, "until you stand in his shoes and walk around in them."
Scout's standing on Boo's porch is the novel's
<a href="/glossary/dramatic-irony">quiet, undeclared
climax</a> — Scout has done the thing her father asked her to do.
The bildungsroman closes with the recognition that completes it.</p>
""",
        "related_works": ["great-gatsby"],
        "key_entries": [
            "bildungsroman-genre", "unreliable-narrator", "dramatic-irony",
            "allegory-vs-symbol", "theme-vs-motif", "gothic-fiction",
            "foreshadowing",
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
