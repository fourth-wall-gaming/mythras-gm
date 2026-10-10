// Fourth Wall Gaming novel interior -- 5.5in x 8.5in trade style.
// Used via: #import "novel.typ": *  then  #show: novel.with(title: ..., author: ...)

// pandoc -t typst emits #horizontalrule for markdown "---" scene breaks.
// Note: #include files do not inherit outer scope, so body.typ must import this.
#let horizontalrule = align(center, block(above: 1.5em, below: 1.5em,
  text(size: 11pt)[⁂]))

// Non-human speech. The manuscript writes `::: glint` ... `:::`; novelist.py
// rewrites that to #voice("glint")[...] before pandoc, because pandoc's typst
// writer throws Div classes away. An unknown name falls through to body text
// rather than erroring.
//
// Each family is a fallback chain. The first name is the preferred face; the
// last is one of the three families Typst bundles -- Libertinus Serif (the
// body), New Computer Modern, DejaVu Sans Mono -- so the book always builds,
// on any machine, with the voices still distinct from each other and from the
// body. Trim a chain to its bundled tail for a byte-identical build anywhere.
#let voice-styles = (
  // A glint talks in pulses of colour, not with a mouth. Humanist sans: light,
  // open, obviously not a voice -- and not machine-like, because the one
  // machine in this book speaks in serif italic.
  glint:  (font: ("Optima", "Avenir Next", "Gill Sans", "DejaVu Sans Mono"),
           size: 0.95em, style: "normal", tracking: 0.03em, leading: 0.70em),
  // A fathom is eyeless and arrives inside your head. A second serif, italic:
  // narrower and higher-contrast than the body, precise to the point of prim.
  fathom: (font: ("New Computer Modern", "Libertinus Serif"),
           size: 1.02em, style: "italic", tracking: 0.02em, leading: 0.66em),
  // A station mind on an ear pin. The closest of the three to a human voice,
  // and set in the body face to say so.
  pin:    (font: ("Libertinus Serif",),
           size: 1em, style: "italic", tracking: 0.01em, leading: 0.68em),
)

#let voice(kind, body) = {
  let s = voice-styles.at(kind, default: (
    font: ("Libertinus Serif",), size: 1em, style: "normal",
    tracking: 0em, leading: 0.68em))
  block(inset: (left: 1.3em, right: 0.5em), above: 1.15em, below: 1.15em, {
    set par(justify: false, first-line-indent: 0em, leading: s.leading)
    set text(font: s.font, size: s.size, style: s.style, tracking: s.tracking)
    body
  })
}

#let novel(title: "Untitled", author: "", body) = {
  set document(title: title, author: author)
  set text(size: 10.5pt, lang: "en")
  set par(justify: true, leading: 0.68em, first-line-indent: 1.2em)

  // Title page (its own page params; no header/footer).
  page(width: 5.5in, height: 8.5in, margin: (x: 0.8in, y: 0.8in),
       header: none, footer: none)[
    #align(center + horizon)[
      #text(size: 25pt)[#smallcaps(title)]
      #v(3em)
      #text(size: 12pt, style: "italic")[#author]
    ]
  ]

  // Interior pages: running headers, page numbers.
  set page(
    width: 5.5in, height: 8.5in,
    margin: (inside: 0.8in, outside: 0.6in, top: 0.75in, bottom: 0.75in),
    numbering: "1",
    header: context {
      let pg = counter(page).get().first()
      if calc.even(pg) {
        align(center, text(size: 8.5pt, smallcaps(title)))
      } else {
        let chapters = query(selector(heading.where(level: 1)).before(here()))
        if chapters.len() > 0 {
          align(center, text(size: 8.5pt, smallcaps(chapters.last().body)))
        }
      }
    },
  )
  counter(page).update(1)

  // Plates. A novel has pictures, not figures: no "Figure 1:" and no numbering,
  // just the caption under the image, quiet and out of the way.
  set figure(numbering: none, gap: 0.9em)
  show figure.caption: it => text(size: 8.5pt, style: "italic", fill: luma(45%), it.body)
  show figure: set block(breakable: false)

  // Chapter openers: new page, centered small-caps title, ornament.
  show heading.where(level: 1): it => {
    pagebreak(weak: true)
    v(16%)
    align(center, text(size: 17pt, weight: "regular", smallcaps(it.body)))
    v(0.5em)
    // U+2756 BLACK DIAMOND MINUS WHITE X. Do NOT use U+2726 (BLACK FOUR
    // POINTED STAR) here: it is absent from Typst's default New Computer
    // Modern and renders as a missing-glyph box on every chapter opener.
    // U+2733 falls back to a colour emoji font. U+2756 and U+2042 both
    // render correctly; keep them distinct (2756 chapters, 2042 scene breaks).
    align(center, text(size: 11pt)[❖])
    v(2em)
  }

  body
}
