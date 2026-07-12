#!/usr/bin/env Rscript
# Source a generated TLF program, capture the pre-rendering result data frame
# from its rtables object `tbl`, write it to data/tlf_frames/<table>.csv.
# Usage: Rscript extract_tlf_frame.R <program.R> <table_number>
args <- commandArgs(trailingOnly = TRUE)
program <- args[1]
table_number <- args[2]

env <- new.env()
export_as_txt <- function(...) invisible(NULL)  # neutralize rendering export
assign("export_as_txt", export_as_txt, envir = env)
sys.source(program, envir = env)

tbl <- get("tbl", envir = env)
df <- rtables::as_result_df(tbl)
dir.create("data/tlf_frames", showWarnings = FALSE, recursive = TRUE)
out <- sprintf("data/tlf_frames/%s.csv", table_number)
write.csv(df, out, row.names = FALSE)
cat(out, "\n")
