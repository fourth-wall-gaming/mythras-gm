// Fourth Wall Gaming novel interior -- 5.5in x 8.5in trade style.
// Used via: #import "novel.typ": *  then  #show: novel.with(title: ..., author: ...)

// pandoc -t typst emits #horizontalrule for markdown "---" scene breaks.
// Note: #include files do not inherit outer scope, so body.typ must import this.
#let horizontalrule = align(center, block(above: 1.5em, below: 1.5em,
  text(size: 11pt)[⁂]))

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

  // Chapter openers: new page, drop, centered small-caps title, ornament.
  show heading.where(level: 1): it => {
    pagebreak(weak: true)
    v(16%)
    align(center, text(size: 17pt, weight: "regular", smallcaps(it.body)))
    v(0.5em)
    align(center, text(size: 11pt)[✦])
    v(2em)
  }

  body
}
