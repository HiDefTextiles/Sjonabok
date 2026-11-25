# Recurring sub-motifs across the ten manuscripts, in Helga's time order.
#
#   Rscript timeline.R [MIN_BOOKS] [MIN_CELLS]
#
# Reads work/submotifs/occurrences.csv and motifs.csv (submotifs.py) and
# manuscript_dates.csv; writes work/submotifs/timeline.csv (sub-motif by
# manuscript, number of charts) and work/submotifs/timeline.png: one row per
# sub-motif found in at least MIN_BOOKS manuscripts, ordered by the earliest
# manuscript it appears in, with a picture of the sub-motif on the left.
# Manuscripts without a date on record (5898, 1960-60) are kept, in Helga's
# order, and marked "?".

suppressPackageStartupMessages({
  library(readr); library(dplyr); library(tidyr); library(ggplot2); library(png); library(grid)
})

args <- commandArgs(trailingOnly = TRUE)
min_books <- if (length(args) >= 1) as.integer(args[1]) else 3
min_cells <- if (length(args) >= 2) as.integer(args[2]) else 15
dir <- "work/submotifs"

dates <- read_csv("manuscript_dates.csv", show_col_types = FALSE) |>
  mutate(short = sub("Þjms. ", "", manuscript, fixed = TRUE),
         when = ifelse(is.na(when_start), "?", sub("th century", "th c.", sub("^c\\. ", "c.", when_label))),
         label = paste0(order, "\n", short, "\n", when))
motifs <- read_csv(file.path(dir, "motifs.csv"), show_col_types = FALSE)
occ <- read_csv(file.path(dir, "occurrences.csv"), show_col_types = FALSE)

keep <- motifs |> filter(manuscripts >= min_books, cells >= min_cells)
tab <- occ |>
  semi_join(keep, by = "submotif") |>
  count(submotif, source = manuscript, name = "charts") |>
  left_join(dates, by = "source")

first <- tab |> group_by(submotif) |>
  summarise(first = min(order), books = n_distinct(source), total = sum(charts), .groups = "drop") |>
  arrange(first, desc(books), desc(total)) |>
  mutate(row = row_number())

tab <- tab |> left_join(first, by = "submotif")
write_csv(tab |> select(submotif, manuscript, order, when_label, charts, books, total) |> arrange(submotif, order),
          file.path(dir, "timeline.csv"))

n <- nrow(first)
p <- ggplot(tab, aes(x = order, y = -row)) +
  geom_point(aes(size = charts), colour = "#10099F") +
  scale_size_area(max_size = 6, breaks = c(1, 3, 10, 30), name = "Charts") +
  scale_x_continuous(breaks = dates$order, labels = dates$label, limits = c(-0.6, 10.5),
                     position = "top") +
  scale_y_continuous(breaks = -first$row, labels = paste0("#", first$submotif), expand = expansion(add = 0.8)) +
  labs(x = NULL, y = NULL,
       title = "Recurring sub-motifs across the manuscripts",
       subtitle = sprintf("Sub-motifs (at least %d cells) found in %d or more manuscripts; manuscripts in time order", min_cells, min_books)) +
  theme_minimal(base_size = 9) +
  theme(panel.grid.minor = element_blank(), plot.title = element_text(colour = "#10099F", face = "bold"), text = element_text(colour = "#262626"), axis.text.x = element_text(size = 6.5, lineheight = 0.9),
        legend.position = "bottom")

# picture of each sub-motif in the left margin column (x = 0)
for (k in seq_len(n)) {
  f <- file.path(dir, "png", paste0(first$submotif[k], ".png"))
  if (!file.exists(f)) next
  img <- readPNG(f)
  h <- dim(img)[1]; w <- dim(img)[2]; s <- 0.42 / max(h, w)
  p <- p + annotation_custom(rasterGrob(img, interpolate = FALSE),
                             xmin = -w * s * 1.6, xmax = w * s * 1.6,
                             ymin = -first$row[k] - h * s, ymax = -first$row[k] + h * s)
}

ggsave(file.path(dir, "timeline.png"), p, width = 8, height = 1.6 + 0.32 * n, dpi = 200, bg = "white")
cat(sprintf("%d sub-motifs in %d+ manuscripts -> %s\n", n, min_books, file.path(dir, "timeline.png")))
