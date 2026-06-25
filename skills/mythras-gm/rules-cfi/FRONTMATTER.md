# CFI rule-piece frontmatter contract

Every `.md` file under `rules-cfi/` is ONE small rule piece: YAML frontmatter
then a short Markdown body. Required keys:

- `id`: unique, kebab, prefixed `cfi/<domain>/<slug>` (e.g. `cfi/class/cleric`)
- `title`: human title
- `system`: ALWAYS `"classic-fantasy"`
- `category` / `domain`: one of core|combat|magic|system|character|skill|creature
- `topic`: hierarchy topic within the domain
- `kind`: procedure|table|modifier|special-effect|condition|reference-list|formula|spell|class|race
- `summary`: one-sentence description (becomes the rule's `description`)
- `facets`: dict of dim -> [values]; dims: phase action effect weapon trigger
  body severity condition magic-system stat kind class race
- `links`: list of related rule ids (may target `mythras` pieces by their id)

Worked example -- `rules-cfi/magic/spell-heal.md`:

    ---
    id: "cfi/magic/spell-heal"
    title: "Heal"
    system: "classic-fantasy"
    category: "magic"
    domain: "magic"
    topic: "divine-spells"
    kind: "spell"
    summary: "Restores hit points to a single location."
    facets: {"magic-system": ["divine"], "kind": ["spell"]}
    links: ["cfi/magic/casting"]
    ---
    **Heal** restores hit points to a single damaged location...

ASCII only. Keep bodies short -- the GM fetches these live during play.
