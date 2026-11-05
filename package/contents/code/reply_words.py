"""Talpy Chat's suggested replies: the few words per language that tell the
shape of the question Claude ends its reply with (pane.py asks_of). Nothing
else is decided by words: a list of options and an either/or are found by
their shape, and your usual replies come from your own chats.

Each language (its two-letter code) has:
  yes, no     the chips for a yes/no question, in that language;
  yesno       how a yes/no question starts, lowercase ("should i" …); one
              that ends with "?" is a whole question ("proceed?");
  verbs       verbs that make a question starting with them a yes/no one;
  wh          question words of an open question (which, what …): no chips;
  or          the word between the two halves of an either/or question;
  or_not      what after it isn't a second choice ("or not", "or something");
  either      how an either/or question starts, left off its first half
              ("should i", "would you rather" …);
  lead        words a question can start with that don't count (so, ok …);
  recommended how an option is marked as the one Claude recommends;
  common      a few frequent words, to tell which language a question is in
              when its start doesn't say (its Yes and No chips).
Words are matched lowercase, at word boundaries. To add a language, add its
table; nothing else changes. The rules were measured on real chats
(English); the other tables are a start.
"""

WORDS = {
    "en": {
        "yes": "Yes", "no": "No",
        "yesno": ["should i", "shall i", "should we", "shall we", "do you want", "want me to", "would you like",
                  "would you prefer", "can i", "may i", "could i", "is it ok", "is that ok", "ok to", "okay to",
                  "ready to", "ready for", "go ahead", "proceed", "do i", "does that", "is that", "is this",
                  "are you", "do you", "did you", "have you", "will you", "should it", "want to", "want that",
                  "want this", "want them", "want it", "want both", "good to", "fine to", "happy with",
                  "sound good", "sounds good", "any objection",
                  "proceed?", "go ahead?", "ok?", "okay?", "sound good?", "shall i?", "should i?", "want me to?"],
        "verbs": ["should", "shall", "do", "does", "did", "is", "are", "was", "were", "can", "could", "would", "will",
                  "may", "might", "must", "have", "has", "had", "want", "need", "ok", "okay", "ready", "any"],
        "wh": ["which", "what", "how", "where", "when", "why", "who", "whose", "whom"],
        "or": ["or"],
        "or_not": ["not", "no", "something", "anything", "should", "do you", "would you", "is there"],
        "either": ["should i", "shall i", "do you want me to", "want me to", "would you like me to", "would you prefer",
                   "do you prefer", "would you rather", "should we", "shall we", "do you want to", "do you want",
                   "is it better to"],
        "lead": ["so", "ok", "okay", "alright", "then", "and", "also", "now", "next", "anyway", "otherwise", "or"],
        "recommended": ["recommended"],
        "common": ["the", "and", "to", "is", "it", "you", "this", "that", "of", "with", "for", "now"],
    },
    "de": {
        "yes": "Ja", "no": "Nein",
        "yesno": ["soll ich", "sollen wir", "möchtest du", "willst du", "darf ich", "passt das", "ist das"],
        "verbs": ["soll", "sollen", "sollte", "möchtest", "möchten", "willst", "wollen", "darf", "kann", "können",
                  "ist", "sind", "hast", "haben", "gibt"],
        "wh": ["welche", "welcher", "welches", "was", "wie", "wo", "wann", "warum"],
        "or": ["oder"],
        "or_not": ["nicht", "so"],
        "either": ["soll ich", "sollen wir", "möchtest du", "willst du", "lieber"],
        "lead": ["also", "ok", "dann", "und", "jetzt"],
        "recommended": ["empfohlen", "empfehle"],
        "common": ["der", "die", "das", "und", "ist", "ich", "du", "nicht", "ein", "eine", "mit", "jetzt"],
    },
    "fr": {
        "yes": "Oui", "no": "Non",
        "yesno": ["dois-je", "veux-tu", "voulez-vous", "est-ce que", "je lance", "on y va"],
        "verbs": ["dois", "veux", "voulez", "faut", "peux", "puis", "est-ce"],
        "wh": ["quel", "quelle", "quels", "quelles", "que", "comment", "où", "pourquoi", "quand"],
        "or": ["ou"],
        "or_not": ["pas", "non"],
        "either": ["dois-je", "veux-tu", "voulez-vous", "préfères-tu", "préférez-vous"],
        "lead": ["alors", "donc", "ok", "et", "maintenant"],
        "recommended": ["recommandé", "recommandée", "recommande"],
        "common": ["le", "la", "les", "et", "est", "je", "tu", "vous", "une", "des", "pour", "pas"],
    },
    "es": {
        "yes": "Sí", "no": "No",
        "yesno": ["¿quieres", "¿debo", "quieres", "debo", "¿lo hago"],
        "verbs": ["quieres", "debo", "puedo"],
        "wh": ["cuál", "qué", "cómo", "dónde", "cuándo", "por qué"],
        "or": ["o"],
        "or_not": ["no"],
        "either": ["¿quieres", "quieres", "¿debo", "debo", "¿prefieres", "prefieres"],
        "lead": ["entonces", "y", "ahora", "vale"],
        "recommended": ["recomendado", "recomendada", "recomiendo"],
        "common": ["el", "los", "las", "y", "es", "que", "una", "para", "con", "ahora"],
    },
    "it": {
        "yes": "Sì", "no": "No",
        "yesno": ["vuoi", "devo"],
        "verbs": ["vuoi", "devo", "posso"],
        "wh": ["quale", "quali", "cosa", "come", "dove", "quando", "perché"],
        "or": ["oppure", "o"],
        "or_not": ["no", "meno"],
        "either": ["vuoi", "devo", "preferisci"],
        "lead": ["allora", "quindi", "e", "ora"],
        "recommended": ["consigliato", "consigliata", "consiglio"],
        "common": ["il", "lo", "gli", "che", "di", "un", "per", "sono", "questo", "non"],
    },
    "pt": {
        "yes": "Sim", "no": "Não",
        "yesno": ["queres", "devo", "quer que eu"],
        "verbs": ["queres", "devo", "posso", "quer"],
        "wh": ["qual", "quais", "como", "onde", "quando", "porquê", "por que"],
        "or": ["ou"],
        "or_not": ["não"],
        "either": ["queres", "devo", "preferes", "prefere"],
        "lead": ["então", "e", "agora"],
        "recommended": ["recomendado", "recomendada", "recomendo"],
        "common": ["os", "as", "um", "uma", "para", "não", "isso", "com", "agora", "é"],
    },
}
