# Signature motif per manuscript, for the manuscript map markers.
#
# A "motif" here is one connected piece of a chart (8-neighbour cells set to 1),
# the small figures that the bands and frames are built from. For each
# manuscript we look for a small piece (icon size) that
#   1. recurs: it, or a near copy (a few cells off, any turn or mirror), is
#      found on many pages of that manuscript;
#   2. belongs to it: most of its copies are in that manuscript;
#   3. differs from the pieces picked for the other manuscripts.
# Data: patterns/min/*.txt (exact bands stored as one repeat unit, which is
# tiled three times so pieces across the seam are whole) and patterns/repeats.csv.
#
# Usage (from the repository root): Rscript gallery/map/signature_motifs.R
#   -> gallery/map/signatures.csv  (top candidates per manuscript, picked = TRUE)
#   -> gallery/map/candidates.png  (review sheet, not committed)
# Optional gallery/map/picks.csv (source,chart,rank) overrides a pick by hand.
suppressPackageStartupMessages({
  library(readr); library(dplyr); library(purrr); library(tibble); library(stringr)
})

MIN_SIDE <- 5; MAX_SIDE <- 11; MIN_CELLS <- 10   # icon-sized pieces only
NEAR <- 0.12          # near copy: at most 12% of cells differ
MIN_OWN <- 0.5        # at least half the pages with it are in this manuscript
MIN_FILL <- 0.3       # at least 30% of the box filled (no stray lines)
DISTINCT <- 0.45      # picks must differ in at least 45% of their cells
TOP <- 6              # candidates kept per manuscript

# ── Small grid helpers ────────────────────────────────────────────────────────
read_chart <- function(f) do.call(rbind, lapply(strsplit(read_lines(f), ""), as.integer))

shift <- function(m, dr, dc) {
  h <- nrow(m); w <- ncol(m); o <- matrix(0L, h, w)
  rs <- max(1, 1 + dr):min(h, h + dr); cs <- max(1, 1 + dc):min(w, w + dc)
  o[rs, cs] <- m[rs - dr, cs - dc]; o
}

# Connected pieces by label propagation (vectorised, one pass per step)
label_pieces <- function(m) {
  on <- m == 1L; lab <- matrix(0L, nrow(m), ncol(m)); lab[on] <- which(on)
  repeat {
    new <- lab
    for (dr in -1:1) for (dc in -1:1) if (dr | dc) new <- pmax(new, shift(lab, dr, dc))
    new[!on] <- 0L
    if (identical(new, lab)) return(lab)
    lab <- new
  }
}

rot90 <- function(x) t(x[nrow(x):1, , drop = FALSE])
dihedral <- function(s) { out <- list(); for (k in 1:4) { out <- c(out, list(s, t(s))); s <- rot90(s) }; out }
as_key <- function(x) paste0(nrow(x), "x", ncol(x), ":", paste(t(x), collapse = ""))
canon <- function(s) { tr <- dihedral(s); tr[[which.min(rank(vapply(tr, as_key, "")))]] }

# Share of differing cells between two pieces, best over turns and mirrors;
# pieces of other sizes are compared centred on a common canvas.
pad_to <- function(x, h, w) {
  o <- matrix(0L, h, w); r0 <- (h - nrow(x)) %/% 2; c0 <- (w - ncol(x)) %/% 2
  o[r0 + seq_len(nrow(x)), c0 + seq_len(ncol(x))] <- x; o
}
piece_distance <- function(a, b) {
  n <- max(dim(a), dim(b)); A <- pad_to(a, n, n)
  min(vapply(dihedral(pad_to(b, n, n)), function(B) sum(A != B) / sum(A | B), 0))
}

# ── Figures in every chart ────────────────────────────────────────────────────
# A figure is a box of MIN_SIDE..MAX_SIDE cells per side whose filled cells touch
# all four of its sides (tight) and whose one-cell surround is (almost) empty:
# at most RING cells, so a figure on a short stem or touching a frame still counts.
RING <- 2

box_sums <- function(m) {          # integral image, with a zero row and column
  I <- matrix(0, nrow(m) + 1, ncol(m) + 1); I[-1, -1] <- apply(apply(m, 2, cumsum), 1, cumsum) |> t(); I
}
box <- function(I, r1, c1, r2, c2) I[cbind(r2 + 1, c2 + 1)] - I[cbind(r1, c2 + 1)] - I[cbind(r2 + 1, c1)] + I[cbind(r1, c1)]

