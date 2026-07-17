"""Localized <title> / <meta name="description"> for each language's homepage.

Used by build_lang_pages.py. Kept separate from UI_T (in static/app.js)
because these are page-level SEO metadata, not client-rendered UI strings.

Source (en): "Lexio — Understand languages the way they're really used" /
"Reading English and stuck on a word? Lexio gives you its exact meaning
in that sentence — idioms and phrasal verbs included — explained in your
own language, with pronunciation. Built for English learners."
"""

META = {
    'es': {
        'title': 'Lexio — Entiende el inglés tal y como se usa de verdad',
        'description': '¿Lees en inglés y te atascas en una palabra? Lexio te da su significado exacto en esa frase — modismos y phrasal verbs incluidos — explicado en tu propio idioma, con pronunciación. Hecho para quienes aprenden inglés.',
    },
    'fr': {
        'title': "Lexio — Comprenez l'anglais tel qu'il est vraiment utilisé",
        'description': "Vous lisez en anglais et butez sur un mot ? Lexio vous donne son sens exact dans cette phrase — idiomes et verbes à particule inclus — expliqué dans votre langue, avec la prononciation. Conçu pour les apprenants d'anglais.",
    },
    'de': {
        'title': 'Lexio — Englisch verstehen, wie es wirklich verwendet wird',
        'description': 'Du liest Englisch und hängst bei einem Wort fest? Lexio gibt dir die genaue Bedeutung in diesem Satz — inklusive Redewendungen und Phrasal Verbs — erklärt in deiner eigenen Sprache, mit Aussprache. Gemacht für Englischlernende.',
    },
    'it': {
        'title': "Lexio — Capisci l'inglese così com'è davvero usato",
        'description': "Leggi in inglese e ti blocchi su una parola? Lexio ti dà il significato esatto in quella frase — modi di dire e phrasal verbs inclusi — spiegato nella tua lingua, con la pronuncia. Pensato per chi impara l'inglese.",
    },
    'pt': {
        'title': 'Lexio — Entenda o inglês como ele é realmente usado',
        'description': 'Está lendo em inglês e travou numa palavra? O Lexio te dá o significado exato naquela frase — idiomatismos e phrasal verbs incluídos — explicado no seu idioma, com pronúncia. Feito para quem aprende inglês.',
    },
    'nl': {
        'title': 'Lexio — Begrijp Engels zoals het echt gebruikt wordt',
        'description': 'Lees je Engels en blijf je steken op een woord? Lexio geeft je de exacte betekenis in die zin — idiomen en phrasal verbs inbegrepen — uitgelegd in je eigen taal, met uitspraak. Gemaakt voor mensen die Engels leren.',
    },
    'ru': {
        'title': 'Lexio — Понимайте английский таким, каким его используют на самом деле',
        'description': 'Читаете по-английски и застряли на слове? Lexio даёт точное значение именно в этом предложении — включая идиомы и фразовые глаголы — с объяснением на вашем языке и произношением. Создано для изучающих английский.',
    },
    'zh': {
        'title': 'Lexio — 理解英语真实的使用方式',
        'description': '读英语时卡在某个单词上？Lexio 会给出该词在这句话里的准确含义——包括习语和短语动词——并用你的母语解释，附带发音。专为英语学习者打造。',
    },
    'ja': {
        'title': 'Lexio — 英語が実際にどう使われているかを理解する',
        'description': '英語を読んでいて単語につまずいていませんか？Lexioはその文脈での正確な意味を、イディオムや句動詞も含めて、あなたの母国語で発音付きで説明します。英語学習者のために作られました。',
    },
    'ko': {
        'title': 'Lexio — 영어가 실제로 어떻게 쓰이는지 이해하세요',
        'description': '영어를 읽다가 단어에서 막히셨나요? Lexio는 그 문장 속 정확한 의미를 관용구와 구동사까지 포함해 모국어로 설명하고 발음까지 알려줍니다. 영어 학습자를 위해 만들어졌습니다.',
    },
}
