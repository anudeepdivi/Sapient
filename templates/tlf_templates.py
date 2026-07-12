TLF_SKELETON = """
library(dplyr)
library(rtables)
library(tern)
library(haven)

# Load ADaM (only datasets that exist in data/adam/)
adsl <- haven::read_xpt("data/adam/ADSL.xpt")

# --- build an rtables layout with the tern/rtables functions from the
# --- SIGNATURES block, then: tbl <- build_table(lyt, <analysis dataset>)

# Export
formatters::export_as_txt(tbl, file = "output/{table_number}.txt")
"""