figures_of <- function(file, repeats) {
  name <- sub("\\.txt$", "", basename(file)); m <- read_chart(file)
  r <- filter(repeats, .data$name == !!name)
  axis <- if (nrow(r) && r$status == "unit") r$axis else ""
  h0 <- nrow(m); w0 <- ncol(m)
  if (axis == "x") m <- cbind(m, m, m)          # whole figures across the seam
  if (axis == "y") m <- rbind(m, m, m)
  m <- rbind(0L, cbind(0L, m, 0L), 0L)           # empty surround at the chart edge
  I <- box_sums(m); H <- nrow(m); W <- ncol(m)
  hits <- list()
  for (ih in MIN_SIDE:MAX_SIDE) for (iw in MIN_SIDE:MAX_SIDE) {
    if (ih + 2 > H || iw + 2 > W) next
    pos <- expand.grid(r = 2:(H - ih), c = 2:(W - iw))   # top-left of the inner box
    r1 <- pos$r; c1 <- pos$c; r2 <- r1 + ih - 1; c2 <- c1 + iw - 1
    inner <- box(I, r1, c1, r2, c2)
    ring <- box(I, r1 - 1, c1 - 1, r2 + 1, c2 + 1) - inner
    ok <- ring <= RING & inner >= MIN_CELLS &
      box(I, r1, c1, r1, c2) > 0 & box(I, r2, c1, r2, c2) > 0 &
      box(I, r1, c1, r2, c1) > 0 & box(I, r1, c2, r2, c2) > 0
    # tiled bands: count a figure once, when it starts in the middle copy
    if (axis == "x") ok <- ok & c1 - 1 > w0 & c1 - 1 <= 2 * w0
    if (axis == "y") ok <- ok & r1 - 1 > h0 & r1 - 1 <= 2 * h0
    if (any(ok)) hits[[length(hits) + 1]] <- tibble(r1 = r1[ok], c1 = c1[ok], r2 = r2[ok], c2 = c2[ok],
                                                    ring = ring[ok], cells = inner[ok])
  }
  if (!length(hits)) return(NULL)
  hits <- bind_rows(hits) |> arrange(ring, desc(cells))
  # overlapping boxes: keep the cleanest, then the fullest
  taken <- matrix(FALSE, H, W); keep <- logical(nrow(hits))
  for (i in seq_len(nrow(hits))) {
    rr <- hits$r1[i]:hits$r2[i]; cc <- hits$c1[i]:hits$c2[i]
    if (!any(taken[rr, cc])) { taken[rr, cc] <- TRUE; keep[i] <- TRUE }
  }
  hits[keep, ] |> mutate(chart = name, shape = pmap(list(r1, c1, r2, c2), function(r1, c1, r2, c2) canon(m[r1:r2, c1:c2, drop = FALSE])),
                         key = map_chr(shape, as_key), h = map_int(shape, nrow), w = map_int(shape, ncol)) |>
    select(chart, key, cells, h, w, shape)
}

source_of <- function(chart) str_extract(chart, "^(natmus453|thjmsth_116|thjms[0-9-]+?)(?=_)")

repeats <- read_csv("patterns/repeats.csv", show_col_types = FALSE)
cache <- Sys.getenv("PIECES_CACHE")
if (nzchar(cache) && file.exists(cache)) pieces <- readRDS(cache) else {
  pieces <- list.files("patterns/min", pattern = "\\.txt$", full.names = TRUE) |>
    map(figures_of, repeats = repeats) |> list_rbind() |>
    mutate(source = source_of(chart))
  if (nzchar(cache)) saveRDS(pieces, cache)
}

# One row per distinct shape and manuscript
shapes <- pieces |>
  group_by(source, key) |>
  summarise(cells = first(cells), h = first(h), w = first(w), shape = list(shape[[1]]),
            example = first(chart), .groups = "drop")

# Near copies: for each shape, the pages (charts) holding it or a near copy,
# in its own manuscript and elsewhere
uniq <- distinct(shapes, key, .keep_all = TRUE)
near <- map(seq_len(nrow(uniq)), function(i) {
  a <- uniq$shape[[i]]
  ok <- abs(uniq$cells - uniq$cells[i]) <= ceiling(NEAR * uniq$cells[i]) &
        abs(uniq$h - uniq$h[i]) <= 1 & abs(uniq$w - uniq$w[i]) <= 1
  cand <- which(ok)
  uniq$key[cand[vapply(cand, function(j) piece_distance(a, uniq$shape[[j]]) <= NEAR, TRUE)]]
})
names(near) <- uniq$key
chart_keys <- select(pieces, source, chart, key)   # one row per copy

recurrence <- map(seq_len(nrow(shapes)), function(i) {
  hits <- filter(chart_keys, key %in% near[[shapes$key[i]]])
  tibble(pages = n_distinct(hits$chart[hits$source == shapes$source[i]]),
         copies = sum(hits$source == shapes$source[i]),
         elsewhere = n_distinct(hits$chart[hits$source != shapes$source[i]]))
}) |> list_rbind()

