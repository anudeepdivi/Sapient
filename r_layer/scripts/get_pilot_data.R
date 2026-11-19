#!/usr/bin/env Rscript
# Fetch the public CDISC pilot study (CDISCPILOT01) data Sapient runs on. Skips any file
# that already exists, so it is safe to run again.
#   data/sdtm/            SDTM: the pharmaversesdtm package (DM, AE, EX, DS, VS, MH, SV, LB),
#                         plus QS and SC from the pilot's own submission package
#   data/reference/pilot/ the pilot's own ADaM datasets: the answer key, never shown to the AI
#   data/adam/ADSL.xpt    the parent ADSL that ADAE reads (the pilot's own ADSL)
# Usage: Rscript r_layer/scripts/get_pilot_data.R [all]   ("all" also fetches ADLBC and ADTTE, ~34 MB)
suppressMessages(library(haven))
args <- commandArgs(trailingOnly = TRUE)
pilot <- paste0("https://raw.githubusercontent.com/cdisc-org/sdtm-adam-pilot-project/master/",
                "updated-pilot-submission-package/900172/m5/datasets/cdiscpilot01/")
for (d in c("data/sdtm", "data/reference/pilot", "data/adam")) dir.create(d, recursive = TRUE, showWarnings = FALSE)

fetch <- function(url, dest) {
  if (file.exists(dest)) return(invisible())
  cat("downloading", dest, "\n")
  tmp <- paste0(dest, ".part")
  download.file(url, tmp, mode = "wb", quiet = TRUE)
  file.rename(tmp, dest)
}

for (d in c("dm", "ae", "ex", "ds", "vs", "mh", "sv", "lb")) {
  dest <- sprintf("data/sdtm/%s.xpt", toupper(d))
  if (file.exists(dest)) next
  cat("writing", dest, "from pharmaversesdtm\n")
  e <- new.env()
  data(list = d, package = "pharmaversesdtm", envir = e)
  write_xpt(get(d, envir = e), dest)
}
for (d in c("qs", "sc")) fetch(paste0(pilot, "tabulations/sdtm/", d, ".xpt"), sprintf("data/sdtm/%s.xpt", toupper(d)))

reference <- if (identical(args[1], "all")) c("adsl", "adae", "adlbc", "adtte") else c("adsl", "adae")
for (d in reference) fetch(paste0(pilot, "analysis/adam/datasets/", d, ".xpt"), sprintf("data/reference/pilot/%s.xpt", toupper(d)))

if (!file.exists("data/adam/ADSL.xpt")) {
  cat("using the pilot's own ADSL as the parent for ADAE: data/adam/ADSL.xpt\n")
  invisible(file.copy("data/reference/pilot/ADSL.xpt", "data/adam/ADSL.xpt"))
}
cat("pilot data ready\n")
