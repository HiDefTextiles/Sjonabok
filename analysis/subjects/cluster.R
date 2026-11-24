# Hierarchical clustering of Sjónabók units (see README.md).
#
#   Rscript cluster.R K work/shape_dist.csv [work/embed_dist.csv]
#
# Each distance matrix is turned into ranks scaled to 0..1, so the two
# measures count equally whatever their units. With one matrix it is used
# alone. Ward linkage (ward.D2): it keeps clusters of even size, where
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
files <- args[-1]
files <- files[file.exists(files)]

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
d <- Reduce(`+`, lapply(mats, rank_scale)) / length(mats)

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
            paste(basename(files), collapse = " + ")))