cand <- bind_cols(shapes, recurrence) |>
  mutate(own = pages / (pages + elsewhere),
         score = pages * own * log1p(copies)) |>
  filter(cells / (h * w) >= MIN_FILL) |>
  # a manuscript where nothing is mostly its own keeps its shared figures
  group_by(source) |> filter(own >= MIN_OWN | !any(own >= MIN_OWN)) |> ungroup() |>
  group_by(source) |>
  arrange(desc(score), desc(cells), .by_group = TRUE)

# Keep the best few per manuscript that differ from each other, then pick one
# per manuscript so that all picks differ (clearest signatures choose first)
dedupe <- function(d) {
  keep <- integer(0)
  for (i in seq_len(nrow(d))) {
    if (all(vapply(keep, function(j) piece_distance(d$shape[[i]], d$shape[[j]]) >= DISTINCT, TRUE))) keep <- c(keep, i)
    if (length(keep) == TOP) break
  }
  d[keep, ]
}
cand <- cand |> group_modify(~ dedupe(.x)) |> mutate(rank = row_number()) |> ungroup()

picks_file <- "gallery/map/picks.csv"
manual <- if (file.exists(picks_file)) read_csv(picks_file, show_col_types = FALSE) else tibble(source = character(), rank = integer())

order_src <- cand |> group_by(source) |> summarise(best = max(score)) |> arrange(desc(best)) |> pull(source)
picked <- list(); cand$picked <- FALSE
for (s in order_src) {
  d <- filter(cand, source == s)
  forced <- manual$rank[manual$source == s]
  ok <- if (length(forced)) d$rank == forced[1] else
    vapply(seq_len(nrow(d)), function(i)
      all(vapply(picked, function(p) piece_distance(d$shape[[i]], p) >= DISTINCT, TRUE)), TRUE)
  i <- which(ok)[1]; if (is.na(i)) i <- 1
  picked[[s]] <- d$shape[[i]]
  cand$picked[cand$source == s] <- d$rank == d$rank[i]
}

as_rows <- function(s) paste(apply(s, 1, paste, collapse = ""), collapse = "/")
out <- cand |>
  mutate(rows = map_chr(shape, as_rows), own = round(own, 2), score = round(score, 2)) |>
  select(source, rank, picked, example, h, w, cells, pages, copies, elsewhere, own, score, rows)
write_csv(out, "gallery/map/signatures.csv")

# ── Review sheet: candidates per manuscript, pick framed in HI pink ───────────
labels <- c(natmus453 = "Natmus 453", thjms1105 = "Þjms. 1105", `thjms1960-60` = "Þjms. 1960-60",
            `thjms1985-235` = "Þjms. 1985-235", `thjms1997-123` = "Þjms. 1997-123",
            `thjms2007-45` = "Þjms. 2007-45", `thjms2008-14` = "Þjms. 2008-14",
            thjms5898 = "Þjms. 5898", thjms6950 = "Þjms. 6950", thjmsth_116 = "Þjms. Th 116")
srcs <- names(labels)[names(labels) %in% cand$source]
png("gallery/map/candidates.png", width = 760, height = 90 + 120 * length(srcs), res = 110, type = "cairo", family = "DejaVu Sans")
par(mar = c(0, 0, 0, 0)); plot.new(); plot.window(c(0, 7.6), c(length(srcs) + 0.6, 0))
text(0.05, 0.3, "Candidates per manuscript, best first. Pink frame = picked. Under each: pages · copies", adj = 0, cex = 0.8)
for (k in seq_along(srcs)) {
  d <- filter(cand, source == srcs[k]); y <- k - 0.1
  text(0.05, y + 0.35, labels[srcs[k]], adj = 0, cex = 0.75, font = 2, col = "#10099F")
  for (i in seq_len(nrow(d))) {
    s <- d$shape[[i]]; x0 <- 1.4 + (i - 1) * 1.03; cell <- 0.7 / MAX_SIDE
    ox <- x0 + (MAX_SIDE - ncol(s)) * cell / 2; oy <- y + (MAX_SIDE - nrow(s)) * cell / 2
    if (d$picked[i]) rect(x0 - 0.06, y - 0.06, x0 + 0.76, y + 0.76, border = "#d61f69", lwd = 2.5)
    idx <- which(s == 1L, arr.ind = TRUE)
    rect(ox + (idx[, 2] - 1) * cell, oy + (idx[, 1] - 1) * cell, ox + idx[, 2] * cell, oy + idx[, 1] * cell,
         col = "#10099F", border = NA)
    text(x0 + 0.35, y + 0.84, sprintf("%d · %d", d$pages[i], d$copies[i]), cex = 0.55, col = "#555555")
  }
}
invisible(dev.off())
message("Wrote gallery/map/signatures.csv and gallery/map/candidates.png")
