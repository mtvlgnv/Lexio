"""
Lexio Glossary — SEO long-tail content pages.

Each entry targets a real search like "what does [word] mean in [book]".
The pages are rendered server-side from this module, so adding a new entry
is just appending a dict to ENTRIES.

Internal contract per entry:
    slug             : URL slug (kebab-case)
    term             : the word/phrase being defined
    context          : short context line ("Baudelaire's poetry")
    title            : <title> tag content (no site suffix; we append " — Lexio")
    meta_description : <meta description> (target ~150–160 chars)
    h1               : <h1> page heading
    body_html        : main article body (already-rendered HTML; safe to embed)
    related          : list of slugs for the "Related entries" footer
    updated          : YYYY-MM-DD (used as <lastmod>)
"""

from __future__ import annotations
from typing import Iterable
from html import escape


# ── Entries ──────────────────────────────────────────────────────────────────
# Add a new entry by appending a dict here — the index page, sitemap, and
# per-entry routes pick it up automatically.

ENTRIES: list[dict] = [
    # ──────────────────────────────────────────────────────────────────────
    {
        "slug": "spleen-baudelaire",
        "term": "spleen",
        "context": "Baudelaire's poetry",
        "title": "What \"Spleen\" Means in Baudelaire's Poetry",
        "meta_description": "A clear guide to what \"spleen\" actually means in Baudelaire's Les Fleurs du Mal — not the organ, not boredom, but the specific modern melancholy he coined.",
        "h1": "What \"spleen\" means in Baudelaire's poetry",
        "updated": "2026-05-19",
        "related": ["ennui-in-literature", "melancholy-hamlet", "sublime-in-romanticism"],
        "body_html": """
<p>If you're reading Charles Baudelaire's <em>Les Fleurs du Mal</em> and you hit
the word <strong>spleen</strong>, your dictionary will fail you. It will tell
you about an organ that filters blood. Baudelaire was not writing about anatomy.</p>

<p>He was writing about a very specific kind of soul-sickness — and he used the
word so deliberately that he made it the title of four separate poems in his
collection.</p>

<h2>The literal meaning he was playing on</h2>

<p>In medieval and early-modern medicine, the spleen was thought to be the
source of black bile, one of the four humors. An excess of black bile produced
<em>melancholia</em> — a heavy, brooding sadness. By the 18th century, English
writers had already adopted "spleen" as slang for that mood. Pope, Swift, and
the Restoration poets all use it.</p>

<p>Baudelaire knew this tradition. He chose the English word "spleen" on purpose,
in French verse, to import its specific texture of disgust, irritability, and
heaviness.</p>

<h2>What he made it mean</h2>

<p>Baudelaire's spleen is not generic sadness. It is the specific feeling of
modern urban life pressing down on a sensitive consciousness. It includes:</p>

<ul>
  <li><strong>Heaviness</strong> — the sky is "a lid" pressing on the spirit.</li>
  <li><strong>Disgust</strong> — with self, with the city, with time itself.</li>
  <li><strong>Time-sickness</strong> — the dragging, viscous quality of hours
      that refuse to pass.</li>
  <li><strong>Confinement</strong> — the soul as a damp dungeon, a graveyard,
      a coffin.</li>
</ul>

<p>Each of the four "Spleen" poems works one of these registers. Spleen II
("J'ai plus de souvenirs…") is about memory as a crushing weight. Spleen IV
("Quand le ciel bas et lourd…") is the one most students read first — the sky
becomes a literal ceiling closing in.</p>

<h2>Why "boredom" or "melancholy" are wrong translations</h2>

<p>English translators sometimes render <em>spleen</em> as "melancholy" or
"boredom." Both are wrong, and a contextual reading shows why:</p>

<ul>
  <li><strong>Melancholy</strong> is too refined. It implies elegant, tasteful
      sadness — the mood of a Renaissance painting. Spleen is grubbier, more
      physical, more aggressive.</li>
  <li><strong>Boredom</strong> is too thin. The English word doesn't carry the
      sense of disgust or the bodily heaviness.</li>
  <li><strong>Ennui</strong> is closer, but Baudelaire uses <em>both words
      separately</em> — they aren't synonyms in his vocabulary. Ennui is the
      cause; spleen is the symptom.</li>
</ul>

<h2>How to read it in context</h2>

<p>When you meet "spleen" in a Baudelaire poem, read it as a <strong>state of
the body and soul together</strong>: a leaden mood that has weight, smell, and
temperature. Don't picture an organ; picture weather. The poet is telling you
the atmospheric pressure of his interior life.</p>

<p>This is also why "spleen" became one of the founding terms of literary
modernism. Eliot's <em>The Waste Land</em> inherits it directly. So does the
sensibility of writers like Cioran, Pessoa, and Houellebecq — all of them
descend, in some way, from Baudelaire's coinage.</p>
""",
    },

    # ──────────────────────────────────────────────────────────────────────
    {
        "slug": "labyrinthine-in-literature",
        "term": "labyrinthine",
        "context": "literary description",
        "title": "What \"Labyrinthine\" Means in Literature",
        "meta_description": "Labyrinthine isn't just a fancy word for \"complex.\" Here's what it actually signals when an author describes a plot, sentence, or world as labyrinthine.",
        "h1": "What \"labyrinthine\" means in literature",
        "updated": "2026-05-19",
        "related": ["verisimilitude-in-literature", "bildungsroman-genre", "pathetic-fallacy"],
        "body_html": """
<p>If a critic describes a novel's plot as <strong>labyrinthine</strong>, they
are saying something more specific than "complicated." The word carries
2,500 years of literary baggage that "complex" and "intricate" don't.</p>

<h2>The myth it comes from</h2>

<p>The original labyrinth was built by Daedalus on Crete to imprison the
Minotaur. Theseus survived it only by trailing a thread behind him — Ariadne's
thread — so he could find his way out. Two ideas are baked into the word
from the start:</p>

<ul>
  <li>It is designed to <strong>disorient</strong>, not just to be large.</li>
  <li>Escape requires a <strong>guide</strong> — a thread, a clue, a key.</li>
</ul>

<p>This is why "labyrinthine" carries a faint anxiety that "complex" doesn't.
A complex system can be elegant. A labyrinthine one threatens to swallow you.</p>

<h2>What writers signal when they use it</h2>

<p>When a passage or a plot is called labyrinthine, the writer is usually
flagging one of three things:</p>

<ol>
  <li><strong>Deliberate intricacy.</strong> The complexity is the point, not
      a flaw. The author wants you to feel a little lost.</li>
  <li><strong>Architectural quality.</strong> The structure is built; it isn't
      messy. There are corridors and chambers, not heaps of debris.</li>
  <li><strong>A hidden center.</strong> Somewhere in the maze there is a
      revelation — a Minotaur, a meaning — and the reader is being walked
      toward it.</li>
</ol>

<h2>Authors who lean on the word</h2>

<p>Three writers have made the labyrinth almost their signature image:</p>

<ul>
  <li><strong>Jorge Luis Borges.</strong> His story "The Garden of Forking
      Paths" treats time itself as a labyrinth. Almost every Borges essay
      reaches for the word.</li>
  <li><strong>Franz Kafka.</strong> The bureaucracy in <em>The Trial</em> and
      <em>The Castle</em> is a labyrinth made of paperwork — endless corridors
      of clerks, no minotaur, no thread.</li>
  <li><strong>Umberto Eco.</strong> The library in <em>The Name of the Rose</em>
      is a literal labyrinth, and the novel's plot mirrors its floor plan.</li>
</ul>

<h2>How it differs from neighbors</h2>

<p>Context disambiguates "labyrinthine" from words that look similar:</p>

<ul>
  <li><strong>Convoluted</strong> implies a flaw — twisted in a way that obscures
      meaning. Labyrinthine doesn't carry the same disapproval.</li>
  <li><strong>Byzantine</strong> implies bureaucratic complexity with political
      overtones; you'd use it of a government, not a poem.</li>
  <li><strong>Intricate</strong> just means "many fine parts." It lacks the
      sense of a center to be reached.</li>
</ul>

<h2>How to read it in a sentence</h2>

<p>When you meet "labyrinthine" in a piece of criticism or fiction, ask: where
is the thread, and what waits at the center? The word almost always implies
that the author has built something you are meant to navigate, slowly and with
attention — not skim past.</p>
""",
    },

    # ──────────────────────────────────────────────────────────────────────
    {
        "slug": "sublime-in-romanticism",
        "term": "sublime",
        "context": "Romantic literature",
        "title": "What \"Sublime\" Means in Romantic Literature",
        "meta_description": "The sublime in Romanticism isn't \"a sublime dessert.\" Here's what Burke, Kant, and Wordsworth actually meant — and how to spot it in poetry.",
        "h1": "What \"sublime\" means in Romantic literature",
        "updated": "2026-05-19",
        "related": ["spleen-baudelaire", "pathetic-fallacy", "melancholy-hamlet"],
        "body_html": """
<p>Modern English has worn the word <strong>sublime</strong> almost smooth.
We use it for desserts and weather. In Romantic literature — roughly
1780–1850 — it meant something far more specific, and far more violent.</p>

<h2>The technical definition the Romantics inherited</h2>

<p>The word's literary career begins with Edmund Burke's
<em>A Philosophical Enquiry into the Origin of Our Ideas of the Sublime and
Beautiful</em> (1757). Burke argued that the sublime is the <strong>opposite</strong>
of the beautiful, not a stronger version of it.</p>

<ul>
  <li><strong>The beautiful</strong> is small, smooth, ordered, gentle. A garden.
      A face. A song.</li>
  <li><strong>The sublime</strong> is vast, rough, obscure, threatening. A storm.
      A cliff. A ruin. The night sky.</li>
</ul>

<p>Crucially, Burke said the sublime works through <strong>terror</strong>. We
feel something is sublime when it is large or powerful enough that it
<em>could destroy us</em>, but we are safely separated from it — watching from
a window, reading on a sofa, standing on a path above the abyss.</p>

<h2>Kant's refinement</h2>

<p>Immanuel Kant, in the <em>Critique of Judgment</em> (1790), split the sublime
into two categories:</p>

<ul>
  <li><strong>Mathematical sublime:</strong> things so vast they overwhelm the
      mind's ability to grasp them — the night sky, the ocean, geological
      time.</li>
  <li><strong>Dynamical sublime:</strong> things so powerful they overwhelm
      the body's ability to resist them — avalanches, storms, volcanoes.</li>
</ul>

<p>For Kant, the experience of the sublime is paradoxical: we feel small and
crushed, and at the same time we feel <em>elevated</em>, because our mind is
able to <strong>think</strong> the vastness even though it cannot contain it.</p>

<h2>How Romantic poets used the word</h2>

<p>This is the philosophical equipment Wordsworth, Coleridge, Shelley, and
Byron carried with them into the Alps. When Wordsworth describes a mountain
in <em>The Prelude</em>, he is not saying it is pretty. He is saying it
performs a specific operation on the consciousness:</p>

<ol>
  <li>It dwarfs the self.</li>
  <li>It induces a kind of fear.</li>
  <li>It opens up an awareness of something larger — divinity, nature, the
      infinite — that the safe domestic world had hidden.</li>
</ol>

<p>Shelley's "Mont Blanc" is a textbook case. Byron's storm in
<em>Childe Harold</em> is another. Mary Shelley uses the sublime ironically in
<em>Frankenstein</em>: the creature roams in landscapes that are sublime in
the Burkean sense, while delivering speeches that test the limits of the
concept.</p>

<h2>Why modern usage misleads</h2>

<p>When we say a meal is "sublime," we mean "very, very good." That use was
mocked even in the Romantic period — Coleridge complained about it. The
Romantic sublime is closer to <strong>awe</strong>, with all of awe's
discomfort: the feeling of being made very small by something very large.</p>

<h2>How to read it in a poem</h2>

<p>When you meet "sublime" in a Romantic poem or essay, ask:</p>

<ul>
  <li>What is the threat? (storm, cliff, ocean, ruin)</li>
  <li>Is the speaker safe from it, or in it?</li>
  <li>What faculty is being overwhelmed — sight, reason, memory?</li>
</ul>

<p>The word is doing technical work. Treat it as you would treat
<em>verisimilitude</em> or <em>catharsis</em>: a term of art with a tradition
behind it, not a casual adjective.</p>
""",
    },

    # ──────────────────────────────────────────────────────────────────────
    {
        "slug": "melancholy-hamlet",
        "term": "melancholy",
        "context": "Shakespeare's Hamlet",
        "title": "What \"Melancholy\" Means in Hamlet",
        "meta_description": "Hamlet calls himself melancholy, but the word meant something specific in 1600 — a clinical condition, not a mood. Here's what Shakespeare's audience would have heard.",
        "h1": "What \"melancholy\" means in Hamlet",
        "updated": "2026-05-19",
        "related": ["spleen-baudelaire", "ennui-in-literature", "sublime-in-romanticism"],
        "body_html": """
<p>When Hamlet describes himself as melancholy, a modern reader hears "sad."
A 1600 audience heard something much more specific: a <strong>medical
diagnosis</strong>, a temperament, and a fashionable pose all at once.</p>

<h2>The medical meaning</h2>

<p>Shakespeare's England inherited Greek humoral medicine. Health was thought
to depend on the balance of four fluids in the body:</p>

<ul>
  <li><strong>Blood</strong> — sanguine, warm, cheerful</li>
  <li><strong>Yellow bile</strong> — choleric, hot, angry</li>
  <li><strong>Phlegm</strong> — phlegmatic, cool, calm</li>
  <li><strong>Black bile</strong> — melancholic, cold, brooding</li>
</ul>

<p>Black bile was thought to come from the spleen. An excess produced
<em>melancholia</em>: a constitutional state of cold, dry heaviness with
specific physical symptoms — dark complexion, weight loss, insomnia,
obsessive thought.</p>

<p>So when Hamlet says he has "lost all my mirth," he is not just feeling
down. He is describing himself as clinically melancholic, a recognized
condition that an Elizabethan physician would have tried to treat with diet
and bleeding.</p>

<h2>The temperamental meaning</h2>

<p>Beyond the medical, melancholy was also understood as a <strong>type of
mind</strong>. Robert Burton's <em>The Anatomy of Melancholy</em> (1621, just
twenty years after Hamlet) catalogues hundreds of variants: love melancholy,
religious melancholy, scholarly melancholy.</p>

<p>The "melancholy scholar" was a recognizable Renaissance archetype: a young
man who reads too much, thinks too much, sleeps poorly, and broods on death.
Hamlet, just back from his studies at Wittenberg, fits the type exactly. The
1600 audience would have recognized the silhouette immediately.</p>

<h2>The fashionable meaning</h2>

<p>By Shakespeare's time, melancholy had also become a <strong>pose</strong>.
Young gentlemen at the Inns of Court cultivated it. Black clothes, sighs,
broken sentences, sudden departures — these were affectations as much as
symptoms. Shakespeare mocks the pose in <em>As You Like It</em> through
Jaques, who is famously and tediously melancholic by choice.</p>

<p>Hamlet sits between the genuine and the fashionable. He <em>is</em>
grieving. He has <em>seen a ghost</em>. But he also knows how a melancholy
prince is supposed to behave, and he uses the role — strategically — to buy
himself time while he investigates his father's murder. The black clothes are
real grief; they are also a costume.</p>

<h2>How to read the word in the play</h2>

<p>Whenever a character in Hamlet uses the word "melancholy" (or
"distemper," "humour," "vapor"), keep three readings in mind:</p>

<ol>
  <li><strong>Diagnosis</strong> — is the speaker claiming Hamlet is medically
      ill?</li>
  <li><strong>Characterization</strong> — is the speaker placing Hamlet in the
      "melancholy scholar" type?</li>
  <li><strong>Suspicion</strong> — is the speaker accusing Hamlet of putting
      it on?</li>
</ol>

<p>Polonius and Claudius shift between all three readings, often within the
same scene. Reading "melancholy" as simply "sad" flattens the play and misses
its central question: is Hamlet ill, philosophical, performing, or all three
at once?</p>
""",
    },

    # ──────────────────────────────────────────────────────────────────────
    {
        "slug": "ennui-in-literature",
        "term": "ennui",
        "context": "French and modernist literature",
        "title": "What \"Ennui\" Means in Literature",
        "meta_description": "Ennui isn't just boredom. In Flaubert, Baudelaire, and the existentialists, it names a specific modern condition — here's how to recognize it.",
        "h1": "What \"ennui\" means in literature",
        "updated": "2026-05-19",
        "related": ["spleen-baudelaire", "melancholy-hamlet", "sublime-in-romanticism"],
        "body_html": """
<p>The French word <strong>ennui</strong> entered English as a loanword in the
18th century, but it has never quite settled. Translators reach for "boredom,"
which loses the weight, or "weariness," which loses the philosophical edge.
In literary contexts, the word does specific work that neither English
substitute can do.</p>

<h2>The literal meaning, and why it's misleading</h2>

<p>In modern French, <em>ennui</em> can mean trouble, annoyance, or boredom —
quite ordinary feelings. A French speaker complaining about a flat tire might
say "quel ennui." This is not the literary sense.</p>

<p>The literary <strong>ennui</strong> is heavier, slower, and more
metaphysical. It is the boredom of someone who has every comfort and finds
that comfort intolerable.</p>

<h2>Flaubert's contribution</h2>

<p>Gustave Flaubert's <em>Madame Bovary</em> (1856) is the novel that
crystallized literary ennui. Emma Bovary has a husband, a child, a house, a
village. She finds them all unendurable — not because they are bad, but
because the gap between her imagination and her actual life is so wide it
becomes a chronic pain.</p>

<p>That pain is ennui. It is not the boredom of having nothing to do; it is
the boredom of having nothing that matches the size of your inner life.</p>

<h2>Baudelaire's version</h2>

<p>In Baudelaire's <em>Les Fleurs du Mal</em>, ennui is upgraded into a kind
of demon. In the prefatory poem "Au Lecteur," he names ennui as the worst of
all human vices — worse than cruelty, worse than greed — because it is the
one that dreams of swallowing the world while doing nothing. (For the related
but distinct mood Baudelaire calls <em>spleen</em>, see our
<a href="/glossary/spleen-baudelaire">entry on spleen in Baudelaire</a>.)</p>

<h2>The existentialist inheritance</h2>

<p>Sartre's <em>Nausea</em> and Camus's <em>The Stranger</em> are both built
on a foundation of ennui, though neither uses the word much. The defining
modern symptom — <strong>the feeling that nothing matters, including the
feeling that nothing matters</strong> — is the late descendant of Flaubert's
Emma and Baudelaire's poet-narrator.</p>

<h2>Ennui vs. its neighbors</h2>

<ul>
  <li><strong>Boredom</strong> is local and passing. You are bored at the
      airport.</li>
  <li><strong>Ennui</strong> is structural and chronic. You are not bored at
      anything; you are bored at being.</li>
  <li><strong>Melancholy</strong> has a sad object — a loss, a grief. Ennui
      has no object; that is the point. (See our
      <a href="/glossary/melancholy-hamlet">entry on melancholy in Hamlet</a>.)</li>
  <li><strong>Mal du siècle</strong> ("sickness of the age") is the
      historical-cultural version of ennui — the same mood diagnosed as a
      generational condition, as in Musset or Chateaubriand.</li>
</ul>

<h2>How to read it</h2>

<p>When a character in a 19th-century novel is described as suffering from
ennui, do not picture them yawning. Picture them at a beautiful dinner table
unable to lift the fork, because the gap between what life promised and what
it delivered has just opened underneath their chair.</p>

<p>That is the literary ennui — and once you've read it that way, you'll see
it everywhere from Chekhov to Houellebecq.</p>
""",
    },

    # ──────────────────────────────────────────────────────────────────────
    {
        "slug": "verisimilitude-in-literature",
        "term": "verisimilitude",
        "context": "fiction and criticism",
        "title": "What \"Verisimilitude\" Means in Literature",
        "meta_description": "Verisimilitude isn't the same as realism. Here's the precise literary meaning — from Aristotle to the 19th-century novel — and how critics actually use it.",
        "h1": "What \"verisimilitude\" means in literature",
        "updated": "2026-05-19",
        "related": ["labyrinthine-in-literature", "bildungsroman-genre", "pathetic-fallacy"],
        "body_html": """
<p><strong>Verisimilitude</strong> is one of those words that sound technical
on purpose. It comes from the Latin <em>verum</em> ("true") plus
<em>similis</em> ("like") — so, literally, "truth-likeness." In literary
criticism it means something more precise than its English near-synonyms
("realism," "believability") and worth getting right.</p>

<h2>Aristotle's distinction</h2>

<p>The concept goes back to Aristotle's <em>Poetics</em>. Aristotle argued
that a poet's job was not to report what <em>did</em> happen — that was the
historian's job — but to depict what <strong>could</strong> happen. The poet
works in the realm of the <em>probable</em>, not the merely factual.</p>

<p>This is the seed of verisimilitude as a critical idea. A story has
verisimilitude when its events, characters, and dialogue feel like things
that <em>could plausibly</em> occur in the world the story has set up —
whether that world is realistic London or a magical kingdom.</p>

<h2>Why it's not the same as realism</h2>

<p>This is the most common confusion. Realism is a 19th-century literary
movement with specific commitments: contemporary settings, ordinary
characters, social-observational detail. Verisimilitude is a much older
quality that <em>any</em> work can have or lack:</p>

<ul>
  <li>A fantasy novel can have high verisimilitude (internally consistent
      magic, plausible character motives) even though it has zero realism.</li>
  <li>A realist novel can fail at verisimilitude if its dialogue is wooden or
      its coincidences too lucky.</li>
</ul>

<p>Tolkien's Middle-earth has tremendous verisimilitude — readers feel its
languages, geography, and centuries-deep history are <em>coherent</em>. No
one would call it realist.</p>

<h2>The two kinds of verisimilitude</h2>

<p>Critics often distinguish two flavors:</p>

<ol>
  <li><strong>Cultural verisimilitude</strong> — the story matches what the
      reader already believes about the real world. (A 19th-century reader
      would expect a bank clerk to behave a certain way.)</li>
  <li><strong>Generic verisimilitude</strong> — the story matches what the
      reader expects of <em>its genre</em>. (We expect a noir detective to
      drink too much; we expect a fairy-tale villain to overplay their
      hand.)</li>
</ol>

<p>A skilled writer manages both. They keep faith with the reader's lived
experience <em>and</em> with the conventions of the form they are writing in.</p>

<h2>How critics use the word</h2>

<p>When a critic praises a novel's verisimilitude, they are usually
complimenting one of these:</p>

<ul>
  <li>Dialogue that sounds like real people speaking.</li>
  <li>Period detail that is research-deep, not Wikipedia-thin.</li>
  <li>Cause-and-effect that feels earned, not engineered.</li>
  <li>Characters whose decisions arise from their psychology, not the
      author's plot need.</li>
</ul>

<p>When they complain about a lack of verisimilitude, they usually mean one
of these has broken — most often the last.</p>

<h2>How to read the word</h2>

<p>When you meet "verisimilitude" in an essay or review, translate it
mentally as: "the writer's craft of making this seem true enough to keep me
inside the story." It is a measure of <strong>internal coherence and
plausibility</strong>, not a measure of how realistic the surface is.</p>
""",
    },

    # ──────────────────────────────────────────────────────────────────────
    {
        "slug": "bildungsroman-genre",
        "term": "bildungsroman",
        "context": "coming-of-age literature",
        "title": "What \"Bildungsroman\" Means — Coming-of-Age Genre Explained",
        "meta_description": "A bildungsroman is more than a coming-of-age story. Here's the precise genre — its German origin, its structure, and its famous examples from Goethe to today.",
        "h1": "What \"bildungsroman\" means",
        "updated": "2026-05-19",
        "related": ["verisimilitude-in-literature", "labyrinthine-in-literature", "pathetic-fallacy"],
        "body_html": """
<p><strong>Bildungsroman</strong> is one of those German loan-words critics
reach for when "coming-of-age novel" feels too loose. The terms overlap but
are not identical, and using bildungsroman correctly means knowing the
specific structural pattern it names.</p>

<h2>The literal meaning</h2>

<p>The German word combines <em>Bildung</em> (formation, education,
cultivation) and <em>Roman</em> (novel). Literally: <strong>formation
novel</strong>. The emphasis is on the deliberate shaping of a self over
time — not just growing up, but being <em>formed</em> by experience into a
particular kind of person.</p>

<h2>The original</h2>

<p>The genre is conventionally dated to Goethe's <em>Wilhelm Meister's
Apprenticeship</em> (1795–96). Wilhelm leaves his bourgeois family, joins a
theatre troupe, falls in and out of love, suffers, learns, and emerges with
a stable adult identity and a useful place in society.</p>

<p>That arc — <strong>departure → trial → integration</strong> — is the
backbone of the genre. Every later bildungsroman inherits it, even when it
subverts it.</p>

<h2>The structural features</h2>

<p>A novel earns the label "bildungsroman" when it includes most of these:</p>

<ol>
  <li><strong>A young protagonist</strong>, usually adolescent at the start.</li>
  <li><strong>A loss or rupture</strong> early on — death of a parent, a
      forced departure, expulsion from a safe world.</li>
  <li><strong>A journey</strong>, geographical or social, that puts the
      protagonist in contact with new classes, ideas, or worlds.</li>
  <li><strong>A series of trials and mistakes</strong>, especially in love
      and work.</li>
  <li><strong>A guide or mentor</strong>, sometimes more than one.</li>
  <li><strong>An arrival</strong> — the protagonist takes a place in adult
      society, having become someone they were not at the start.</li>
</ol>

<p>If the arrival is missing or ironized, you're often in the territory of
the <strong>anti-bildungsroman</strong> — a novel that uses the form to
show formation <em>failing</em>.</p>

<h2>Canonical examples</h2>

<ul>
  <li><strong>Goethe, <em>Wilhelm Meister's Apprenticeship</em></strong> — the
      template.</li>
  <li><strong>Dickens, <em>David Copperfield</em></strong> and
      <strong><em>Great Expectations</em></strong> — the English Victorian
      bildungsroman, with class as a central pressure.</li>
  <li><strong>Joyce, <em>A Portrait of the Artist as a Young Man</em></strong>
      — formation specifically of an artistic consciousness (sometimes called
      a <em>Künstlerroman</em>, an artist-novel, a sub-genre).</li>
  <li><strong>Salinger, <em>The Catcher in the Rye</em></strong> — often
      read as an anti-bildungsroman; Holden refuses the arrival.</li>
  <li><strong>Adichie, <em>Purple Hibiscus</em></strong> — a contemporary
      Nigerian bildungsroman.</li>
  <li><strong>Ferrante, the Neapolitan Quartet</strong> — a four-volume
      bildungsroman of two women, complicating the genre's traditionally
      male protagonist.</li>
</ul>

<h2>Bildungsroman vs. neighbors</h2>

<ul>
  <li><strong>Coming-of-age story</strong> is the loose English equivalent.
      Every bildungsroman is a coming-of-age story; not every coming-of-age
      story is a bildungsroman. A short story about a single summer is rarely
      a bildungsroman — the genre demands scale and time.</li>
  <li><strong>Künstlerroman</strong> — a bildungsroman specifically about an
      artist's formation.</li>
  <li><strong>Erziehungsroman</strong> — emphasizes formal education
      (boarding school novels, for example).</li>
</ul>

<h2>How to read it</h2>

<p>When a critic calls a novel a bildungsroman, they are signalling: <em>watch
the protagonist's identity change shape</em>. The book's real subject is not
plot but <strong>formation</strong> — how a self is built, and at what
cost.</p>
""",
    },

    # ──────────────────────────────────────────────────────────────────────
    {
        "slug": "pathetic-fallacy",
        "term": "pathetic fallacy",
        "context": "poetry and criticism",
        "title": "What \"Pathetic Fallacy\" Means in Literature",
        "meta_description": "Pathetic fallacy isn't an insult, and it isn't personification. Here's exactly what John Ruskin meant in 1856 — and what critics mean by it now.",
        "h1": "What \"pathetic fallacy\" means in literature",
        "updated": "2026-05-19",
        "related": ["sublime-in-romanticism", "verisimilitude-in-literature", "ennui-in-literature"],
        "body_html": """
<p><strong>Pathetic fallacy</strong> is a term that has changed meaning twice
since it was coined, which is why it confuses students. To use it accurately
you need to know three things: who invented it, what they originally meant,
and how critics use it now.</p>

<h2>Who invented it</h2>

<p>The phrase was coined by the Victorian critic <strong>John Ruskin</strong>
in volume three of <em>Modern Painters</em> (1856). "Pathetic" here doesn't
mean "weak" or "sad in a contemptible way" — it comes from the Greek
<em>pathos</em>, "feeling." So "pathetic fallacy" literally means a
<strong>fallacy of feeling</strong>: an error involving emotion.</p>

<h2>What Ruskin originally meant</h2>

<p>Ruskin was complaining about a habit he saw in second-rate poets:
attributing human emotions to natural objects that couldn't possibly have
them. A poet who writes that "the cruel waves" attacked the ship is
projecting human cruelty onto water that is, in fact, just obeying physics.</p>

<p>For Ruskin this was a <strong>fault</strong> — a sign that the poet's
emotion had overwhelmed their accurate perception of the world. He thought
the greatest poets (Homer, Dante, Shakespeare) used the device sparingly and
with awareness, while sentimental Romantics over-used it.</p>

<p>So in Ruskin's hands, "pathetic fallacy" was a <strong>criticism</strong>.
Calling a passage an instance of pathetic fallacy meant the poet had lost
their grip.</p>

<h2>How the meaning shifted</h2>

<p>By the twentieth century, critics had quietly stripped the word of its
disapproval. Today "pathetic fallacy" usually names a <strong>neutral
literary technique</strong>:</p>

<blockquote>
  <em>A storm rages while the protagonist's marriage falls apart. The clouds
  reflect Heathcliff's grief.</em>
</blockquote>

<p>A modern critic identifying these moments isn't condemning them; they're
just naming the device. The valence of the word has flipped from "fault" to
"feature."</p>

<h2>Pathetic fallacy vs. its neighbors</h2>

<ul>
  <li><strong>Personification</strong> attributes human <em>qualities or
      behavior</em> to non-human things — "the fog crept on little cat feet."
      Pathetic fallacy specifically attributes <em>emotion</em>.</li>
  <li><strong>Anthropomorphism</strong> turns non-humans into full human-like
      agents — animal characters in a fable. Pathetic fallacy stops short of
      that.</li>
  <li><strong>Objective correlative</strong> (T. S. Eliot's term) is the
      <em>opposite</em> direction: finding an external object that
      <em>evokes</em> a feeling in the reader, rather than dumping feeling
      onto the object.</li>
</ul>

<h2>Famous examples</h2>

<ul>
  <li>The storm on the heath in <em>King Lear</em> rages as Lear's mind
      breaks. Shakespeare uses it deliberately and self-consciously — Lear
      <em>knows</em> the storm is indifferent, which is part of the tragedy.</li>
  <li>The weather in <em>Wuthering Heights</em> tracks the emotional
      temperature of the Earnshaw and Linton households so closely it becomes
      structural.</li>
  <li>The sea in Conrad's <em>Heart of Darkness</em> is repeatedly described
      as "brooding" — the projection is part of how Marlow narrates his own
      dread.</li>
</ul>

<h2>How to read it</h2>

<p>When you meet "pathetic fallacy" in an essay, two questions help you read
it precisely:</p>

<ol>
  <li>Is the critic using Ruskin's old meaning (it's a fault) or the modern
      one (it's a technique)?</li>
  <li>Is the writer using the device naively (the storm just "feels sad"
      because the character does) or self-consciously (the character knows
      they're projecting, and the gap is the point)?</li>
</ol>

<p>The most interesting cases — Shakespeare, the Brontës, Conrad — are
always self-conscious. The device only becomes a "fallacy" in Ruskin's sense
when the writer hasn't noticed they're doing it.</p>
""",
    },

    # ──────────────────────────────────────────────────────────────────────
    {
        "slug": "catharsis-greek-tragedy",
        "term": "catharsis",
        "context": "Greek tragedy and Aristotelian theory",
        "title": "What \"Catharsis\" Means in Greek Tragedy",
        "meta_description": "Aristotle's catharsis isn't just \"emotional release.\" Here's what he actually meant in the Poetics — and why scholars are still arguing about it.",
        "h1": "What \"catharsis\" means in Greek tragedy",
        "updated": "2026-05-19",
        "related": ["anagnorisis", "peripeteia", "dramatic-irony"],
        "body_html": """
<p>When a student today writes that a film provides "great catharsis," they
usually mean a satisfying emotional release. In Aristotle's <em>Poetics</em>
— the text that gave us the word — it meant something far more specific
and far more contested. Scholars have been arguing about what Aristotle
actually meant for 2,400 years.</p>

<h2>The word in the Poetics</h2>

<p>Aristotle uses <em>katharsis</em> only once in the <em>Poetics</em>, in
his definition of tragedy. Tragedy, he says, imitates a serious action and,
through pity and fear, accomplishes the <em>katharsis</em> of such
emotions. That sentence is the entire textual basis for the concept.
Everything else is interpretation.</p>

<h2>The three main readings</h2>

<p>Three competing readings have dominated the conversation:</p>

<ol>
  <li><strong>Purgation.</strong> The medical reading. Catharsis is the
      discharge of harmful emotional excess — pity and fear are flushed
      out of the spectator's system the way black bile might be purged from
      the body. This was the dominant reading from the Renaissance through
      the 19th century.</li>
  <li><strong>Purification.</strong> The ethical reading. Catharsis doesn't
      eliminate pity and fear; it refines them, teaches them their proper
      objects. We leave a tragedy with our emotions <em>better
      calibrated</em>, not emptied.</li>
  <li><strong>Clarification.</strong> The cognitive reading, championed by
      modern scholars like Martha Nussbaum. Catharsis is an intellectual
      event — the play <em>clarifies</em> what pity and fear are, what
      they're for, when they are warranted. We leave knowing something we
      didn't know before.</li>
</ol>

<p>All three readings have textual support; none has been definitively
proven. Most contemporary classicists treat catharsis as a deliberately
multi-layered term doing several kinds of work at once.</p>

<h2>What it isn't</h2>

<ul>
  <li><strong>Catharsis as venting.</strong> "I needed a good cry — it was
      cathartic." This is the popular-psychology sense, in which catharsis
      means expressing a pent-up feeling. Aristotle's catharsis is not about
      the spectator <em>expressing</em> anything; it's about what the play
      <em>does</em> to them.</li>
  <li><strong>Catharsis as resolution.</strong> "The film's third act
      provides catharsis." Here it just means a satisfying ending. But
      Aristotelian catharsis can occur in tragedies that resolve
      <em>badly</em> — Oedipus does not end happily, and that is the
      point.</li>
</ul>

<h2>How to read the word in criticism</h2>

<p>When a critic invokes catharsis, ask which reading they're working
from. A psychoanalytic critic usually means purgation. An ethicist often
means purification. A modern classicist usually means clarification. The
word is genuinely a contested term of art — it carries 2,400 years of
argument, and treating it as a synonym for "emotional release" flattens
that history beyond recognition.</p>
""",
    },

    # ──────────────────────────────────────────────────────────────────────
    {
        "slug": "anagnorisis",
        "term": "anagnorisis",
        "context": "Greek tragedy and narrative theory",
        "title": "What \"Anagnorisis\" Means in Tragedy",
        "meta_description": "Anagnorisis is Aristotle's term for the moment a character moves from ignorance to knowledge. Here's how to spot it in tragedy — and why it still matters.",
        "h1": "What \"anagnorisis\" means in tragedy",
        "updated": "2026-05-19",
        "related": ["catharsis-greek-tragedy", "peripeteia", "dramatic-irony"],
        "body_html": """
<p><strong>Anagnorisis</strong> is the Greek for "recognition" — and in
Aristotle's <em>Poetics</em> it names the precise moment in a tragedy when
a character moves from ignorance to knowledge about something that matters.
It is one of the two engines of tragic plot, and learning to spot it
changes the way you read drama.</p>

<h2>What Aristotle meant</h2>

<p>For Aristotle, anagnorisis is not just any insight. It is a structural
event: a shift from <em>not knowing</em> to <em>knowing</em>, with
consequences. The most powerful anagnorisis involves discovering the
identity of a person — a parent, a child, a killer — but it can also be
recognition of a fact (one's own crime, one's true situation).</p>

<p>The clearest example is <em>Oedipus Rex</em>. The play's entire arc is
the slow movement of Oedipus from <em>thinking he is the savior of
Thebes</em> to <em>knowing he is its polluter</em>. The moment the
shepherd's testimony confirms his identity, that is anagnorisis. The
audience has known for a while; Oedipus has not. The play exists in the
gap between those two knowings.</p>

<h2>Anagnorisis and peripeteia together</h2>

<p>Aristotle pairs anagnorisis with <em>peripeteia</em> — reversal. The
finest tragedies, he says, fold the two together: the moment of
recognition <em>is</em> the moment fortune turns. (See our
<a href="/glossary/peripeteia">entry on peripeteia</a>.) Oedipus is again
the model. The recognition of his identity <em>is</em> the reversal from
king to outcast. Recognition and reversal share a single line.</p>

<h2>Types of recognition</h2>

<ul>
  <li><strong>Recognition by tokens</strong> — birthmarks, scars, heirlooms.
      Aristotle considered this the weakest kind: it depends on an external
      accident, not on the character's situation. The scar on Odysseus's
      thigh is a famous example.</li>
  <li><strong>Recognition by reasoning</strong> — the character deduces the
      truth from circumstantial evidence. Often a detective-story effect.</li>
  <li><strong>Recognition through events</strong> — Aristotle's favorite.
      The plot itself, working out its own logic, forces the truth into
      the open. This is what happens in <em>Oedipus</em>: the investigation
      Oedipus himself launches is what reveals him to himself.</li>
</ul>

<h2>Beyond Greek tragedy</h2>

<ul>
  <li>Hamlet's recognition, in the gravedigger scene, that Yorick's skull
      is the same flesh that once entertained him.</li>
  <li>Elizabeth Bennet rereading Darcy's letter and seeing she has
      misjudged him.</li>
  <li>The narrator's recognition at the end of Joyce's "The Dead" that
      his wife once loved someone else more than him.</li>
  <li>Almost every "twist ending" in modern film — though most twists are
      recognition without reversal, which Aristotle rated as the weaker
      form.</li>
</ul>

<h2>How to read it</h2>

<p>When you meet "anagnorisis" in an essay, the writer is naming a
<strong>structural moment</strong>, not just a feeling. Ask: who
recognizes what, and what changes as a result? If the recognition does
not change the situation, it is decorative. The genuinely tragic
anagnorisis closes a door — the character cannot un-know what they have
learned, and the world reshapes itself around the new knowledge.</p>
""",
    },

    # ──────────────────────────────────────────────────────────────────────
    {
        "slug": "peripeteia",
        "term": "peripeteia",
        "context": "Greek tragedy and dramatic theory",
        "title": "What \"Peripeteia\" Means in Tragedy",
        "meta_description": "Peripeteia is Aristotle's word for the reversal — the moment a tragedy's plot turns. Here's how it works and why the best tragedies fuse it with recognition.",
        "h1": "What \"peripeteia\" means in tragedy",
        "updated": "2026-05-19",
        "related": ["anagnorisis", "catharsis-greek-tragedy", "deus-ex-machina"],
        "body_html": """
<p><strong>Peripeteia</strong> — Greek for "reversal" — is Aristotle's
name for the moment a tragedy's fortunes turn. It is the structural hinge
on which a tragic plot pivots, and Aristotle considered it, together with
anagnorisis (recognition), the defining element of a properly constructed
tragedy.</p>

<h2>The definition in the Poetics</h2>

<p>Aristotle defines peripeteia as a change in the direction of the action
<em>into its opposite</em>. This is more specific than "things go badly."
Peripeteia is the moment when the very effort the hero makes to achieve a
goal produces the <strong>reverse</strong> of that goal.</p>

<p>The textbook example is again <em>Oedipus Rex</em>. The messenger
arrives intending to <em>cheer Oedipus up</em> by revealing that Polybus,
the king he believed was his father, is not his father. The news is meant
to dissolve the prophecy. Instead, it sets in motion the chain of
revelations that destroys Oedipus. The messenger's intention and his
effect are exact opposites. That is peripeteia in its purest form.</p>

<h2>Peripeteia and anagnorisis together</h2>

<p>Aristotle considered the finest tragic structure one in which
<strong>reversal and recognition coincide</strong>. The moment the
character recognizes the truth (anagnorisis) <em>is</em> the moment their
fortune turns (peripeteia). The two events share a single beat. This is
why <em>Oedipus Rex</em> is, for Aristotle, the template — the shepherd
scene performs both functions in one line. (See our
<a href="/glossary/anagnorisis">entry on anagnorisis</a>.)</p>

<h2>Peripeteia vs. ordinary plot turns</h2>

<p>Not every twist is a peripeteia. The distinguishing features:</p>

<ul>
  <li><strong>It reverses an intention.</strong> The character is trying
      to do A; the action accomplishes the opposite of A.</li>
  <li><strong>It is internal to the plot.</strong> A peripeteia rises from
      the plot's own logic, not from an outside intervention. When an
      outside force resolves the situation, that's a
      <a href="/glossary/deus-ex-machina">deus ex machina</a> — which
      Aristotle considered a fault.</li>
  <li><strong>It is necessary or probable.</strong> Once it happens, the
      audience should feel "of course." Peripeteia is the structural
      payoff, not a surprise for surprise's sake.</li>
</ul>

<h2>Famous examples beyond Greek tragedy</h2>

<ul>
  <li><strong>Macbeth.</strong> Macbeth murders Duncan to secure the
      throne and his own peace. The murder produces only further bloodshed
      and unrest — the reverse of his intention.</li>
  <li><strong>Crime and Punishment.</strong> Raskolnikov commits the
      murder to prove he is above ordinary morality. The act proves the
      opposite.</li>
  <li><strong>The Great Gatsby.</strong> Gatsby builds an empire to win
      Daisy. The empire is exactly what makes him unworthy in the eyes of
      her class.</li>
</ul>

<h2>How to read it</h2>

<p>When a critic identifies a peripeteia, they are pointing at a moment
of <strong>intentional irony in the plot's structure</strong> — the
hero's action curving back on itself. Ask: what was the character trying
to do? What did the action accomplish? When the two are mirror opposites,
you have peripeteia. The deeper the inversion, the closer the play comes
to Aristotle's ideal.</p>
""",
    },

    # ──────────────────────────────────────────────────────────────────────
    {
        "slug": "dramatic-irony",
        "term": "dramatic irony",
        "context": "drama and narrative",
        "title": "What \"Dramatic Irony\" Means in Literature",
        "meta_description": "Dramatic irony isn't sarcasm. It's the specific structural device where the audience knows something the character doesn't. Here's how it works in tragedy and comedy.",
        "h1": "What \"dramatic irony\" means in literature",
        "updated": "2026-05-19",
        "related": ["anagnorisis", "peripeteia", "unreliable-narrator"],
        "body_html": """
<p><strong>Dramatic irony</strong> is one of those phrases that gets used
loosely to mean "anything ironic in a story." Its actual literary
definition is much tighter — and once you have the tight definition, the
device becomes one of the most powerful tools you can recognize in
fiction and drama.</p>

<h2>The strict definition</h2>

<p>Dramatic irony exists when <strong>the audience knows something a
character does not</strong>, and the character's words or actions take on
a meaning the character cannot perceive but the audience can. The gap
between what the character thinks they are saying or doing and what the
audience sees them saying or doing is the irony.</p>

<p>Crucially, it is not the character being sarcastic and the audience
not getting it. It is the opposite — the audience getting it, the
character not.</p>

<h2>How it works in tragedy</h2>

<p>In tragedy, dramatic irony usually deepens dread. Oedipus declares he
will hunt down the killer of Laius and curse him with the worst fate
imaginable. The audience knows Oedipus is cursing himself. Every line he
speaks about the search is a hammer-stroke. The horror is not in what he
says but in what he <em>cannot hear himself saying</em>.</p>

<p>This is why dramatic irony tightens the audience's emotional
investment. The audience becomes a co-conspirator with the play, holding
the secret the character is about to discover. Anticipation becomes
unbearable.</p>

<h2>How it works in comedy</h2>

<p>In comedy, the same device flips into pleasure. <em>Twelfth Night</em>
runs on dramatic irony: Viola is dressed as a man; Olivia falls in love
with her thinking she's a man; we know Olivia is wrong. Every misdirected
line is funny precisely because we hold the key. Restoration comedy,
Wodehouse, and most sitcom misunderstandings work the same way.</p>

<h2>Three relatives often confused with it</h2>

<ul>
  <li><strong>Verbal irony</strong> is sarcasm — saying the opposite of
      what one means. The speaker is in on the joke. ("Nice weather we're
      having," in a thunderstorm.)</li>
  <li><strong>Situational irony</strong> is the gap between expected and
      actual outcomes. A fire station burning down. Nobody needs to be in
      the dark.</li>
  <li><strong>Dramatic irony</strong> requires the specific asymmetry
      between audience knowledge and character knowledge.</li>
</ul>

<p>Modern usage often blurs these into "irony" generally; in literary
analysis you should keep them separate.</p>

<h2>How writers create it</h2>

<ol>
  <li><strong>A confession by another character.</strong> The audience
      overhears a soliloquy or aside that the protagonist does not.</li>
  <li><strong>An out-of-order plot.</strong> A flash-forward shows a
      death; the rest of the story plays out with the audience watching
      the character walk toward it.</li>
  <li><strong>Genre knowledge.</strong> The audience knows what kind of
      story they are in — a horror film teaches us to fear the basement
      long before the character does.</li>
</ol>

<h2>How to read it</h2>

<p>When a critic identifies dramatic irony, look for the asymmetry. Who
knows what? When did each party learn it? What does the character say
that the audience hears double? The closer you get to that gap, the
closer you get to what the device is doing emotionally — generating
either dread (tragedy) or recognition-comedy (humor), but always at the
expense of a character who cannot hear themselves clearly.</p>
""",
    },

    # ──────────────────────────────────────────────────────────────────────
    {
        "slug": "deus-ex-machina",
        "term": "deus ex machina",
        "context": "drama and narrative",
        "title": "What \"Deus Ex Machina\" Means in Literature",
        "meta_description": "Deus ex machina — literally \"god from the machine\" — names a specific kind of plot resolution. Here's its origin in Greek theater and why critics often see it as a fault.",
        "h1": "What \"deus ex machina\" means in literature",
        "updated": "2026-05-19",
        "related": ["peripeteia", "anagnorisis", "verisimilitude-in-literature"],
        "body_html": """
<p><strong>Deus ex machina</strong> — Latin for "god from the machine" —
is one of the oldest pieces of literary jargon still in active use. The
phrase began as a literal description of stagecraft and ended as critical
shorthand for a specific kind of bad ending. Both senses are worth
knowing.</p>

<h2>The literal origin</h2>

<p>In Greek tragedy, the playwright sometimes needed a god to descend and
resolve the plot. To stage this, theaters used a crane-like device — the
<em>mēchanē</em> — to lower an actor playing the god onto the stage from
above. The Latin translation, <em>deus ex machina</em>, just describes
the mechanism: the god, from the machine.</p>

<p>Euripides was famous for using it. At the end of <em>Medea</em>, Medea
escapes on a chariot drawn by dragons sent by Helios. At the end of
<em>Iphigenia in Tauris</em>, Athena appears to settle the dispute. The
audience would have seen the actor literally lowered from above.</p>

<h2>How it became an insult</h2>

<p>Aristotle, in the <em>Poetics</em>, gave the device its lasting
reputation. The unraveling of the plot, he argued, should arise from
within the plot itself — from the characters' actions and the necessary
consequences. When the resolution is imposed from outside, the plot has
not fulfilled its own logic; the playwright has cheated.</p>

<p>So "deus ex machina" became critical shorthand for any
<strong>external, unmotivated solution</strong> that rescues a story its
writer couldn't otherwise resolve:</p>

<ul>
  <li>A long-lost rich uncle dies and leaves the protagonist money at
      exactly the moment they need it.</li>
  <li>An undiagnosed illness is cured by a coincidental meeting.</li>
  <li>A villain is killed by an unrelated falling tree.</li>
  <li>The hero wakes up and discovers it was all a dream.</li>
</ul>

<p>Whether a literal god descends or not, the structural pattern is the
same: the resolution comes from outside the world the plot has been
building.</p>

<h2>When it isn't a fault</h2>

<ol>
  <li><strong>When the genre asks for it.</strong> Comedies, fairy tales,
      and religious dramas often want a heightened, providential ending.
      Shakespeare's late romances (<em>The Winter's Tale</em>,
      <em>Cymbeline</em>) lean into deus ex machina deliberately.</li>
  <li><strong>When it is the point.</strong> Brecht's
      <em>The Threepenny Opera</em> ends with a mounted messenger
      pardoning the protagonist; the absurdity is deliberate.</li>
  <li><strong>When the "god" was seeded.</strong> If a powerful figure
      has been established earlier in the story, their late intervention
      is not unmotivated — it is the payoff of setup.</li>
</ol>

<h2>How to read it</h2>

<p>When a critic complains of a deus ex machina, they are accusing the
writer of failing to make the plot resolve itself. Ask: does the
resolution arise from the characters' choices and the situation they
have built, or from something external the writer has imported? The
sharper the gap, the more accurate the charge. And ask whether the genre
invites the device — the late Shakespearean god from the machine is
doing different work than a thriller's last-minute coincidence.</p>
""",
    },
]


