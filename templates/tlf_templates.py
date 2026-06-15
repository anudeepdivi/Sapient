TLF_SKELETON = """
library(tidyverse)
library(rtables)
library(haven)

# Load ADaM
adsl <- haven::read_xpt("data/adam/ADSL.xpt")

# --- Table generation goes here ---

# Export
rtables::export_as_txt(tbl, file = "output/{table_number}.txt")
"""