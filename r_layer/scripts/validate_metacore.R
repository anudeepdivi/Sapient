library(metacore)
library(haven)

args <- commandArgs(trailingOnly = TRUE)
dataset_name <- args[1]
adam_dir <- if (length(args) >= 2) args[2] else "data/adam"

tryCatch({
  mc <- metacore::load_metacore(Sys.getenv("SAPIENT_SPEC_RDS", unset = "specs/metacore_spec.rds"))
  mc <- metacore::select_dataset(mc, dataset_name)
  ds <- haven::read_xpt(file.path(adam_dir, paste0(dataset_name, ".xpt")))
  result <- metatools::check_variables(ds, mc)
  print(result)
  cat("SUCCESS: metacore check complete\n")
}, error = function(e) {
  cat(sprintf("ERROR: %s\n", conditionMessage(e)))
  quit(status = 1)
})