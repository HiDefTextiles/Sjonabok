# Do patterns travel? Map and timeline of the printed European pattern books
# next to the Icelandic Sjónabók manuscripts, for the gallery's Explore page.
#
# Data:
#   ../../books/books.csv          one row per printed book (place, dates, holder, rights,
#                                  copied_from = the book the museum says it copies)
#   ../../books/travel/shared.csv  sub-motifs found both in a book and in a manuscript
#                                  (books/travel.py)
#   manuscripts.csv, places.csv    the Icelandic manuscripts (as for manuscript_map.R)
#
# Usage (from the repository root): make books-map  -> gallery/map/web/europe.html
suppressPackageStartupMessages({
  library(readr); library(dplyr); library(purrr); library(stringr); library(tidyr)
  library(leaflet); library(htmlwidgets); library(htmltools)
})

HI <- c(blue = "#10099F", teal = "#2DD2C0", pink = "#d61f69", grey = "#9E9E9E")
SHORT <- c(sib = "Sibmacher", quentel = "Quentel", jobin = "Jobin", vavassore = "Vavassore",
           pagano = "Pagano", vinciolo = "Vinciolo", bretschneider = "Bretschneider",
           schoensperger = "Schönsperger", tagliente = "Tagliente", fuerst = "Fürst",
           egenolff = "Egenolff", gulfferich = "Gülfferich", hoffmann = "Hoffmann", vorsterman = "Vorsterman", latomus = "Latomus", martin = "Martin")
source_of_id <- function(id) case_when(
  id == "N.453.a" ~ "natmus453",
  id == "Þjms. Th 116" ~ "thjmsth_116",
  TRUE ~ paste0("thjms", str_remove(id, "^Þjms\\. "))
)

# ── Data ──────────────────────────────────────────────────────────────────────
books <- read_csv("../../books/books.csv", show_col_types = FALSE) |>
  mutate(first = coalesce(first_edition, year),
         digitised = str_detect(status, "digitised") & !str_detect(status, "not digitised"),
         short = paste(SHORT[str_remove(code, "\\d+$")], year))

mss <- read_csv("manuscripts.csv", show_col_types = FALSE) |>
  mutate(source = source_of_id(id))
main_place <- read_csv("places.csv", show_col_types = FALSE) |>
  filter(step == 1) |> select(id, place, lat, lon, role)
mss <- left_join(mss, main_place, by = "id")

shared <- read_csv("../../books/travel/shared.csv", show_col_types = FALSE) |>
  mutate(motif = row_number())
links <- shared |>
  separate_longer_delim(book_sources, "; ") |>
  separate_longer_delim(manuscript_sources, "; ") |>
  count(book = book_sources, source = manuscript_sources, name = "figures") |>
  left_join(select(books, book = code, blat = lat, blon = lon, bfirst = first, short, bplace = place), by = "book") |>
  left_join(select(mss, source, id, mlat = lat, mlon = lon, when_start, when_end, when_label), by = "source")

copies <- books |> filter(!is.na(copied_from)) |>
  left_join(select(books, copied_from = code, clat = lat, clon = lon, cfirst = first), by = "copied_from")

esc <- function(x) htmlEscape(coalesce(as.character(x), ""))
book_popup <- with(books, sprintf(
  "<b>%s</b><br>%s, %s %s%s<br>%s<br>%s %s<br>%s%s<br><i>%s</i>",
  esc(title), esc(publisher), esc(place), esc(year),
  ifelse(!is.na(first_edition) & first_edition != year, sprintf(" (first edition %s)", first_edition), ""),
  esc(author), esc(holder), esc(accession),
  ifelse(is.na(record_url), "", sprintf("<a href='%s' target='_blank'>museum record</a>, ", record_url)),
  esc(rights), esc(coalesce(copied_note, notes))))

# ── Map ───────────────────────────────────────────────────────────────────────
m <- leaflet(options = leafletOptions(zoomSnap = 0.25, scrollWheelZoom = FALSE)) |>
  addTiles(attribution = '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> contributors') |>
  fitBounds(-24, 43, 16, 66.5)

# copying the museums document between books: grey dashes
for (i in seq_len(nrow(copies)))
  m <- addPolylines(m, lng = c(copies$clon[i], copies$lon[i]), lat = c(copies$clat[i], copies$lat[i]),
                    color = HI[["grey"]], weight = 2, dashArray = "4 6", opacity = 0.9,
                    label = sprintf("%s copies %s (museum record)", copies$code[i], copies$copied_from[i]))
# shared sub-motifs between a book and a manuscript: pink, thicker = more figures
ml <- filter(links, !is.na(mlat))
for (i in seq_len(nrow(ml)))
  m <- addPolylines(m, lng = c(ml$blon[i], ml$mlon[i]), lat = c(ml$blat[i], ml$mlat[i]),
                    color = HI[["pink"]], weight = 1.5 + ml$figures[i], opacity = 0.55,
                    label = sprintf("%d shared figure(s): %s %s and %s", ml$figures[i], ml$short[i], "", ml$id[i]))

m <- m |>
  addCircleMarkers(data = books, ~lon, ~lat, radius = ~ifelse(digitised, 9, 6),
                   color = "white", weight = 1.5, fillOpacity = 1,
                   fillColor = ~ifelse(digitised, HI[["pink"]], HI[["grey"]]),
                   label = ~sprintf("%s, %s", short, place), popup = book_popup) |>
  addCircleMarkers(data = filter(mss, !is.na(lat)), ~lon, ~lat, radius = 6,
                   color = "white", weight = 1.5, fillOpacity = 1, fillColor = HI[["blue"]],
                   label = ~sprintf("%s (%s)", id, when_label),
                   popup = ~sprintf("<b>%s</b><br>%s<br>%s", id, esc(place), esc(when_label)))

