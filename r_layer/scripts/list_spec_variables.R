library(metacore)

args <- commandArgs(trailingOnly = TRUE)
dataset_name <- args[1]

mc <- metacore::load_metacore(Sys.getenv("SAPIENT_SPEC_RDS", unset = "specs/metacore_spec.rds"))
mc_ds <- metacore::select_dataset(mc, dataset_name)
cat(mc_ds$ds_vars$variable, sep = "\n")
