# Map of the ten Sjónabók source manuscripts for the gallery's Explore page.
# Each manuscript is marked by its signature motif (signature_motifs.R), drawn
# in the HI palette, with a timeline of the same icons above the map.
#
# Data (all in this folder):
#   manuscripts.csv  one row per book, numbered as in the project table
#   places.csv       one row per place tied to a book (main place = step 1)
#   signatures.csv   motif candidates per manuscript, picked = TRUE is used
# Unresolved places are tracked in https://github.com/HiDefTextiles/Sjonabok/issues/15
#
# Usage (from the repository root): make map
#   -> gallery/map/web/index.html (+ web/lib, shared leaflet files)
# Light for phones: no embedded coastline, leaflet files kept separate so the
# browser caches them, icons are small inline SVGs.
suppressPackageStartupMessages({
  library(readr); library(dplyr); library(purrr); library(stringr)
  library(leaflet); library(htmlwidgets); library(htmltools)
})

HI <- c(blue = "#10099F", teal = "#2DD2C0", pink = "#d61f69", grey = "#9E9E9E")
role_col <- c(made = HI[["blue"]], owned = HI[["teal"]], `later owned` = HI[["grey"]],
              uncertain = HI[["grey"]], held = HI[["grey"]], `family link` = HI[["grey"]])
ISSUE <- "https://github.com/HiDefTextiles/Sjonabok/issues/15"
GALLERY <- "../../index.html"          # map lives at <site>/map/web/

# Gallery file prefix for each museum number
source_of_id <- function(id) case_when(
  id == "N.453.a" ~ "natmus453",
  id == "Þjms. Th 116" ~ "thjmsth_116",
  TRUE ~ paste0("thjms", str_remove(id, "^Þjms\\. "))
)

# ── Motif icons: inline SVG, motif cells in HI blue on white, ring in role colour
motif_svg <- function(rows, ring, size, number = NULL) {
  cells <- str_split(str_split_1(rows, "/"), "")
  h <- length(cells); w <- length(cells[[1]]); n <- max(h, w) + 2   # 1-cell margin
  ox <- (n - w) / 2; oy <- (n - h) / 2
  on <- which(do.call(rbind, cells) == "1", arr.ind = TRUE)
  rects <- sprintf('<rect x="%g" y="%g" width="1.02" height="1.02"/>', ox + on[, 2] - 1, oy + on[, 1] - 1)
  badge <- if (!is.null(number)) sprintf(
    '<circle cx="%g" cy="%g" r="%g" fill="%s"/><text x="%g" y="%g" font-size="%g" font-family="sans-serif" font-weight="700" fill="white" text-anchor="middle">%s</text>',
    n - 1.6, 1.6, 1.9, ring, n - 1.6, 1.6 + 1.05, 2.6, number) else ""
  sprintf(paste0('<svg xmlns="http://www.w3.org/2000/svg" viewBox="-0.6 -0.6 %g %g" width="%d" height="%d">',
                 '<rect x="-0.3" y="-0.3" width="%g" height="%g" rx="1.4" fill="white" stroke="%s" stroke-width="0.6"/>',
                 '<g fill="%s">%s</g>%s</svg>'),
          n + 1.2, n + 1.2, size, size, n + 0.6, n + 0.6, ring, HI[["blue"]], paste(rects, collapse = ""), badge)
}
svg_uri <- function(svg) paste0("data:image/svg+xml;charset=utf-8,", URLencode(svg, reserved = TRUE))

# ── Data ──────────────────────────────────────────────────────────────────────
motifs <- read_csv("signatures.csv", show_col_types = FALSE) |>
  filter(picked) |> select(source, example, pages, copies, rows)

books <- read_csv("manuscripts.csv", show_col_types = FALSE) |>
  mutate(source = source_of_id(id), order = map_no,
         dot = ifelse(date_on_record, when_start, (when_start + when_end) / 2)) |>
  left_join(motifs, by = "source")

places <- read_csv("places.csv", show_col_types = FALSE) |>
  left_join(select(books, id, order, who, when_label, confidence, repository, source, example, pages, copies, rows),
            by = "id") |>
  mutate(colour = unname(role_col[role]), first = step == 1)

motif_note <- function(example, pages, copies)
  sprintf("Signature motif: on %d page%s (%d cop%s). <a href='%s#%s' target='_top'>Example in the gallery</a>",
          pages, ifelse(pages == 1, "", "s"), copies, ifelse(copies == 1, "y", "ies"), GALLERY, example)

