#!/usr/bin/env Rscript
# Build a metacore object from a human-approved JSON spec (specs/approved/<DATASET>.json).
# Usage: Rscript build_metacore_from_spec.R ADSL
args <- commandArgs(trailingOnly = TRUE)
dataset <- args[1]
suppressMessages({library(metacore); library(jsonlite)})

spec <- fromJSON(sprintf("specs/approved/%s.json", dataset))
n <- nrow(spec)

ds_spec <- data.frame(dataset = dataset, structure = NA_character_, label = dataset)
ds_vars <- data.frame(dataset = dataset, variable = spec$variable, keep = TRUE,
                      key_seq = NA_integer_, order = seq_len(n),
                      core = NA_character_, supp_flag = FALSE)
var_spec <- data.frame(variable = spec$variable, label = spec$label,
                       length = NA_integer_, type = spec$type,
                       common = NA, format = NA_character_)
value_spec <- data.frame(dataset = dataset, variable = spec$variable,
                         where = NA_character_, type = spec$type,
                         sig_dig = NA_integer_, code_id = NA_character_,
                         origin = spec$origin, derivation_id = spec$variable)
derivations <- data.frame(derivation_id = spec$variable, derivation = spec$derivation)
codelist <- data.frame(code_id = character(), name = character(),
                       type = character(), codes = character())

mc <- metacore(ds_spec = ds_spec, ds_vars = ds_vars, var_spec = var_spec,
               value_spec = value_spec, derivations = derivations, codelist = codelist)
out <- sprintf("specs/approved/%s_metacore.rds", dataset)
saveRDS(mc, out)
cat(out, "\n")
