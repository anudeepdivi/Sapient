#!/usr/bin/env Rscript
# Build ONE combined metacore object from all human-approved generated specs
# (specs/approved/<DS>.json) -> specs/generated_spec.rds. This is the closed-loop
# counterpart to specs/metacore_spec.rds (the pilot Define-XML): once built, the
# code-generation grounding can point here instead of the reference spec.
suppressMessages({library(metacore); library(jsonlite)})

files <- list.files("specs/approved", pattern = "\\.json$", full.names = TRUE)
ds_spec <- data.frame(); ds_vars <- data.frame(); var_spec <- data.frame()
value_spec <- data.frame(); derivations <- data.frame()

type_map <- c(text = "text", integer = "integer", float = "float", date = "integer")

for (f in files) {
  dataset <- sub("\\.json$", "", basename(f))
  spec <- fromJSON(f)
  spec <- spec[!duplicated(spec$variable), ]
  n <- nrow(spec)
  types <- unname(ifelse(spec$type %in% names(type_map), type_map[spec$type], "text"))

  ds_spec <- rbind(ds_spec, data.frame(
    dataset = dataset, structure = NA_character_, label = dataset))
  ds_vars <- rbind(ds_vars, data.frame(
    dataset = dataset, variable = spec$variable, keep = TRUE,
    key_seq = NA_integer_, order = seq_len(n), core = NA_character_, supp_flag = FALSE))
  var_spec <- rbind(var_spec, data.frame(
    variable = paste(dataset, spec$variable, sep = "."), length = NA_integer_,
    label = spec$label, type = types, common = NA, format = NA_character_))
  value_spec <- rbind(value_spec, data.frame(
    dataset = dataset, variable = spec$variable, where = NA_character_, type = types,
    sig_dig = NA_integer_, code_id = NA_character_, origin = spec$origin,
    derivation_id = paste(dataset, spec$variable, sep = ".")))
  derivations <- rbind(derivations, data.frame(
    derivation_id = paste(dataset, spec$variable, sep = "."),
    derivation = ifelse(is.na(spec$derivation) | spec$derivation == "",
                        "generated", spec$derivation)))
}

var_spec <- var_spec[!duplicated(var_spec$variable), ]
derivations <- derivations[!duplicated(derivations$derivation_id), ]
codelist <- data.frame(code_id = character(), name = character(),
                       type = character(), codes = character())

mc <- metacore(ds_spec = ds_spec, ds_vars = ds_vars, var_spec = var_spec,
               value_spec = value_spec, derivations = derivations, codelist = codelist)
save_metacore(mc, "specs/generated_spec.rds")
cat("specs/generated_spec.rds:", nrow(ds_spec), "datasets,", nrow(ds_vars), "variables\n")