places <- places |>
  mutate(
    icon = pmap_chr(list(rows, colour, first, order), function(r, col, f, o)
      svg_uri(motif_svg(r, col, if (f) 40 else 28, o))),
    popup = sprintf(
      "<b>%s. %s</b><br>%s<br><i>%s</i><br>%s: <b>%s</b>%s<br><small>%s</small><br>Confidence: %s<br>Now held: <b>%s</b><br>%s<br><a href='%s' target='_blank'>Museum record</a>",
      order, id, who, when_label, role, place, ifelse(is.na(when), "", paste0(" (", when, ")")),
      note, confidence, repository, motif_note(example, pages, copies), url)
  )

pl_is <- filter(places, role != "held")
unresolved <- books |> filter(!id %in% places$id)
abroad <- places |> filter(role == "held")

# ── Map ───────────────────────────────────────────────────────────────────────
m <- leaflet(options = leafletOptions(zoomSnap = 0.25, scrollWheelZoom = FALSE)) |>
  addProviderTiles(providers$CartoDB.Positron) |>
  fitBounds(-24.4, 63.3, -13.4, 66.6)

# dashed line from a book's main place to its other places
for (b in unique(pl_is$id)) {
  path <- pl_is |> filter(id == b) |> arrange(step)
  if (nrow(path) > 1)
    m <- addPolylines(m, lng = path$lon, lat = path$lat, color = HI[["blue"]],
                      weight = 2, opacity = 0.6, dashArray = "5 5")
}
add_icons <- function(map, d, size) {
  if (!nrow(d)) return(map)
  addMarkers(map, data = d, ~lon, ~lat, popup = ~popup,
             popupOptions = popupOptions(maxWidth = 240, autoPanPaddingTopLeft = c(50, 10)), label = ~paste0(order, ". ", id),
             icon = icons(iconUrl = d$icon, iconWidth = size, iconHeight = size,
                          iconAnchorX = size / 2, iconAnchorY = size / 2))
}
m <- m |>
  add_icons(filter(pl_is, !first), 28) |>
  add_icons(filter(pl_is, first), 40)

# ── Timeline: same icons on a time axis ───────────────────────────────────────
timeline_svg <- function(d, from = 1600, to = 1900, w = 640) {
  x0 <- 20; x1 <- w - 110; r <- 15
  sx <- function(y) x0 + (y - from) / (to - from) * (x1 - x0)
  dated <- d |> filter(!is.na(when_start)) |> arrange(when_start, order)
  undated <- d |> filter(is.na(when_start))
  lane_end <- numeric(0); dated$lane <- NA
  for (i in seq_len(nrow(dated))) {             # greedy lanes, nothing overlaps
    left <- min(sx(dated$when_start[i]), sx(dated$dot[i]) - r)
    right <- max(sx(dated$when_end[i]), sx(dated$dot[i]) + r)
    l <- which(lane_end < left - 4)[1]; if (is.na(l)) l <- length(lane_end) + 1
    lane_end[l] <- right; dated$lane[i] <- l
  }
  lane_y <- function(l) 20 + (l - 1) * 34
  h <- lane_y(max(dated$lane)) + 44; axis_y <- h - 22
  icon <- function(cx, cy, colour, rows, order, title)
    sprintf('<g><title>%s</title><image href="%s" x="%.1f" y="%.1f" width="%d" height="%d"/></g>',
            htmlEscape(title), pmap_chr(list(rows, colour, order), \(rw, col, o) svg_uri(motif_svg(rw, col, 2 * r, o))),
            cx - r, cy - r, 2 * r, 2 * r)
  ticks <- seq(ceiling(from / 25) * 25, to, by = 25)
  parts <- c(
    sprintf('<line x1="%d" x2="%d" y1="%d" y2="%d" stroke="%s" stroke-width="1.5"/>', x0, x1, axis_y, axis_y, HI[["blue"]]),
    sprintf('<line x1="%.1f" x2="%.1f" y1="%d" y2="%d" stroke="%s"/><text x="%.1f" y="%d" text-anchor="middle" font-size="12" fill="#333">%s</text>',
            sx(ticks), sx(ticks), axis_y, axis_y + ifelse(ticks %% 100 == 0, 6, 3), HI[["blue"]],
            sx(ticks), axis_y + 18, ifelse(ticks %% 50 == 0, ticks, "")),
    with(dated, sprintf('<line x1="%.1f" x2="%.1f" y1="%.1f" y2="%.1f" stroke="%s" stroke-opacity="0.3" stroke-width="8" stroke-linecap="round"/>',
                        sx(when_start), sx(when_end), lane_y(lane), lane_y(lane), colour)),
    with(dated, icon(sx(dot), lane_y(lane), colour, rows, order, paste0(order, ". ", id, ", ", when_label))),
    if (nrow(undated)) sprintf('<text x="%d" y="12" font-size="12" fill="#333">no date</text>', x1 + 30),
    if (nrow(undated)) with(undated, icon(x1 + 40 + (seq_along(order) - 1) * 36, 36, colour, rows, order,
                                          paste0(order, ". ", id, ", ", when_label)))
  )
  HTML(sprintf('<svg viewBox="0 0 %d %d" width="100%%" role="img" aria-label="Timeline of the manuscripts" font-family="sans-serif">%s</svg>',
               w, h, paste(parts, collapse = "")))
}
tl <- books |>
  left_join(places |> filter(first) |> select(id, colour), by = "id") |>
  mutate(colour = coalesce(colour, HI[["grey"]]))