# ── Lookups ──────────────────────────────────────────────────────────────────

_BY_SLUG: dict[str, dict] = {e["slug"]: e for e in ENTRIES}

def get(slug: str) -> dict | None:
    return _BY_SLUG.get(slug)

def all_entries() -> list[dict]:
    return list(ENTRIES)


# ── HTML rendering ───────────────────────────────────────────────────────────
# Self-contained pages — match the dark hero / orange-accent look of the main
# site, but with comfortable reading typography (Lora for headings, DM Sans
# for UI, larger body text).

_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --accent:  #c35500;
  --accent2: #ff7a18;
  --text:    #f5ede0;
  --text-mid:#cfc4b3;
  --muted:   #9b8f7d;
  --border:  rgba(255,255,255,0.08);
  --bg:      #0f0c08;
  --surface: #181310;
}
body {
  font-family: 'DM Sans', system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.75;
  padding: 0 24px;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 720px; margin: 0 auto; padding: 56px 0 96px; }
.back {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 0.85rem; color: var(--muted);
  text-decoration: none; margin-bottom: 36px;
  transition: color 0.15s;
}
.back:hover { color: var(--accent2); }
.logo {
  font-family: 'Lora', serif;
  font-size: 1.4rem; font-weight: 600;
  color: var(--accent2);
  display: block; margin-bottom: 14px;
}
.logo em { font-style: italic; }
.breadcrumb { font-size: 0.78rem; color: var(--muted); margin-bottom: 18px; letter-spacing: 0.02em; }
.breadcrumb a { color: var(--muted); text-decoration: none; }
.breadcrumb a:hover { color: var(--accent2); }
h1 {
  font-family: 'Lora', serif;
  font-size: 2.1rem; font-weight: 600;
  margin-bottom: 10px;
  line-height: 1.25;
  color: var(--text);
}
.term-context {
  font-size: 0.95rem; color: var(--muted);
  margin-bottom: 36px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--border);
  font-style: italic;
}
h2 {
  font-family: 'Lora', serif;
  font-size: 1.3rem; font-weight: 600;
  margin: 36px 0 12px;
  color: var(--text);
}
p, li {
  font-size: 1rem;
  color: var(--text-mid);
  margin-bottom: 14px;
}
ul, ol { padding-left: 22px; margin-bottom: 14px; }
li { margin-bottom: 8px; }
li::marker { color: var(--accent); }
strong { color: var(--text); font-weight: 600; }
em { font-style: italic; }
a { color: var(--accent2); text-decoration: none; border-bottom: 1px solid rgba(255,122,24,0.25); }
a:hover { border-bottom-color: var(--accent2); }
blockquote {
  border-left: 3px solid var(--accent);
  padding: 6px 16px; margin: 18px 0;
  color: var(--text); font-style: italic;
  background: rgba(195,85,0,0.05);
}

