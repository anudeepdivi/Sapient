ADAM_SKELETON = """
library(admiral)
library(metacore)
library(xportr)
library(tidyverse)
library(haven)

# Load spec
mc <- metacore::load_metacore("specs/metacore_spec.rds")
# Load SDTM
sdtm <- haven::read_xpt("data/sdtm/{dataset}.xpt")

# --- Derivations go here ---

# Metacore compliance check
metacore::check_variables(dataset, mc)
# Export
xportr::xportr_write(dataset, path = "data/adam/{dataset}.xpt")
"""