# ── Timeline: books and manuscripts on one axis, shared figures joined ─────────
timeline_svg <- function(from = 1520, to = 1900, w = 760) {
  x0 <- 178; x1 <- w - 10
  sx <- function(y) x0 + (y - from) / (to - from) * (x1 - x0)
  b <- books |> arrange(first) |> mutate(y = 22 + (row_number() - 1) * 18)
  d <- mss |> filter(!is.na(when_start)) |> arrange(when_start) |>
    mutate(y = max(b$y) + 40 + (row_number() - 1) * 18, mid = (when_start + when_end) / 2)
  h <- max(d$y) + 40; axis_y <- h - 22
  bar <- function(a, z, y, col, op) sprintf(
    '<line x1="%.1f" x2="%.1f" y1="%d" y2="%d" stroke="%s" stroke-opacity="%s" stroke-width="8" stroke-linecap="round"/>',
    sx(a), pmax(sx(z), sx(a) + 0.1), y, y, col, op)
  lab <- function(y, text) sprintf('<text x="%d" y="%d" font-size="11" text-anchor="end" fill="#333">%s</text>', x0 - 8, y + 4, htmlEscape(text))
  ln <- links |> inner_join(select(b, book = code, by = y), by = "book") |>
    inner_join(select(d, source, my = y, mid), by = "source")
  ticks <- seq(ceiling(from / 20) * 20, to, by = 20)
  parts <- c(
    sprintf('<text x="4" y="12" font-size="12" font-weight="600" fill="%s">Printed pattern books</text>', HI[["pink"]]),
    sprintf('<text x="4" y="%d" font-size="12" font-weight="600" fill="%s">Icelandic manuscripts</text>', min(d$y) - 14, HI[["blue"]]),
    with(ln, sprintf('<path d="M%.1f %d C %.1f %d, %.1f %d, %.1f %d" fill="none" stroke="%s" stroke-opacity="0.45" stroke-width="%.1f"><title>%d shared figure(s)</title></path>',
                     sx(bfirst), by, sx(bfirst), (by + my) / 2, sx(mid), (by + my) / 2, sx(mid), my, HI[["pink"]], 0.8 + figures * 0.8, figures)),
    with(b, bar(first, year, y, ifelse(digitised, HI[["pink"]], HI[["grey"]]), 0.9)),
    with(b, lab(y, sprintf("%s, %s", short, place))),
    with(d, bar(when_start, when_end, y, HI[["blue"]], 0.7)),
    with(d, lab(y, id)),
    sprintf('<line x1="%d" x2="%d" y1="%d" y2="%d" stroke="%s"/>', x0, x1, axis_y, axis_y, HI[["blue"]]),
    sprintf('<line x1="%.1f" x2="%.1f" y1="%d" y2="%d" stroke="%s"/><text x="%.1f" y="%d" text-anchor="middle" font-size="11" fill="#333">%s</text>',
            sx(ticks), sx(ticks), axis_y, axis_y + 4, HI[["blue"]], sx(ticks), axis_y + 17, ifelse(ticks %% 40 == 0, ticks, ""))
  )
  HTML(sprintf('<svg viewBox="0 0 %d %d" width="100%%" role="img" aria-label="Timeline of pattern books and manuscripts" font-family="sans-serif">%s</svg>',
               w, h, paste(parts, collapse = "")))
}

n_fig <- nrow(shared)
note <- sprintf(paste(
  "Pink lines join a printed book to a manuscript when both hold the same figure (%d figures so far,",
  "matched cell by cell allowing turns, mirroring and a cell of difference; see books/travel).",
  "Grey dashes: copying the museum records between books. Pink dots = digitised (partly), grey = listed.",
  "Bars run from first edition to the edition held; Icelandic bars are the date range on record",
  "(undated manuscripts are left off the timeline but kept on the map)."), n_fig)

page <- m |>
  prependContent(tags$meta(name = "viewport", content = "width=device-width, initial-scale=1")) |>
  prependContent(tags$style(HTML(sprintf(
    "body { margin: 0; padding: 4px !important; font: 14px sans-serif; color: #222; }
     h4 { font: 600 14px sans-serif; color: %1$s; margin: 0 0 4px; }
     .timeline svg { max-width: 820px; display: block; }
     .note { font-size: 12px; color: #444; max-width: 820px; margin: 4px 0 8px; }
     .leaflet { width: 100%% !important; height: min(70vw, 75vh) !important; }
     .leaflet-tile-pane { filter: grayscale(1) sepia(0.2) hue-rotate(190deg) saturate(1.3) brightness(1.12) contrast(0.72); opacity: 0.85; }
     .leaflet-container { background: #f4f5fb; }
     .leaflet-popup-content { font-size: 12px; margin: 10px 12px; }
     .leaflet-popup-content a { color: %1$s; }", HI[["blue"]])))) |>
  prependContent(tags$div(class = "timeline",
    tags$h4("Do patterns travel? Printed pattern books and the Icelandic manuscripts"),
    timeline_svg(), tags$p(class = "note", note)))
page$sizingPolicy$browser$fill <- FALSE
page$sizingPolicy$browser$padding <- 0

dir.create("web", showWarnings = FALSE)
saveWidget(page, "web/europe.html", selfcontained = FALSE, libdir = "lib", title = "Pattern books and manuscripts")