/* CTA card */
.cta {
  margin-top: 56px; padding: 26px 28px;
  background: linear-gradient(135deg, rgba(195,85,0,0.10), rgba(255,122,24,0.05));
  border: 1px solid rgba(255,122,24,0.25);
  border-radius: 14px;
}
.cta-eyebrow {
  font-size: 0.72rem; letter-spacing: 0.12em; text-transform: uppercase;
  color: var(--accent2); font-weight: 700; margin-bottom: 8px;
  display: block;
}
.cta h3 {
  font-family: 'Lora', serif; font-size: 1.25rem; font-weight: 600;
  color: var(--text); margin-bottom: 8px;
}
.cta p { color: var(--text-mid); font-size: 0.95rem; margin-bottom: 16px; }
.cta-btn {
  display: inline-block; padding: 11px 22px;
  background: var(--accent); color: #fff;
  font-family: inherit; font-weight: 500; font-size: 0.92rem;
  text-decoration: none; border-radius: 8px; border: none;
  transition: background 0.15s, transform 0.15s;
}
.cta-btn:hover { background: var(--accent2); transform: translateY(-1px); border-bottom: none; }

/* Related */
.related { margin-top: 56px; padding-top: 28px; border-top: 1px solid var(--border); }
.related-title {
  font-size: 0.74rem; letter-spacing: 0.12em; text-transform: uppercase;
  color: var(--muted); font-weight: 700; margin-bottom: 14px;
}
.related-list { display: grid; gap: 8px; }
.related-item {
  display: block; padding: 14px 16px;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; text-decoration: none;
  transition: border-color 0.15s, transform 0.15s;
}
.related-item:hover { border-color: rgba(255,122,24,0.4); transform: translateY(-1px); }
.related-item-term {
  font-family: 'Lora', serif; font-size: 1rem; font-weight: 600;
  color: var(--text); margin-bottom: 2px;
}
.related-item-context { font-size: 0.82rem; color: var(--muted); font-style: italic; }

