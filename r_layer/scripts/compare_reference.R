library(admiral)
library(haven)

args <- commandArgs(trailingOnly = TRUE)
dataset_name <- args[1]

tryCatch({
  generated <- haven::read_xpt(sprintf("data/adam/%s.xpt", dataset_name))
  reference <- haven::read_xpt(sprintf("data/reference/%s.xpt", dataset_name))
  admiral::expect_dfs_equal(generated, reference)
  cat("SUCCESS: datasets match reference\n")
}, error = function(e) {
  cat(sprintf("MISMATCH: %s\n", conditionMessage(e)))
  quit(status = 1)
})