library(metacore)
library(haven)

args <- commandArgs(trailingOnly = TRUE)
dataset_name <- args[1]

tryCatch({
  mc <- metacore::load_metacore(Sys.getenv("SAPIENT_SPEC_RDS", unset = "specs/metacore_spec.rds"))
  mc <- metacore::select_dataset(mc, dataset_name)
  ds <- haven::read_xpt(sprintf("data/adam/%s.xpt", dataset_name))
  result <- metatools::check_variables(ds, mc)
  print(result)
  cat("SUCCESS: metacore check complete\n")
}, error = function(e) {
  cat(sprintf("ERROR: %s\n", conditionMessage(e)))
  quit(status = 1)
})