/* Index page extras */
.intro {
  font-size: 1.05rem; color: var(--text-mid);
  margin-bottom: 40px; padding-bottom: 28px;
  border-bottom: 1px solid var(--border);
}
.entry-grid { display: grid; gap: 14px; }
.entry-card {
  display: block; padding: 18px 20px;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 12px; text-decoration: none;
  transition: border-color 0.15s, transform 0.15s;
}
.entry-card:hover { border-color: rgba(255,122,24,0.4); transform: translateY(-1px); }
.entry-card-term {
  font-family: 'Lora', serif; font-size: 1.15rem; font-weight: 600;
  color: var(--text); margin-bottom: 4px;
}
.entry-card-context { font-size: 0.85rem; color: var(--muted); font-style: italic; margin-bottom: 8px; }
.entry-card-desc { font-size: 0.9rem; color: var(--text-mid); line-height: 1.55; }

.closing {
  margin-top: 56px; padding-top: 28px;
  border-top: 1px solid var(--border);
  font-size: 0.85rem; color: var(--muted);
  text-align: center;
}
.closing em { font-style: italic; color: var(--accent2); }
.closing a { color: var(--muted); border-bottom: none; }
.closing a:hover { color: var(--accent2); }

@media (max-width: 640px) {
  h1 { font-size: 1.7rem; }
  .wrap { padding: 40px 0 72px; }
}
"""


def _head(title: str, description: str, canonical: str,
         og_image: str = "https://lexio.site/og-image.png") -> str:
    """Shared <head> block — title/meta/OG/Twitter/Plausible."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{escape(title)} — Lexio</title>
  <meta name="description" content="{escape(description)}" />
  <link rel="canonical" href="{escape(canonical)}" />
  <link rel="icon" type="image/x-icon" href="/favicon.ico" />

  <!-- Open Graph -->
  <meta property="og:type" content="article" />
  <meta property="og:title" content="{escape(title)} — Lexio" />
  <meta property="og:description" content="{escape(description)}" />
  <meta property="og:url" content="{escape(canonical)}" />
  <meta property="og:image" content="{escape(og_image)}" />
  <meta property="og:site_name" content="Lexio" />

  <!-- Twitter -->
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{escape(title)} — Lexio" />
  <meta name="twitter:description" content="{escape(description)}" />
  <meta name="twitter:image" content="{escape(og_image)}" />

  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,600;1,400&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet" />
  <style>{_CSS}</style>

  <!-- Privacy-friendly analytics -->
  <script async src="https://plausible.io/js/pa-uClUulm_iku5Ah2kWnseu.js"></script>
  <script>
    window.plausible=window.plausible||function(){{(plausible.q=plausible.q||[]).push(arguments)}},plausible.init=plausible.init||function(i){{plausible.o=i||{{}}}};
    plausible.init()
  </script>