# ── Books not on the map: place unresolved, or abroad ─────────────────────────
side_item <- function(d, text) tags$li(
  tags$img(src = svg_uri(motif_svg(d$rows, HI[["grey"]], 30, d$order)), width = 30, height = 30, alt = ""),
  tags$span(HTML(sprintf("<b>%s. %s</b> (%s): %s", d$order, d$id, d$when_label, text))))
not_mapped <- tags$div(class = "not-mapped",
  tags$h4("Not on the map"),
  tags$ul(
    map(split(unresolved, unresolved$order), function(d)
      side_item(d, sprintf("%s, place not yet identified.", coalesce(d$where, d$place_type)))),
    map(split(abroad, abroad$order), function(d)
      side_item(d, sprintf("held at %s; where it was made is unknown.", d$place)))),
  tags$p(HTML(sprintf("Open questions about places are tracked in <a href='%s' target='_top'>issue #15</a>.", ISSUE))))

page <- m |>
  prependContent(tags$meta(name = "viewport", content = "width=device-width, initial-scale=1")) |>
  prependContent(tags$style(HTML(sprintf(
    "body { margin: 0; padding: 4px !important; font: 14px sans-serif; color: #222; }
     .timeline h4, .not-mapped h4 { font: 600 14px sans-serif; color: %1$s; margin: 0 0 4px; }
     .timeline { margin-bottom: 6px; }
     .leaflet-container { width: 100%% !important; height: min(75vw, 75vh) !important; }
     .key { margin: 2px 0 6px; font-size: 13px; color: #333; }
     .key span { display: inline-block; width: 11px; height: 11px; border: 2px solid; border-radius: 3px; margin: 0 4px 0 10px; vertical-align: -2px; }
     .key span:first-child { margin-left: 0; }
     .info.legend { font-size: 11px !important; line-height: 13px !important; padding: 4px 6px !important; }
     .info.legend i { width: 11px !important; height: 11px !important; margin-right: 4px !important; }
     .not-mapped ul { list-style: none; padding: 0; margin: 4px 0; }
     .not-mapped li { display: flex; align-items: center; gap: 8px; margin: 4px 0; }
     .not-mapped p { margin: 4px 0; color: #444; }
     .not-mapped a, .leaflet-popup-content a { color: %1$s; }
     .leaflet-popup-content { font-size: 12px; margin: 10px 12px; }", HI[["blue"]])))) |>
  prependContent(tags$div(class = "timeline",
    tags$h4("When: icon at a bar end = date on record, mid-bar = estimated range"),
    timeline_svg(tl),
    tags$div(class = "key", HTML(sprintf(
      'Frame: <span style="border-color:%s"></span>made here <span style="border-color:%s"></span>owned here <span style="border-color:%s"></span>later owner, family link or uncertain. Tap an icon for details.',
      HI[["blue"]], HI[["teal"]], HI[["grey"]]))))) |>
  appendContent(not_mapped)
page$sizingPolicy$browser$fill <- FALSE
page$sizingPolicy$browser$padding <- 0

dir.create("web", showWarnings = FALSE)
saveWidget(page, "web/index.html", selfcontained = FALSE, libdir = "lib", title = "Sjónabók manuscripts")

# Keep only the library files the page loads (no source maps, unminified
# copies or default marker images): about 0.6 MB instead of 2.4 MB
used <- str_extract_all(read_file("web/index.html"), 'lib/[^"]+')[[1]]
all_lib <- list.files("web/lib", recursive = TRUE)
invisible(file.remove(file.path("web/lib", setdiff(all_lib, str_remove(used, "^lib/")))))
for (d in rev(list.dirs("web/lib"))) if (!length(list.files(d, all.files = TRUE, no.. = TRUE))) unlink(d, recursive = TRUE)
message("Wrote gallery/map/web/index.html")
