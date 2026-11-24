# Look-alike families for every chart, found without labels (see README.md).
#
#   Rscript families.R [K_FAMILY] [K_CLOSE]
#
# Bands (borders, edgings, vertical bands; compared by one repeat) and
# stand-alone motifs are grouped separately, because they are used
# differently, in the gallery and in pattern synthesis. Each gets its own
# tree; families are numbered M1, M2, ... for motifs and B1, B2, ... for bands.
#
# Uses the distances that weights.csv names, with the weights learnt from the
# people's labels (`subjects.py learn`), so the people chose which features
# count, but the grouping itself sees no labels. Each Ward tree gives:
#   family        each tree cut into K_FAMILY large groups (default 8)
#   close         the same tree cut finer, K_CLOSE groups (default 24); each
#                 close family sits inside one family
#   order         the charts' order along the tree: neighbours look alike,
#                 so sorting by it walks through the collection like with like
#   x, y          a two-dimensional map (t-SNE, fixed seed) where nearby
#                 charts look alike
#   example       the chart closest to all others in its close family
# Output: families.csv (kept in git, so the gallery can be built without the
# image model).
suppressPackageStartupMessages({
  library(readr)
  library(dplyr)
  library(tibble)
  library(Rtsne)
})

args <- commandArgs(trailingOnly = TRUE)
k_family <- if (length(args) >= 1) as.integer(args[1]) else 8L
k_close <- if (length(args) >= 2) as.integer(args[2]) else 24L

file_for <- function(name) {
  switch(name,
         image = "work/embed_all_dist.csv",
         image_tiled = "work/embed_tiled_dist.csv",
         file.path("work/all", paste0(name, "_dist.csv")))
}

read_dist <- function(path) {
  m <- read_csv(path, show_col_types = FALSE)
  ids <- m$id
  m <- as.matrix(select(m, -id))
  dimnames(m) <- list(ids, ids)
  m
}

rank_scale <- function(m) {
  r <- m
  up <- upper.tri(m)
  r[up] <- (rank(m[up]) - 1) / (sum(up) - 1)
  r[lower.tri(r)] <- t(r)[lower.tri(r)]
  diag(r) <- 0
  r
}

weights <- read_csv("weights.csv", show_col_types = FALSE) |> filter(weight > 0)
mats <- lapply(weights$distance, function(n) read_dist(file_for(n)))
ids <- rownames(mats[[1]])
mats <- lapply(mats, function(m) m[ids, ids])
d <- Reduce(`+`, Map(function(m, w) w * rank_scale(m), mats, weights$weight)) / sum(weights$weight)

kinds <- read_csv("work/all/kinds.csv", show_col_types = FALSE)
is_band <- kinds$band[match(ids, kinds$id)] == 1

# one tree per part (motifs, bands); order runs through motifs first, then bands
family <- character(length(ids)); close <- character(length(ids)); order <- integer(length(ids))
offset <- 0L
for (part in c("M", "B")) {
  i <- which(if (part == "M") !is_band else is_band)
  tree <- hclust(as.dist(d[i, i]), method = "ward.D2")
  renumber <- function(raw) match(raw, unique(raw[tree$order]))   # numbered along the tree
  f <- renumber(cutree(tree, k = k_family))
  cl <- renumber(cutree(tree, k = k_close))
  family[i] <- paste0(part, f)
  close[i] <- paste0(part, sprintf("%02d", cl))
  order[i] <- offset + match(seq_along(i), tree$order)
  offset <- offset + length(i)
}

set.seed(2026)
map <- Rtsne(as.dist(d), is_distance = TRUE, perplexity = 20, theta = 0, max_iter = 2000,
             check_duplicates = FALSE)$Y

example <- rep(FALSE, length(ids))
for (c in unique(close)) {
  i <- which(close == c)
  example[i[which.min(rowSums(d[i, i, drop = FALSE]))]] <- TRUE
}

out <- tibble(id = ids, family = family, close = close, order = order,
              x = round(map[, 1], 2), y = round(map[, 2], 2), example = example) |>
  arrange(order)
write_csv(out, "families.csv")

sizes <- count(out, family)$n
cat(sprintf("%d charts: %d families (%d to %d charts), %d close families; weights %s\n",
            length(ids), length(sizes), min(sizes), max(sizes), length(unique(out$close)),
            paste(sprintf("%s %g", weights$distance, weights$weight), collapse = ", ")))