</head>
"""


def _related_block(slugs: Iterable[str]) -> str:
    items = []
    for s in slugs:
        e = _BY_SLUG.get(s)
        if not e: continue
        items.append(f"""
        <a class="related-item" href="/glossary/{escape(e['slug'])}">
          <div class="related-item-term">{escape(e['term'])}</div>
          <div class="related-item-context">in {escape(e['context'])}</div>
        </a>""")
    if not items: return ""
    return f"""
  <div class="related">
    <div class="related-title">Related entries</div>
    <div class="related-list">{''.join(items)}</div>
  </div>"""


def _cta_block() -> str:
    return """
  <div class="cta">
    <span class="cta-eyebrow">Try Lexio</span>
    <h3>Look up any word like this — in any book, in any browser.</h3>
    <p>Lexio is a free Chrome extension and web app that reads a word's actual context and tells you what it means <em>in this sentence</em>, not from a generic dictionary.</p>
    <a class="cta-btn" href="/">Try Lexio — free →</a>
  </div>"""


def _jsonld_entry(entry: dict, canonical: str) -> str:
    """Schema.org DefinedTerm + Article hybrid — best for glossary pages."""
    import json as _json
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "DefinedTerm",
                "name": entry["term"],
                "description": entry["meta_description"],
                "inDefinedTermSet": {
                    "@type": "DefinedTermSet",
                    "name": "Lexio Glossary",
                    "url": "https://lexio.site/glossary",
                },
                "url": canonical,
            },
            {
                "@type": "Article",
                "headline": entry["title"],
                "description": entry["meta_description"],
                "url": canonical,
                "dateModified": entry["updated"],
                "author": {"@type": "Organization", "name": "Lexio"},
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
                    {"@type": "ListItem", "position": 2, "name": "Glossary", "item": "https://lexio.site/glossary"},
                    {"@type": "ListItem", "position": 3, "name": entry["term"], "item": canonical},
                ],
            },
        ],
    }
    return f'<script type="application/ld+json">{_json.dumps(data, ensure_ascii=False)}</script>'


def render_entry(entry: dict) -> str:
    canonical = f"https://lexio.site/glossary/{entry['slug']}"
    head = _head(entry["title"], entry["meta_description"], canonical)
    jsonld = _jsonld_entry(entry, canonical)
    return f"""{head}
