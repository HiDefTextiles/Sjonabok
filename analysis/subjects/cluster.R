# Hierarchical clustering of Sjónabók units (see README.md).
#
#   Rscript cluster.R K W1=work/a_dist.csv W2=work/b_dist.csv ...
#
# Each distance matrix is turned into ranks scaled to 0..1, so the two
# measures are on the same scale whatever their units, and then averaged
# with the weights given. The Makefile default is 0 for shape and 1 for the
# image model: on the pilot, mixing in the shape distance put deer, stars
# and flowers in the same piles, while the image model alone kept the
# animals together. A missing matrix is left out. Ward linkage (ward.D2): it keeps clusters of even size, where
# average linkage chained most charts into one large cluster; the tree is cut into K clusters on purpose more
# than there are subjects, so that each cluster is likely to hold one
# subject. Clusters are numbered in the order of the tree, so neighbouring
# numbers look alike. hclust is deterministic: no seed is needed.
suppressPackageStartupMessages({
  library(readr)
  library(dplyr)
  library(tibble)
})

args <- commandArgs(trailingOnly = TRUE)
k <- as.integer(args[1])
pairs <- strsplit(args[-1], "=", fixed = TRUE)
weights <- as.numeric(vapply(pairs, `[`, "", 1))
files <- vapply(pairs, `[`, "", 2)
keep <- file.exists(files) & weights > 0
if (!any(keep)) keep <- file.exists(files)        # e.g. only the shape distance exists
weights <- pmax(weights[keep], 1e-9)
files <- files[keep]

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

mats <- lapply(files, read_dist)
ids <- rownames(mats[[1]])
mats <- lapply(mats, function(m) m[ids, ids])
d <- Reduce(`+`, Map(function(m, w) w * rank_scale(m), mats, weights)) / sum(weights)

tree <- hclust(as.dist(d), method = "ward.D2")
raw <- cutree(tree, k = k)
in_order <- unique(raw[tree$order])          # renumber along the tree
clusters <- tibble(id = ids, cluster = match(raw, in_order)) |>
  arrange(cluster, id)

write_csv(clusters, "work/clusters.csv")
write_csv(as_tibble(d, rownames = "id"), "work/dist.csv")

sizes <- count(clusters, cluster)
cat(sprintf("%d units, %d clusters (sizes %d to %d), from %s\n",
            length(ids), k, min(sizes$n), max(sizes$n),
            paste(sprintf("%g x %s", weights, basename(files)), collapse = " + ")))