<body>
{jsonld}
<div class="wrap">
  <a class="back" href="/glossary">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
    All glossary entries
  </a>

  <span class="logo">Le<em>x</em>io</span>
  <nav class="breadcrumb" aria-label="Breadcrumb">
    <a href="/">Home</a> &nbsp;›&nbsp; <a href="/glossary">Glossary</a> &nbsp;›&nbsp; {escape(entry['term'])}
  </nav>

  <h1>{escape(entry['h1'])}</h1>
  <p class="term-context">A term you'll meet in {escape(entry['context'])}.</p>

  {entry['body_html']}

  {_cta_block()}
  {_related_block(entry.get('related', []))}

  <p class="closing">
    <em>Read deeper. Understand everything.</em><br>
    © 2026 Lexio · <a href="/privacy.html">Privacy</a> · <a href="/credits.html">Credits</a>
  </p>
</div>
</body>
</html>
"""


def render_index() -> str:
    canonical = "https://lexio.site/glossary"
    head = _head(
        "Lexio Glossary — Literary terms explained in context",
        "Free explainers for literary terms students actually search: spleen in Baudelaire, sublime in Romanticism, melancholy in Hamlet, and more.",
        canonical,
    )

    import json as _json
    jsonld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Lexio Glossary",
        "description": "Free explainers for literary terms in context.",
        "url": canonical,
        "hasPart": [
            {
                "@type": "DefinedTerm",
                "name": e["term"],
                "description": e["meta_description"],
                "url": f"https://lexio.site/glossary/{e['slug']}",
            }
            for e in ENTRIES
        ],
    }
    jsonld_tag = f'<script type="application/ld+json">{_json.dumps(jsonld, ensure_ascii=False)}</script>'

    cards = []
    for e in ENTRIES:
        # Truncate body for preview — pull first <p> text content.
        body = e["body_html"]
        # crude first-paragraph extraction
        start = body.find("<p>")
        end = body.find("</p>", start) if start != -1 else -1
        preview = ""
        if start != -1 and end != -1:
            raw = body[start + 3:end]
            # strip HTML tags for the preview
            import re
            preview = re.sub(r"<[^>]+>", "", raw)
            preview = preview.strip().replace("\n", " ")
            if len(preview) > 180:
                preview = preview[:180].rstrip() + "…"
        cards.append(f"""
    <a class="entry-card" href="/glossary/{escape(e['slug'])}">
      <div class="entry-card-term">{escape(e['term'])}</div>
      <div class="entry-card-context">in {escape(e['context'])}</div>
      <div class="entry-card-desc">{escape(preview)}</div>
    </a>""")

    return f"""{head}
<body>
{jsonld_tag}
<div class="wrap">
  <a class="back" href="/">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
    Back to Lexio
  </a>

  <span class="logo">Le<em>x</em>io</span>
  <h1>Glossary</h1>
  <p class="intro">Literary terms that don't survive a dictionary lookup — explained in the context where you actually meet them. Free to read, no signup. New entries added regularly.</p>

  <div class="entry-grid">{''.join(cards)}</div>

  {_cta_block()}

  <p class="closing">
    <em>Read deeper. Understand everything.</em><br>
    © 2026 Lexio · <a href="/privacy.html">Privacy</a> · <a href="/credits.html">Credits</a>
  </p>
</div>
</body>
</html>
"""
